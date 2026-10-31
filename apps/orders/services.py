from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.accounts.models import Address, User
from apps.cart import services as cart_services
from apps.catalog.models import Product, ProductVariant
from apps.core.exceptions import BusinessError
from apps.core.utils import after_commit, generate_number, money
from apps.notifications.events import emit

from .models import Order, OrderItem, OrderStatusHistory, ReturnItem, ReturnRequest, ShippingZone


# ---------------------------------------------------------------------------
# Shipping
# ---------------------------------------------------------------------------
def resolve_zone(city: str, province: str = "") -> ShippingZone | None:
    zones = list(ShippingZone.objects.filter(is_active=True))
    city_l, prov_l = (city or "").strip().lower(), (province or "").strip().lower()
    for z in zones:
        if city_l and city_l in [c.lower() for c in z.cities]:
            return z
    for z in zones:
        if prov_l and prov_l in [p.lower() for p in z.provinces]:
            return z
    return next((z for z in zones if z.is_default), zones[0] if zones else None)


def shipping_quote(
    *, subtotal: Decimal, city: str, province: str = "", payment_method: str = "cod", free_shipping: bool = False
) -> dict:
    zone = resolve_zone(city, province)
    if not zone:
        return {
            "zone": None,
            "rate": Decimal("0"),
            "cod_fee": Decimal("0"),
            "min_days": 3,
            "max_days": 7,
            "free_over": None,
            "is_free": True,
        }
    is_free = free_shipping or (zone.free_over is not None and subtotal >= zone.free_over)
    cod_fee = money(zone.cod_fee) if payment_method == Order.PaymentMethod.COD else Decimal("0")
    return {
        "zone": zone,
        "rate": Decimal("0") if is_free else money(zone.rate),
        "cod_fee": cod_fee,
        "min_days": zone.min_days,
        "max_days": zone.max_days,
        "free_over": zone.free_over,
        "is_free": is_free,
    }


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------
@transaction.atomic
def checkout(
    *,
    request,
    address: dict,
    payment_method: str,
    email: str,
    phone: str,
    notes: str = "",
    save_address: bool = False,
    is_gift: bool = False,
) -> Order:
    user = request.user if request.user.is_authenticated else None
    cart = cart_services.get_or_create_cart(request)
    totals = cart_services.compute_totals(cart, user=user, email=email)
    hard_issues = [i.issue for i in totals.items if i.issue and "reduced" not in i.issue]
    if hard_issues:
        raise BusinessError(hard_issues[0])
    lines = [i for i in totals.items if not i.issue or "reduced" in i.issue]
    if not lines:
        raise BusinessError("Your bag is empty.")
    if payment_method == Order.PaymentMethod.CARD:
        raise BusinessError("Card payments are coming soon — please choose cash on delivery or bank transfer.")

    quote = shipping_quote(
        subtotal=totals.subtotal - totals.discount,
        city=address["city"],
        province=address.get("province", ""),
        payment_method=payment_method,
        free_shipping=totals.free_shipping,
    )
    grand = money(totals.subtotal - totals.discount + quote["rate"] + quote["cod_fee"])

    # Lock variants in a stable order and take stock atomically.
    variant_ids = sorted(i.variant.pk for i in lines)
    # order_by(pk) drops the model's default colour/size ordering joins (FOR UPDATE can't lock outer joins).
    locked = {v.pk: v for v in ProductVariant.objects.select_for_update().filter(pk__in=variant_ids).order_by("pk")}
    for line in lines:
        v = locked[line.variant.pk]
        qty = min(line.item.quantity, line.available)
        if qty <= 0 or v.stock < qty:
            raise BusinessError(f"{v.product.name} ({v.label}) just sold out. Please update your bag.")

    order = Order.objects.create(
        number=generate_number(settings.SHOP["ORDER_NUMBER_PREFIX"]),
        user=user,
        email=email.lower(),
        phone=phone,
        status=Order.Status.PENDING,
        payment_status=Order.PaymentStatus.COD_PENDING
        if payment_method == Order.PaymentMethod.COD
        else Order.PaymentStatus.UNPAID,
        payment_method=payment_method,
        subtotal=totals.subtotal,
        discount_total=totals.discount,
        shipping_total=quote["rate"],
        cod_fee=quote["cod_fee"],
        grand_total=grand,
        total_quantity=sum(min(i.item.quantity, i.available) for i in lines),
        coupon_code=totals.coupon_code,
        shipping_zone=quote["zone"],
        shipping_address=address,
        customer_notes=notes[:500],
        is_gift=is_gift,
        estimated_delivery=timezone.localdate() + timedelta(days=quote["max_days"]),
    )
    items = []
    for line in lines:
        v = locked[line.variant.pk]
        qty = min(line.item.quantity, line.available)
        v.stock -= qty
        v.save(update_fields=["stock", "updated_at"])
        image = v.product.primary_image
        items.append(
            OrderItem(
                order=order,
                variant=v,
                product=v.product,
                product_name=v.product.name,
                variant_label=v.label,
                sku=v.sku,
                image_url=image.image.url if image else "",
                quantity=qty,
                unit_price=line.unit_price,
                compare_at_price=v.product.compare_at_price,
                line_total=money(line.unit_price * qty),
            )
        )
        Product.objects.filter(pk=v.product_id).update(sales_count=F("sales_count") + qty)
    OrderItem.objects.bulk_create(items)
    for pid in {i.product_id for i in items}:
        from apps.catalog.services import refresh_total_stock

        refresh_total_stock(pid)
    OrderStatusHistory.objects.create(order=order, to_status=order.status, changed_by=user, note="Order placed")

    if totals.coupon_code and totals.discount >= 0:
        from apps.promotions.models import Coupon, CouponRedemption

        coupon = Coupon.objects.select_for_update().filter(code=totals.coupon_code).first()
        if coupon:
            CouponRedemption.objects.create(coupon=coupon, order=order, user=user, email=order.email, discount=totals.discount)
            coupon.uses_count = F("uses_count") + 1
            coupon.save(update_fields=["uses_count"])

    if payment_method == Order.PaymentMethod.BANK_TRANSFER:
        from apps.payments.services import create_pending_payment

        create_pending_payment(order)

    if user:
        if save_address and not Address.objects.filter(user=user, line1=address["line1"], city=address["city"]).exists():
            Address.objects.create(
                user=user,
                **{
                    k: v
                    for k, v in address.items()
                    if k in {"full_name", "phone", "line1", "line2", "city", "province", "postal_code", "country"}
                },
                is_default=not Address.objects.filter(user=user).exists(),
            )
        User.objects.filter(pk=user.pk).update(order_count=F("order_count") + 1, total_spent=F("total_spent") + grand)

    cart.items.all().delete()
    cart_services.remove_coupon(cart)
    after_commit(lambda: emit("order.placed", order_id=order.pk))
    return order


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
STAMPS = {
    Order.Status.CONFIRMED: "confirmed_at",
    Order.Status.SHIPPED: "shipped_at",
    Order.Status.DELIVERED: "delivered_at",
    Order.Status.CANCELLED: "cancelled_at",
}


@transaction.atomic
def transition(order: Order, new_status: str, *, by=None, note: str = "", customer_visible=True, **fields) -> Order:
    order = Order.objects.select_for_update().get(pk=order.pk)
    if not order.can_transition(new_status):
        raise BusinessError(f"Cannot move an order from '{order.get_status_display()}' to '{Order.Status(new_status).label}'.")
    old = order.status
    order.status = new_status
    update_fields = ["status", "updated_at"]
    if new_status in STAMPS:
        setattr(order, STAMPS[new_status], timezone.now())
        update_fields.append(STAMPS[new_status])
    if new_status == Order.Status.DELIVERED and order.payment_method == Order.PaymentMethod.COD:
        order.payment_status = Order.PaymentStatus.PAID
        order.paid_at = timezone.now()
        update_fields += ["payment_status", "paid_at"]
    for key, value in fields.items():
        setattr(order, key, value)
        update_fields.append(key)
    order.save(update_fields=update_fields)
    OrderStatusHistory.objects.create(
        order=order, from_status=old, to_status=new_status, note=note, changed_by=by, is_customer_visible=customer_visible
    )
    after_commit(lambda: emit("order.status_changed", order_id=order.pk, from_status=old, to_status=new_status))
    return order


def _restock(order: Order):
    from apps.catalog.services import refresh_total_stock

    for item in order.items.select_related("variant"):
        if item.variant_id:
            ProductVariant.objects.filter(pk=item.variant_id).update(stock=F("stock") + item.quantity)
            Product.objects.filter(pk=item.product_id).update(sales_count=F("sales_count") - item.quantity)
            refresh_total_stock(item.product_id)


@transaction.atomic
def cancel(order: Order, *, by=None, reason: str = "", by_customer=True) -> Order:
    if by_customer and order.status not in Order.CANCELLABLE_STATUSES:
        raise BusinessError("This order is already being packed. Message us and we'll help.")
    if order.status not in (*Order.CANCELLABLE_STATUSES, Order.Status.PROCESSING):
        raise BusinessError("This order can no longer be cancelled.")
    _restock(order)
    if order.user_id:
        User.objects.filter(pk=order.user_id).update(
            order_count=F("order_count") - 1, total_spent=F("total_spent") - order.grand_total
        )
    fields = {"cancel_reason": reason[:300]}
    if order.payment_status == Order.PaymentStatus.PAID:
        fields["payment_status"] = Order.PaymentStatus.REFUNDED
        fields["refunded_total"] = order.grand_total
    return transition(
        order, Order.Status.CANCELLED, by=by, note=reason or ("Cancelled by customer" if by_customer else "Cancelled"), **fields
    )


@transaction.atomic
def reorder(order: Order, request) -> int:
    cart = cart_services.get_or_create_cart(request)
    added = 0
    for item in order.items.select_related("variant"):
        if not item.variant_id:
            continue
        try:
            cart_services.add_item(cart, variant_uid=item.variant.uid, quantity=item.quantity)
            added += 1
        except BusinessError:
            continue
    return added


@transaction.atomic
def mark_paid(order: Order, *, by=None, amount: Decimal | None = None) -> Order:
    order = Order.objects.select_for_update().get(pk=order.pk)
    order.payment_status = Order.PaymentStatus.PAID
    order.paid_at = timezone.now()
    order.save(update_fields=["payment_status", "paid_at", "updated_at"])
    if order.status == Order.Status.PENDING:
        transition(order, Order.Status.CONFIRMED, by=by, note="Payment received")
    after_commit(lambda: emit("order.paid", order_id=order.pk))
    return order


# ---------------------------------------------------------------------------
# Returns
# ---------------------------------------------------------------------------
@transaction.atomic
def request_return(order: Order, *, user, kind: str, reason: str, details: str, items: list[dict], image=None) -> ReturnRequest:
    if not order.can_return:
        raise BusinessError(f"Returns are accepted within {settings.SHOP['RETURN_WINDOW_DAYS']} days of delivery.")
    order_items = {str(i.uid): i for i in order.items.all()}
    if not items:
        raise BusinessError("Select at least one item to return.")
    req = ReturnRequest.objects.create(
        number=generate_number(settings.SHOP["RETURN_NUMBER_PREFIX"]),
        order=order,
        user=user,
        kind=kind,
        reason=reason,
        details=details[:2000],
        image=image,
    )
    refund = Decimal("0")
    for entry in items:
        item = order_items.get(str(entry["order_item"]))
        qty = int(entry.get("quantity", 1))
        if not item or qty < 1 or qty > item.quantity - item.returned_quantity:
            raise BusinessError("Invalid return quantity.")
        exchange = None
        if kind == ReturnRequest.Kind.EXCHANGE and entry.get("exchange_variant"):
            exchange = ProductVariant.objects.filter(
                uid=entry["exchange_variant"], product_id=item.product_id, is_active=True
            ).first()
        ReturnItem.objects.create(request=req, order_item=item, quantity=qty, exchange_variant=exchange)
        refund += item.unit_price * qty
    req.refund_amount = money(refund) if kind == ReturnRequest.Kind.REFUND else Decimal("0")
    req.save(update_fields=["refund_amount"])
    after_commit(lambda: emit("return.requested", return_id=req.pk))
    return req


@transaction.atomic
def resolve_return(
    req: ReturnRequest,
    *,
    status: str,
    by=None,
    staff_notes: str = "",
    refund_amount: Decimal | None = None,
    refund_method: str = "",
) -> ReturnRequest:
    req = ReturnRequest.objects.select_for_update().select_related("order").get(pk=req.pk)
    req.status = status
    req.staff_notes = staff_notes or req.staff_notes
    if refund_amount is not None:
        req.refund_amount = money(refund_amount)
    if refund_method:
        req.refund_method = refund_method
    if status in (ReturnRequest.Status.COMPLETED, ReturnRequest.Status.REJECTED):
        req.resolved_at = timezone.now()
    req.save()
    if status == ReturnRequest.Status.COMPLETED:
        order = req.order
        from apps.catalog.services import refresh_total_stock

        for ri in req.items.select_related("order_item"):
            OrderItem.objects.filter(pk=ri.order_item_id).update(returned_quantity=F("returned_quantity") + ri.quantity)
            if ri.order_item.variant_id:
                ProductVariant.objects.filter(pk=ri.order_item.variant_id).update(stock=F("stock") + ri.quantity)
                refresh_total_stock(ri.order_item.product_id)
        if req.kind == ReturnRequest.Kind.REFUND and req.refund_amount > 0:
            order.refunded_total = money(order.refunded_total + req.refund_amount)
            order.payment_status = (
                Order.PaymentStatus.REFUNDED
                if order.refunded_total >= order.grand_total
                else Order.PaymentStatus.PARTIALLY_REFUNDED
            )
            order.save(update_fields=["refunded_total", "payment_status", "updated_at"])
        if all(i.returned_quantity >= i.quantity for i in order.items.all()) and order.can_transition(Order.Status.RETURNED):
            transition(order, Order.Status.RETURNED, by=by, note=f"Return {req.number} completed")
    after_commit(lambda: emit("return.updated", return_id=req.pk))
    return req
