from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.accounts.models import Address, Company, CompanyMember
from apps.cart import services as cart_services
from apps.catalog.models import Product
from apps.core.exceptions import BusinessError
from apps.core.utils import after_commit, generate_number, money
from apps.notifications.events import emit

from .models import Order, OrderItem, OrderStatusHistory, ShippingMethod

NET_DAYS = {"net_15": 15, "net_30": 30, "net_60": 60}


def _needs_approval(company: Company, membership: CompanyMember, subtotal: Decimal) -> bool:
    if membership.role in CompanyMember.CAN_APPROVE:
        return False
    limit = membership.order_limit or company.approval_threshold
    return bool(limit and subtotal > limit)


def _validate_payment_method(company: Company, method: str, total: Decimal):
    if method == Order.PaymentMethod.NET_TERMS:
        if not company.allows_net_terms:
            raise BusinessError("Net terms are not enabled for your company yet. Choose bank transfer or contact sales.")
        if company.credit_limit and company.credit_available < total:
            raise BusinessError(
                f"This order exceeds your available credit ({company.currency} {company.credit_available:,.2f}). "
                "Reduce the order or pay by bank transfer."
            )
    elif method == Order.PaymentMethod.CARD:
        raise BusinessError("Card payments are coming soon. Please use bank transfer.")


def _cart_weight_kg(items) -> Decimal:
    grams = sum((item.product.weight_grams or 250) * item.quantity for item in items)
    return Decimal(grams) / Decimal(1000)


@transaction.atomic
def checkout(
    *,
    request,
    shipping_address_uid,
    billing_address_uid=None,
    shipping_method_code,
    payment_method,
    po_number="",
    customer_notes="",
    requested_delivery_date=None,
) -> Order:
    company: Company = request.company
    membership: CompanyMember = request.membership
    if not membership.can_order:
        raise BusinessError("Your role does not allow placing orders. Ask a company admin.")
    if not request.user.is_email_verified:
        raise BusinessError("Please verify your email address before placing an order.")

    cart = cart_services.get_or_create_cart(request)
    cart_services.validate_products_available(cart)
    totals = cart_services.reprice_cart(cart, company)
    items = totals["items"]
    if not items:
        raise BusinessError("Your cart is empty.")
    for item in items:
        if "error" in item.price_breakdown:
            raise BusinessError(f"{item.product.name}: {item.price_breakdown['error']}")

    shipping = Address.objects.filter(company=company, uid=shipping_address_uid).first()
    if not shipping:
        raise BusinessError("Select a shipping address.")
    billing = Address.objects.filter(company=company, uid=billing_address_uid).first() if billing_address_uid else shipping
    method = ShippingMethod.objects.filter(code=shipping_method_code, is_active=True).first()
    if not method:
        raise BusinessError("Select a shipping method.")

    subtotal = totals["subtotal"]
    shipping_total = method.estimate(_cart_weight_kg(items))
    grand_total = money(subtotal + shipping_total)
    _validate_payment_method(company, payment_method, grand_total)

    # Lock the company row so concurrent orders cannot both pass the credit check.
    company = Company.objects.select_for_update().get(pk=company.pk)

    needs_approval = _needs_approval(company, membership, subtotal)
    if needs_approval:
        status = Order.Status.PENDING_APPROVAL
    elif payment_method == Order.PaymentMethod.NET_TERMS:
        status = Order.Status.CONFIRMED
    else:
        status = Order.Status.PENDING_PAYMENT

    due_date = None
    if payment_method == Order.PaymentMethod.NET_TERMS:
        due_date = timezone.localdate() + timedelta(days=NET_DAYS.get(company.payment_terms, 30))

    order = Order.objects.create(
        number=generate_number(settings.LEEPA["ORDER_NUMBER_PREFIX"]),
        company=company,
        placed_by=request.user,
        status=status,
        payment_method=payment_method,
        payment_terms=company.payment_terms,
        po_number=po_number[:64],
        currency=cart.currency,
        subtotal=subtotal,
        discount_total=totals["savings"],
        shipping_total=shipping_total,
        grand_total=grand_total,
        total_quantity=totals["quantity"],
        shipping_method=method,
        shipping_address=shipping.as_snapshot(),
        billing_address=billing.as_snapshot(),
        customer_notes=customer_notes[:2000],
        requested_delivery_date=requested_delivery_date,
        due_date=due_date,
        confirmed_at=timezone.now() if status == Order.Status.CONFIRMED else None,
        estimated_ship_date=timezone.localdate() + timedelta(days=max((i.product.lead_time_days for i in items), default=21)),
    )
    OrderItem.objects.bulk_create(
        [
            OrderItem(
                order=order,
                product=item.product,
                fabric=item.fabric,
                product_name=item.product.name,
                sku=item.product.sku,
                fabric_name=item.fabric.name,
                image_url=(item.product.primary_image.image.url if item.product.primary_image else ""),
                breakdown=item.breakdown,
                quantity=item.quantity,
                color=item.color,
                customization=item.customization,
                artwork=item.artwork,
                notes=item.notes,
                unit_price=item.unit_price,
                line_total=item.line_total,
                price_breakdown=item.price_breakdown,
            )
            for item in items
        ]
    )
    OrderStatusHistory.objects.create(order=order, to_status=status, changed_by=request.user, note="Order placed")

    if payment_method == Order.PaymentMethod.NET_TERMS and status != Order.Status.PENDING_APPROVAL:
        Company.objects.filter(pk=company.pk).update(credit_used=F("credit_used") + grand_total)
    else:
        from apps.payments.services import create_pending_payment

        create_pending_payment(order)

    for item in items:
        Product.objects.filter(pk=item.product_id).update(order_count=F("order_count") + item.quantity)
    cart.items.all().delete()

    after_commit(lambda: emit("order.placed", order_id=order.pk))
    if needs_approval:
        after_commit(lambda: emit("order.approval_requested", order_id=order.pk))
    return order


@transaction.atomic
def transition(order: Order, new_status: str, *, by=None, note: str = "", customer_visible=True, **fields) -> Order:
    order = Order.objects.select_for_update().get(pk=order.pk)
    if not order.can_transition(new_status):
        raise BusinessError(f"Cannot move an order from '{order.get_status_display()}' to '{Order.Status(new_status).label}'.")
    old = order.status
    now = timezone.now()
    order.status = new_status
    stamps = {
        Order.Status.CONFIRMED: "confirmed_at",
        Order.Status.SHIPPED: "shipped_at",
        Order.Status.DELIVERED: "delivered_at",
        Order.Status.CANCELLED: "cancelled_at",
    }
    update_fields = ["status", "updated_at"]
    if new_status in stamps:
        setattr(order, stamps[new_status], now)
        update_fields.append(stamps[new_status])
    for key, value in fields.items():
        setattr(order, key, value)
        update_fields.append(key)
    order.save(update_fields=update_fields)
    OrderStatusHistory.objects.create(
        order=order, from_status=old, to_status=new_status, note=note, changed_by=by, is_customer_visible=customer_visible
    )
    after_commit(lambda: emit("order.status_changed", order_id=order.pk, from_status=old, to_status=new_status))
    return order


@transaction.atomic
def approve(order: Order, *, by, membership: CompanyMember) -> Order:
    if membership.role not in CompanyMember.CAN_APPROVE:
        raise BusinessError("Only company admins or owners can approve orders.")
    if order.status != Order.Status.PENDING_APPROVAL:
        raise BusinessError("This order is not waiting for approval.")
    target = Order.Status.CONFIRMED if order.payment_method == Order.PaymentMethod.NET_TERMS else Order.Status.PENDING_PAYMENT
    if order.payment_method == Order.PaymentMethod.NET_TERMS:
        Company.objects.filter(pk=order.company_id).update(credit_used=F("credit_used") + order.grand_total)
    return transition(order, target, by=by, note=f"Approved by {by.full_name}", approved_by=by, approved_at=timezone.now())


@transaction.atomic
def cancel(order: Order, *, by, reason: str = "") -> Order:
    if order.status not in Order.CANCELLABLE_STATUSES:
        raise BusinessError("This order is already in production and can no longer be cancelled online. Please contact us.")
    if order.payment_method == Order.PaymentMethod.NET_TERMS and order.status != Order.Status.PENDING_APPROVAL:
        Company.objects.filter(pk=order.company_id).update(credit_used=F("credit_used") - order.grand_total)
    for item in order.items.all():
        if item.product_id:
            Product.objects.filter(pk=item.product_id).update(order_count=F("order_count") - item.quantity)
    return transition(order, Order.Status.CANCELLED, by=by, note=reason or "Cancelled by customer", cancel_reason=reason[:300])


def reorder(order: Order, request) -> int:
    cart = cart_services.get_or_create_cart(request)
    added = 0
    for item in order.items.select_related("product", "fabric"):
        if not item.product or not item.product.is_active:
            continue
        try:
            cart_services.add_item(
                cart,
                request.company,
                product_slug=item.product.slug,
                fabric_slug=item.fabric.slug if item.fabric else None,
                breakdown=item.breakdown,
                color=item.color,
                customization=item.customization,
                notes=item.notes,
            )
            added += 1
        except BusinessError:
            continue
    return added


def record_payment(order: Order, amount: Decimal):
    """Called by payments when money is confirmed; updates status & payment flags."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    order.amount_paid = money(order.amount_paid + amount)
    if order.amount_paid >= order.grand_total:
        order.payment_status = Order.PaymentStatus.PAID
    elif order.amount_paid > 0:
        order.payment_status = Order.PaymentStatus.DEPOSIT_PAID
    order.save(update_fields=["amount_paid", "payment_status", "updated_at"])
    if order.status == Order.Status.PENDING_PAYMENT and order.payment_status in (
        Order.PaymentStatus.PAID,
        Order.PaymentStatus.DEPOSIT_PAID,
    ):
        transition(order, Order.Status.CONFIRMED, note="Payment received")
    after_commit(lambda: emit("order.payment_received", order_id=order.pk, amount=str(amount)))
    return order
