"""Coupon validation and discount computation. All prices in the store currency."""

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Q

from apps.core.exceptions import BusinessError
from apps.core.utils import money

from .models import Coupon, CouponRedemption


@dataclass
class CouponResult:
    coupon: Coupon
    discount: Decimal
    free_shipping: bool
    message: str


def _eligible_subtotal(coupon: Coupon, items) -> Decimal:
    """Subtotal of items the coupon applies to (all items if unrestricted)."""
    category_paths = list(coupon.categories.values_list("path", flat=True))
    product_ids = set(coupon.products.values_list("id", flat=True))
    if not category_paths and not product_ids:
        return money(sum(i.line_total for i in items))
    total = Decimal("0")
    for item in items:
        product = item.variant.product
        if product.id in product_ids or any(product.category.path.startswith(p) for p in category_paths):
            total += item.line_total
    return money(total)


def validate_coupon(code: str, *, items, user=None, email: str = "", shipping: Decimal = Decimal("0")) -> CouponResult:
    code = (code or "").strip().upper()
    coupon = Coupon.objects.filter(code=code).prefetch_related("categories", "products").first()
    if not coupon or not coupon.is_live:
        raise BusinessError("That code isn't valid or has expired.")
    subtotal = money(sum(i.line_total for i in items))
    if subtotal < coupon.min_subtotal:
        raise BusinessError(f"Spend at least Rs {coupon.min_subtotal:,.0f} to use {coupon.code}.")
    if user is not None or email:
        q = Q(user=user) if user is not None else Q(email__iexact=email)
        used = CouponRedemption.objects.filter(coupon=coupon).filter(q).count()
        if used >= coupon.max_uses_per_user:
            raise BusinessError("You've already used this code.")
    if coupon.first_order_only:
        from apps.orders.models import Order

        q = Q(user=user) if user is not None else Q(email__iexact=email)
        if (user is not None or email) and Order.objects.filter(q).exclude(status=Order.Status.CANCELLED).exists():
            raise BusinessError("This code is for first orders only.")
    eligible = _eligible_subtotal(coupon, items)
    if eligible <= 0:
        raise BusinessError("This code doesn't apply to the items in your bag.")

    if coupon.kind == Coupon.Kind.PERCENT:
        discount = money(eligible * coupon.value / Decimal("100"))
        if coupon.max_discount:
            discount = min(discount, money(coupon.max_discount))
        message = f"{coupon.value:g}% off applied"
    elif coupon.kind == Coupon.Kind.FIXED:
        discount = min(money(coupon.value), eligible)
        message = f"Rs {discount:,.0f} off applied"
    else:
        discount = Decimal("0")
        message = "Free shipping applied"
    return CouponResult(coupon=coupon, discount=discount, free_shipping=coupon.kind == Coupon.Kind.FREE_SHIPPING, message=message)
