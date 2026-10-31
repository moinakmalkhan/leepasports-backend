import secrets
import uuid
from decimal import Decimal

from django.db import transaction
from django.db.models import F

from apps.catalog.models import Product
from apps.core.exceptions import BusinessError
from apps.core.utils import money
from apps.pricing.selectors import resolve_configuration
from apps.pricing.services import compute_price

from .models import Cart, CartItem, SavedList, SavedListItem


def get_or_create_cart(request) -> Cart:
    """Resolve the cart for this request: company cart for members, user cart
    for people without a company, guest cart (by token header) otherwise."""
    user = request.user if request.user.is_authenticated else None
    company = getattr(request, "company", None)
    guest_token = request.headers.get("X-Cart-Token", "")

    if user:
        cart, _ = Cart.objects.get_or_create(
            company=company,
            user=user,
            defaults={"currency": company.currency if company else Cart._meta.get_field("currency").default},
        )
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
        item.pk = None
        item.uid = uuid.uuid4()
        item.cart = target
        item.save()
    guest.delete()


def price_item(item: CartItem, company):
    product = item.product
    product_obj, fabric, adjustment, normalised = resolve_configuration(
        product=product, fabric=item.fabric.slug, breakdown=item.breakdown
    )
    result = compute_price(
        product=product_obj, fabric=fabric, breakdown=normalised, company=company, fabric_adjustment=adjustment
    )
    item.quantity = result.quantity
    item.unit_price = result.unit_price
    item.line_total = result.subtotal
    item.price_breakdown = result.as_dict()
    return result


@transaction.atomic
def add_item(
    cart: Cart, company, *, product_slug, fabric_slug, breakdown, color="", customization=None, notes="", artwork=None
) -> CartItem:
    product, fabric, adjustment, normalised = resolve_configuration(product=product_slug, fabric=fabric_slug, breakdown=breakdown)
    stored = [
        {"gender": line["gender"], "size_id": line["size"].id, "size": line["size"].label, "quantity": line["quantity"]}
        for line in normalised
    ]
    item = CartItem(
        cart=cart,
        product=product,
        fabric=fabric,
        breakdown=stored,
        color=color or "",
        customization=customization or {},
        notes=notes or "",
        artwork=artwork,
    )
    price_item(item, company)
    item.save()
    Cart.objects.filter(pk=cart.pk).update(updated_at=F("updated_at"))
    return item


@transaction.atomic
def update_item(item: CartItem, company, **changes) -> CartItem:
    if "breakdown" in changes or "fabric_slug" in changes:
        fabric_slug = changes.get("fabric_slug", item.fabric.slug)
        product, fabric, adjustment, normalised = resolve_configuration(
            product=item.product, fabric=fabric_slug, breakdown=changes.get("breakdown", item.breakdown)
        )
        item.fabric = fabric
        item.breakdown = [
            {"gender": line["gender"], "size_id": line["size"].id, "size": line["size"].label, "quantity": line["quantity"]}
            for line in normalised
        ]
    for attr in ("color", "customization", "notes"):
        if attr in changes and changes[attr] is not None:
            setattr(item, attr, changes[attr])
    if changes.get("artwork") is not None:
        item.artwork = changes["artwork"]
    price_item(item, company)
    item.save()
    return item


@transaction.atomic
def reprice_cart(cart: Cart, company) -> dict:
    """Re-run pricing for every line (prices/rates may have moved) and return totals."""
    items = list(cart.items.select_related("product__base_fabric", "product__category", "fabric"))
    subtotal = Decimal("0")
    savings = Decimal("0")
    quantity = 0
    for item in items:
        try:
            result = price_item(item, company)
            savings += result.savings
        except BusinessError as exc:
            item.price_breakdown = {"error": str(exc)}
        subtotal += item.line_total
        quantity += item.quantity
    CartItem.objects.bulk_update(items, ["quantity", "unit_price", "line_total", "price_breakdown"])
    return {
        "items": items,
        "subtotal": money(subtotal),
        "savings": money(savings),
        "quantity": quantity,
        "item_count": len(items),
    }


@transaction.atomic
def add_saved_list_to_cart(saved_list: SavedList, cart: Cart, company) -> int:
    added = 0
    for entry in saved_list.items.select_related("product", "fabric"):
        if not entry.product.is_active:
            continue
        fabric_slug = entry.fabric.slug if entry.fabric else None
        try:
            add_item(
                cart,
                company,
                product_slug=entry.product.slug,
                fabric_slug=fabric_slug,
                breakdown=entry.breakdown,
                color=entry.color,
                customization=entry.customization,
                notes=entry.notes,
            )
            added += 1
        except BusinessError:
            continue
    return added


@transaction.atomic
def save_cart_as_list(cart: Cart, company, user, name: str, description: str = "") -> SavedList:
    saved = SavedList.objects.create(company=company, created_by=user, name=name, description=description)
    SavedListItem.objects.bulk_create(
        [
            SavedListItem(
                saved_list=saved,
                product=i.product,
                fabric=i.fabric,
                breakdown=i.breakdown,
                color=i.color,
                customization=i.customization,
                notes=i.notes,
            )
            for i in cart.items.all()
        ]
    )
    return saved


def validate_products_available(cart: Cart):
    inactive = Product.objects.filter(pk__in=cart.items.values("product_id"), is_active=False).values_list("name", flat=True)
    if inactive:
        raise BusinessError(f"Some products are no longer available: {', '.join(inactive)}.")
