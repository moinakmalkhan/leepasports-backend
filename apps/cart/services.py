"""Cart logic. Prices come from the catalog on every read; the client never sends a price."""

import secrets
from dataclasses import dataclass, field
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F

from apps.catalog.models import ProductVariant
from apps.core.exceptions import BusinessError
from apps.core.utils import money

from .models import Cart, CartItem, Wishlist, WishlistItem

MAX_QTY_PER_LINE = 10


@dataclass
class PricedItem:
    item: CartItem
    variant: ProductVariant
    unit_price: Decimal
    line_total: Decimal
    available: int
    issue: str = ""


@dataclass
class CartTotals:
    cart: Cart
    items: list[PricedItem]
    subtotal: Decimal
    discount: Decimal
    coupon_code: str
    coupon_message: str
    free_shipping: bool
    quantity: int
    issues: list[str] = field(default_factory=list)


def get_or_create_cart(request) -> Cart:
    user = request.user if request.user.is_authenticated else None
    guest_token = request.headers.get("X-Cart-Token", "")
    if user:
        cart, _ = Cart.objects.get_or_create(user=user)
        if guest_token:
            merge_guest_cart(guest_token, cart)
        return cart
    if guest_token:
        cart = Cart.objects.filter(guest_token=guest_token, user__isnull=True).first()
        if cart:
            return cart
    return Cart.objects.create(guest_token=secrets.token_urlsafe(32))


@transaction.atomic
def merge_guest_cart(guest_token: str, target: Cart):
    guest = Cart.objects.filter(guest_token=guest_token, user__isnull=True).exclude(pk=target.pk).first()
    if not guest:
        return
    for item in guest.items.all():
        existing = target.items.filter(variant_id=item.variant_id).first()
        if existing:
            existing.quantity = min(existing.quantity + item.quantity, MAX_QTY_PER_LINE)
            existing.save(update_fields=["quantity"])
        else:
            CartItem.objects.create(cart=target, variant_id=item.variant_id, quantity=item.quantity)
    if guest.coupon_code and not target.coupon_code:
        target.coupon_code = guest.coupon_code
        target.save(update_fields=["coupon_code"])
    guest.delete()


def priced_items(cart: Cart) -> list[PricedItem]:
    items = cart.items.select_related("variant__product__category", "variant__color", "variant__size").prefetch_related(
        "variant__product__images"
    )
    out = []
    for item in items:
        v = item.variant
        issue = ""
        if not v.is_active or not v.product.is_active:
            issue = "This item is no longer available."
        elif v.stock <= 0:
            issue = "Sold out — remove it to continue."
        elif item.quantity > v.stock:
            issue = f"Only {v.stock} left; quantity reduced."
        qty = min(item.quantity, max(v.stock, 0)) if not issue or "reduced" in issue else (0 if issue else item.quantity)
        unit = money(v.price)
        out.append(
            PricedItem(item=item, variant=v, unit_price=unit, line_total=money(unit * qty), available=v.stock, issue=issue)
        )
    return out


def compute_totals(cart: Cart, *, user=None, email: str = "") -> CartTotals:
    items = priced_items(cart)
    valid = [i for i in items if not i.issue or "reduced" in i.issue]
    subtotal = money(sum(i.line_total for i in valid))
    quantity = sum(min(i.item.quantity, i.available) for i in valid)
    discount, message, free_shipping, code = Decimal("0"), "", False, cart.coupon_code
    if cart.coupon_code and valid:
        from apps.promotions.services import validate_coupon

        try:
            result = validate_coupon(cart.coupon_code, items=valid, user=user, email=email)
            discount, message, free_shipping, code = result.discount, result.message, result.free_shipping, result.coupon.code
        except BusinessError as exc:
            message = str(exc.detail)
            code = ""
    return CartTotals(
        cart=cart,
        items=items,
        subtotal=subtotal,
        discount=discount,
        coupon_code=code,
        coupon_message=message,
        free_shipping=free_shipping,
        quantity=quantity,
        issues=[i.issue for i in items if i.issue],
    )


@transaction.atomic
def add_item(cart: Cart, *, variant_uid, quantity: int = 1) -> CartItem:
    variant = (
        ProductVariant.objects.select_related("product").filter(uid=variant_uid, is_active=True, product__is_active=True).first()
    )
    if not variant:
        raise BusinessError("That option isn't available.")
    if variant.stock <= 0:
        raise BusinessError(f"{variant.product.name} ({variant.label}) is sold out.")
    quantity = max(1, quantity)
    item = CartItem.objects.select_for_update().filter(cart=cart, variant=variant).first()
    new_qty = (item.quantity if item else 0) + quantity
    if new_qty > MAX_QTY_PER_LINE:
        raise BusinessError(f"You can order up to {MAX_QTY_PER_LINE} of the same item.")
    if new_qty > variant.stock:
        raise BusinessError(f"Only {variant.stock} left in stock.")
    if item:
        item.quantity = new_qty
        item.save(update_fields=["quantity", "updated_at"])
    else:
        item = CartItem.objects.create(cart=cart, variant=variant, quantity=new_qty)
    Cart.objects.filter(pk=cart.pk).update(updated_at=F("updated_at"))
    return item


@transaction.atomic
def set_quantity(item: CartItem, quantity: int) -> CartItem | None:
    if quantity <= 0:
        item.delete()
        return None
    if quantity > MAX_QTY_PER_LINE:
        raise BusinessError(f"You can order up to {MAX_QTY_PER_LINE} of the same item.")
    if quantity > item.variant.stock:
        raise BusinessError(f"Only {item.variant.stock} left in stock.")
    item.quantity = quantity
    item.save(update_fields=["quantity", "updated_at"])
    return item


def apply_coupon(cart: Cart, code: str, *, user=None, email: str = ""):
    from apps.promotions.services import validate_coupon

    items = [i for i in priced_items(cart) if not i.issue or "reduced" in i.issue]
    if not items:
        raise BusinessError("Add something to your bag first.")
    result = validate_coupon(code, items=items, user=user, email=email)
    cart.coupon_code = result.coupon.code
    cart.save(update_fields=["coupon_code", "updated_at"])
    return result


def remove_coupon(cart: Cart):
    cart.coupon_code = ""
    cart.save(update_fields=["coupon_code", "updated_at"])


def purge_guest_carts(days: int | None = None):
    from datetime import timedelta

    from django.utils import timezone

    cutoff = timezone.now() - timedelta(days=days or settings.SHOP["CART_GUEST_TTL_DAYS"])
    return Cart.objects.filter(user__isnull=True, updated_at__lt=cutoff).delete()


# ---- wishlist -------------------------------------------------------------
def get_wishlist(user) -> Wishlist:
    wishlist, _ = Wishlist.objects.get_or_create(user=user)
    return wishlist


@transaction.atomic
def toggle_wishlist(user, product, variant=None) -> bool:
    wishlist = get_wishlist(user)
    existing = WishlistItem.objects.filter(wishlist=wishlist, product=product).first()
    if existing:
        existing.delete()
        return False
    WishlistItem.objects.create(wishlist=wishlist, product=product, variant=variant)
    return True
