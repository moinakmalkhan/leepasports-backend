from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.accounts.models import Address, Company
from apps.cart import services as cart_services
from apps.catalog.models import Product
from apps.core.exceptions import BusinessError
from apps.core.utils import after_commit, generate_number, money
from apps.notifications.events import emit
from apps.orders.models import Order, OrderItem, OrderStatusHistory
from apps.orders.services import NET_DAYS

from .models import Quote, QuoteItem


@transaction.atomic
def request_quote(*, request, customer_notes="", target_budget=None, delivery_deadline=None, shipping_address_uid=None) -> Quote:
    company: Company = request.company
    if not request.membership.can_order:
        raise BusinessError("Your role does not allow requesting quotes.")
    cart = cart_services.get_or_create_cart(request)
    cart_services.validate_products_available(cart)
    totals = cart_services.reprice_cart(cart, company)
    items = totals["items"]
    if not items:
        raise BusinessError("Your cart is empty. Configure the products you'd like quoted first.")
    address = Address.objects.filter(company=company, uid=shipping_address_uid).first() if shipping_address_uid else None

    quote = Quote.objects.create(
        number=generate_number(settings.LEEPA["QUOTE_NUMBER_PREFIX"]),
        company=company,
        requested_by=request.user,
        currency=cart.currency,
        requested_total=totals["subtotal"],
        total_quantity=totals["quantity"],
        target_budget=target_budget,
        delivery_deadline=delivery_deadline,
        shipping_address=address.as_snapshot() if address else {},
        customer_notes=customer_notes[:3000],
    )
    QuoteItem.objects.bulk_create(
        [
            QuoteItem(
                quote=quote,
                product=i.product,
                fabric=i.fabric,
                product_name=i.product.name,
                sku=i.product.sku,
                fabric_name=i.fabric.name,
                image_url=(i.product.primary_image.image.url if i.product.primary_image else ""),
                breakdown=i.breakdown,
                quantity=i.quantity,
                color=i.color,
                customization=i.customization,
                artwork=i.artwork,
                notes=i.notes,
                requested_unit_price=i.unit_price,
                line_total=i.line_total,
                price_breakdown=i.price_breakdown,
            )
            for i in items
        ]
    )
    cart.items.all().delete()
    after_commit(lambda: emit("quote.submitted", quote_id=quote.pk))
    return quote


@transaction.atomic
def respond(
    quote: Quote, *, by, item_prices: dict, message: str = "", valid_days: int | None = None, internal_notes: str = ""
) -> Quote:
    """Staff: set quoted unit prices (keyed by item uid) and publish the quote."""
    quote = Quote.objects.select_for_update().get(pk=quote.pk)
    if quote.status not in (Quote.Status.SUBMITTED, Quote.Status.UNDER_REVIEW, Quote.Status.QUOTED):
        raise BusinessError("This quote can no longer be edited.")
    total = Decimal("0")
    items = list(quote.items.all())
    for item in items:
        price = item_prices.get(str(item.uid))
        unit = money(price) if price is not None else (item.quoted_unit_price or item.requested_unit_price)
        item.quoted_unit_price = unit
        item.line_total = money(unit * item.quantity)
        total += item.line_total
    QuoteItem.objects.bulk_update(items, ["quoted_unit_price", "line_total"])
    quote.quoted_total = money(total)
    quote.status = Quote.Status.QUOTED
    quote.handled_by = by
    quote.response_message = message
    quote.internal_notes = internal_notes or quote.internal_notes
    quote.valid_until = timezone.localdate() + timedelta(days=valid_days or settings.LEEPA["QUOTE_VALIDITY_DAYS"])
    quote.quoted_at = timezone.now()
    quote.responded_at = quote.quoted_at
    quote.save()
    after_commit(lambda: emit("quote.quoted", quote_id=quote.pk))
    return quote


@transaction.atomic
def accept(quote: Quote, *, request, shipping_address_uid, payment_method, po_number="") -> Order:
    quote = Quote.objects.select_for_update().select_related("company").get(pk=quote.pk)
    if quote.status != Quote.Status.QUOTED:
        raise BusinessError("This quote is not ready to be accepted.")
    if quote.valid_until and quote.valid_until < timezone.localdate():
        quote.status = Quote.Status.EXPIRED
        quote.save(update_fields=["status"])
        raise BusinessError("This quote has expired. Please request a fresh one.")
    company = Company.objects.select_for_update().get(pk=quote.company_id)
    address = Address.objects.filter(company=company, uid=shipping_address_uid).first()
    if not address:
        raise BusinessError("Select a shipping address.")
    if payment_method == Order.PaymentMethod.NET_TERMS and not company.allows_net_terms:
        raise BusinessError("Net terms are not enabled for your company.")
    if payment_method == Order.PaymentMethod.NET_TERMS and company.credit_limit and company.credit_available < quote.quoted_total:
        raise BusinessError("This order exceeds your available credit.")

    net = payment_method == Order.PaymentMethod.NET_TERMS
    order = Order.objects.create(
        number=generate_number(settings.LEEPA["ORDER_NUMBER_PREFIX"]),
        company=company,
        placed_by=request.user,
        quote=quote,
        status=Order.Status.CONFIRMED if net else Order.Status.PENDING_PAYMENT,
        payment_method=payment_method,
        payment_terms=company.payment_terms,
        po_number=po_number[:64],
        currency=quote.currency,
        subtotal=quote.quoted_total,
        discount_total=money(max(quote.requested_total - quote.quoted_total, 0)),
        grand_total=quote.quoted_total,
        total_quantity=quote.total_quantity,
        shipping_address=address.as_snapshot(),
        billing_address=address.as_snapshot(),
        customer_notes=f"From quote {quote.number}",
        due_date=(timezone.localdate() + timedelta(days=NET_DAYS.get(company.payment_terms, 30))) if net else None,
        confirmed_at=timezone.now() if net else None,
        estimated_ship_date=timezone.localdate() + timedelta(days=settings.LEEPA["DEFAULT_LEAD_TIME_DAYS"]),
    )
    OrderItem.objects.bulk_create(
        [
            OrderItem(
                order=order,
                product=i.product,
                fabric=i.fabric,
                product_name=i.product_name,
                sku=i.sku,
                fabric_name=i.fabric_name,
                image_url=i.image_url,
                breakdown=i.breakdown,
                quantity=i.quantity,
                color=i.color,
                customization=i.customization,
                artwork=i.artwork,
                notes=i.notes,
                unit_price=i.quoted_unit_price or i.requested_unit_price,
                line_total=i.line_total,
                price_breakdown={**i.price_breakdown, "quoted": True},
            )
            for i in quote.items.all()
        ]
    )
    OrderStatusHistory.objects.create(
        order=order, to_status=order.status, changed_by=request.user, note=f"Created from quote {quote.number}"
    )
    if net:
        Company.objects.filter(pk=company.pk).update(credit_used=F("credit_used") + order.grand_total)
    else:
        from apps.payments.services import create_pending_payment

        create_pending_payment(order)
    for item in quote.items.all():
        if item.product_id:
            Product.objects.filter(pk=item.product_id).update(order_count=F("order_count") + item.quantity)
    quote.status = Quote.Status.CONVERTED
    quote.save(update_fields=["status", "updated_at"])
    after_commit(lambda: emit("order.placed", order_id=order.pk))
    after_commit(lambda: emit("quote.accepted", quote_id=quote.pk))
    return order


def decline(quote: Quote, *, by, reason: str = "") -> Quote:
    if quote.status not in (Quote.Status.SUBMITTED, Quote.Status.UNDER_REVIEW, Quote.Status.QUOTED):
        raise BusinessError("This quote cannot be declined now.")
    quote.status = Quote.Status.DECLINED
    quote.internal_notes = (quote.internal_notes + f"\nDeclined by {by}: {reason}").strip()
    quote.save(update_fields=["status", "internal_notes", "updated_at"])
    emit("quote.declined", quote_id=quote.pk)
    return quote
