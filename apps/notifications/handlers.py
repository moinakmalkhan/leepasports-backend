"""Who hears about what. One place to read the whole communication policy."""

from django.conf import settings

from apps.accounts.models import CompanyMember

from .events import on
from .models import Notification
from .services import notify_company, notify_staff, notify_users
from .tasks import send_email_task

L = Notification.Level
K = Notification.Kind


def _order(order_id):
    from apps.orders.models import Order

    return Order.objects.select_related("company", "placed_by").prefetch_related("items").get(pk=order_id)


def _quote(quote_id):
    from apps.quotes.models import Quote

    return Quote.objects.select_related("company", "requested_by").prefetch_related("items").get(pk=quote_id)


def _order_ctx(order):
    return {"order_id": order.pk, "url": f"{settings.FRONTEND_URL}/account/orders/{order.uid}"}


@on("order.placed")
def order_placed(order_id):
    order = _order(order_id)
    ctx = _order_ctx(order)
    buyers = [order.placed_by] if order.placed_by else []
    for user in buyers:
        send_email_task.delay(template="order_confirmation", to=[user.email], context={**ctx, "name": user.full_name})
    notify_company(
        order.company,
        kind=K.ORDER,
        level=L.SUCCESS,
        title=f"Order {order.number} placed",
        body=f"{order.total_quantity} pcs · {order.currency} {order.grand_total:,.2f}",
        url=f"/account/orders/{order.uid}",
    )
    notify_staff(
        event="order.placed",
        subject=f"New order {order.number} from {order.company.name}",
        context={
            "total": f"{order.currency} {order.grand_total:,.2f}",
            "quantity": order.total_quantity,
            "payment": order.get_payment_method_display(),
            "summary": f"{order.company.name} · {order.total_quantity} pcs",
        },
        url=f"/admin/orders/order/{order.pk}/change/",
    )


@on("order.approval_requested")
def order_approval_requested(order_id):
    order = _order(order_id)
    approvers = [
        m.user
        for m in CompanyMember.objects.filter(
            company=order.company, role__in=CompanyMember.CAN_APPROVE, is_active=True
        ).select_related("user")
    ]
    notify_users(
        approvers,
        company=order.company,
        kind=K.ORDER,
        level=L.WARNING,
        title=f"Approval needed: {order.number}",
        body=f"{order.placed_by.full_name if order.placed_by else 'A buyer'} placed an order of {order.currency} {order.grand_total:,.2f}",
        url=f"/account/orders/{order.uid}",
    )
    for user in approvers:
        send_email_task.delay(template="order_approval", to=[user.email], context={**_order_ctx(order), "name": user.full_name})


STATUS_COPY = {
    "confirmed": ("Order confirmed", "We've confirmed your order and are scheduling production.", L.SUCCESS),
    "in_production": ("In production", "Your garments are being cut and stitched.", L.INFO),
    "quality_check": ("Quality check", "Your order is in final QC and packing.", L.INFO),
    "shipped": ("Shipped", "Your order is on its way.", L.SUCCESS),
    "delivered": ("Delivered", "Your order has been delivered.", L.SUCCESS),
    "completed": ("Completed", "Thanks for ordering with Leepa Sports.", L.SUCCESS),
    "cancelled": ("Cancelled", "Your order was cancelled.", L.WARNING),
    "pending_payment": ("Awaiting payment", "Your order is approved and awaiting payment.", L.WARNING),
}


@on("order.status_changed")
def order_status_changed(order_id, from_status, to_status):
    order = _order(order_id)
    title, body, level = STATUS_COPY.get(to_status, (to_status.replace("_", " ").title(), "", L.INFO))
    notify_company(
        order.company, kind=K.ORDER, level=level, title=f"{order.number}: {title}", body=body, url=f"/account/orders/{order.uid}"
    )
    if order.placed_by and to_status in ("confirmed", "shipped", "delivered", "cancelled", "pending_payment"):
        send_email_task.delay(
            template="order_status",
            to=[order.placed_by.email],
            context={**_order_ctx(order), "name": order.placed_by.full_name, "title": title, "body": body, "status": to_status},
        )


@on("order.payment_received")
def order_payment_received(order_id, amount):
    order = _order(order_id)
    notify_company(
        order.company,
        kind=K.PAYMENT,
        level=L.SUCCESS,
        title=f"Payment received for {order.number}",
        body=f"{order.currency} {amount} confirmed",
        url=f"/account/orders/{order.uid}",
    )


@on("payment.submitted")
def payment_submitted(payment_id):
    from apps.payments.models import Payment

    payment = Payment.objects.select_related("order__company").get(pk=payment_id)
    notify_staff(
        event="payment.submitted",
        subject=f"Payment proof submitted for {payment.order.number}",
        context={
            "amount": f"{payment.currency} {payment.amount}",
            "reference": payment.reference,
            "company": payment.order.company.name,
            "summary": payment.reference,
        },
        url=f"/admin/payments/payment/{payment.pk}/change/",
    )
    notify_company(
        payment.order.company,
        kind=K.PAYMENT,
        level=L.INFO,
        title=f"Payment proof received for {payment.order.number}",
        body="We'll confirm it within one business day.",
        url=f"/account/orders/{payment.order.uid}",
    )


@on("quote.submitted")
def quote_submitted(quote_id):
    quote = _quote(quote_id)
    notify_company(
        quote.company,
        kind=K.QUOTE,
        level=L.INFO,
        title=f"Quote request {quote.number} sent",
        body="Our sales team replies within 1 business day.",
        url=f"/account/quotes/{quote.uid}",
    )
    if quote.requested_by:
        send_email_task.delay(
            template="quote_submitted",
            to=[quote.requested_by.email],
            context={
                "quote_id": quote.pk,
                "name": quote.requested_by.full_name,
                "url": f"{settings.FRONTEND_URL}/account/quotes/{quote.uid}",
            },
        )
    notify_staff(
        event="quote.submitted",
        subject=f"New quote request {quote.number} from {quote.company.name}",
        context={
            "quantity": quote.total_quantity,
            "list_total": f"{quote.currency} {quote.requested_total:,.2f}",
            "deadline": quote.delivery_deadline or "-",
            "summary": f"{quote.total_quantity} pcs",
        },
        url=f"/admin/quotes/quote/{quote.pk}/change/",
    )


@on("quote.quoted")
def quote_quoted(quote_id):
    quote = _quote(quote_id)
    notify_company(
        quote.company,
        kind=K.QUOTE,
        level=L.SUCCESS,
        title=f"Your quote {quote.number} is ready",
        body=f"{quote.currency} {quote.quoted_total:,.2f} · valid until {quote.valid_until}",
        url=f"/account/quotes/{quote.uid}",
    )
    if quote.requested_by:
        send_email_task.delay(
            template="quote_ready",
            to=[quote.requested_by.email],
            context={
                "quote_id": quote.pk,
                "name": quote.requested_by.full_name,
                "url": f"{settings.FRONTEND_URL}/account/quotes/{quote.uid}",
            },
        )


@on("quote.accepted")
def quote_accepted(quote_id):
    quote = _quote(quote_id)
    notify_staff(
        event="quote.accepted",
        subject=f"Quote {quote.number} accepted by {quote.company.name}",
        context={"total": f"{quote.currency} {quote.quoted_total}", "summary": "Converted to order"},
        url=f"/admin/quotes/quote/{quote.pk}/change/",
    )


@on("quote.declined")
def quote_declined(quote_id):
    quote = _quote(quote_id)
    notify_staff(
        event="quote.declined",
        subject=f"Quote {quote.number} declined",
        context={"company": quote.company.name, "summary": "Declined by customer"},
        url=f"/admin/quotes/quote/{quote.pk}/change/",
    )


@on("chat.message")
def chat_message(message_id):
    from apps.chat.models import Message

    message = Message.objects.select_related("conversation__company", "sender").get(pk=message_id)
    conversation = message.conversation
    if message.sender and message.sender.is_staff:
        recipients = [p.user for p in conversation.participants.select_related("user") if not p.user.is_staff]
        url = f"/account/messages/{conversation.uid}"
    else:
        recipients = [p.user for p in conversation.participants.select_related("user") if p.user.is_staff] or []
        url = f"/account/messages/{conversation.uid}"
    recipients = [u for u in recipients if u.pk != message.sender_id]
    notify_users(
        recipients,
        company=conversation.company,
        kind=K.CHAT,
        level=L.INFO,
        title=f"New message · {conversation.subject}",
        body=message.body[:140],
        url=url,
        data={"conversation": str(conversation.uid)},
    )
