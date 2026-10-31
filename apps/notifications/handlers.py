"""Who hears about what — the whole communication policy in one file."""

from django.conf import settings

from .events import on
from .models import Notification
from .services import notify_staff, notify_users
from .tasks import send_email_task

L = Notification.Level
K = Notification.Kind


def _order(order_id):
    from apps.orders.models import Order

    return Order.objects.select_related("user").prefetch_related("items").get(pk=order_id)


def _order_url(order):
    return f"/account/orders/{order.uid}" if order.user_id else f"/track?number={order.number}&contact={order.email}"


@on("user.registered")
def user_registered(user_id):
    from apps.accounts.models import User

    user = User.objects.get(pk=user_id)
    notify_users(
        [user],
        kind=K.ACCOUNT,
        level=L.SUCCESS,
        title=f"Welcome to Chobbar, {user.first_name or 'friend'}!",
        body="Verify your email to unlock order tracking, wishlists and faster checkout.",
        url="/account",
    )


@on("order.placed")
def order_placed(order_id):
    order = _order(order_id)
    send_email_task.delay(
        template="order_confirmation",
        to=[order.email],
        context={
            "order_id": order.pk,
            "name": order.shipping_address.get("full_name", ""),
            "url": f"{settings.FRONTEND_URL}{_order_url(order)}",
        },
    )
    if order.user_id:
        notify_users(
            [order.user],
            kind=K.ORDER,
            level=L.SUCCESS,
            title=f"Order {order.number} placed",
            body=f"{order.total_quantity} item(s) · Rs {order.grand_total:,.0f} · {order.get_payment_method_display()}",
            url=_order_url(order),
        )
    notify_staff(
        event="order.placed",
        subject=f"New order {order.number} — Rs {order.grand_total:,.0f}",
        context={
            "customer": order.shipping_address.get("full_name", order.email),
            "city": order.shipping_address.get("city", ""),
            "payment": order.get_payment_method_display(),
            "items": order.total_quantity,
            "summary": f"{order.get_payment_method_display()} · {order.shipping_address.get('city', '')}",
        },
        url=f"/admin/orders/order/{order.pk}/change/",
    )


STATUS_COPY = {
    "confirmed": ("Order confirmed", "We've confirmed your order and are getting it ready.", L.SUCCESS),
    "processing": ("Being packed", "Your order is being packed at our Sialkot studio.", L.INFO),
    "shipped": ("Shipped", "Your parcel is on its way.", L.SUCCESS),
    "out_for_delivery": ("Out for delivery", "The rider has your parcel — keep your phone handy.", L.INFO),
    "delivered": ("Delivered", "Enjoy! Tell us how it fits with a quick review.", L.SUCCESS),
    "completed": ("Completed", "Thanks for shopping with Chobbar.", L.SUCCESS),
    "cancelled": ("Cancelled", "Your order was cancelled.", L.WARNING),
    "returned": ("Returned", "Your return has been processed.", L.INFO),
}


@on("order.status_changed")
def order_status_changed(order_id, from_status, to_status):
    order = _order(order_id)
    title, body, level = STATUS_COPY.get(to_status, (to_status.replace("_", " ").title(), "", L.INFO))
    if order.user_id:
        notify_users([order.user], kind=K.ORDER, level=level, title=f"{order.number}: {title}", body=body, url=_order_url(order))
    if to_status in ("confirmed", "shipped", "out_for_delivery", "delivered", "cancelled"):
        send_email_task.delay(
            template="order_status",
            to=[order.email],
            context={
                "order_id": order.pk,
                "name": order.shipping_address.get("full_name", ""),
                "title": title,
                "body": body,
                "status": to_status,
                "url": f"{settings.FRONTEND_URL}{_order_url(order)}",
            },
        )


@on("order.paid")
def order_paid(order_id):
    order = _order(order_id)
    if order.user_id:
        notify_users(
            [order.user],
            kind=K.PAYMENT,
            level=L.SUCCESS,
            title=f"Payment received for {order.number}",
            body=f"Rs {order.grand_total:,.0f} confirmed. We'll ship it shortly.",
            url=_order_url(order),
        )


@on("payment.submitted")
def payment_submitted(payment_id):
    from apps.payments.models import Payment

    payment = Payment.objects.select_related("order").get(pk=payment_id)
    notify_staff(
        event="payment.submitted",
        subject=f"Payment proof for {payment.order.number}",
        context={"amount": f"Rs {payment.amount:,.0f}", "reference": payment.reference, "summary": payment.reference},
        url=f"/admin/payments/payment/{payment.pk}/change/",
    )
    if payment.order.user_id:
        notify_users(
            [payment.order.user],
            kind=K.PAYMENT,
            level=L.INFO,
            title=f"Receipt received for {payment.order.number}",
            body="We'll confirm it within a few hours and start packing.",
            url=_order_url(payment.order),
        )


@on("return.requested")
def return_requested(return_id):
    from apps.orders.models import ReturnRequest

    req = ReturnRequest.objects.select_related("order__user").get(pk=return_id)
    notify_staff(
        event="return.requested",
        subject=f"{req.get_kind_display()} request {req.number} for {req.order.number}",
        context={
            "reason": req.get_reason_display(),
            "refund": f"Rs {req.refund_amount:,.0f}",
            "summary": req.get_reason_display(),
        },
        url=f"/admin/orders/returnrequest/{req.pk}/change/",
    )
    if req.order.user_id:
        notify_users(
            [req.order.user],
            kind=K.RETURN,
            level=L.INFO,
            title=f"{req.get_kind_display()} request received",
            body=f"{req.number} — we'll review it within 1 business day.",
            url=f"/account/orders/{req.order.uid}",
        )
    send_email_task.delay(
        template="return_update",
        to=[req.order.email],
        context={"return_id": req.pk, "url": f"{settings.FRONTEND_URL}/account/orders/{req.order.uid}"},
    )


@on("return.updated")
def return_updated(return_id):
    from apps.orders.models import ReturnRequest

    req = ReturnRequest.objects.select_related("order__user").get(pk=return_id)
    copy = {
        "approved": (
            "Return approved",
            "Pack the item in its original condition; our rider will collect it or we'll send pickup details.",
            L.SUCCESS,
        ),
        "received": ("Return received", "We've got your parcel and are checking it.", L.INFO),
        "completed": (
            "Return completed",
            f"Rs {req.refund_amount:,.0f} refunded via {req.refund_method or 'your original method'}."
            if req.kind == "refund"
            else "Your exchange is on its way.",
            L.SUCCESS,
        ),
        "rejected": ("Return not accepted", req.staff_notes or "Please contact support for details.", L.WARNING),
    }
    title, body, level = copy.get(req.status, (req.get_status_display(), "", L.INFO))
    if req.order.user_id:
        notify_users(
            [req.order.user],
            kind=K.RETURN,
            level=level,
            title=f"{req.number}: {title}",
            body=body,
            url=f"/account/orders/{req.order.uid}",
        )
    send_email_task.delay(
        template="return_update",
        to=[req.order.email],
        context={"return_id": req.pk, "url": f"{settings.FRONTEND_URL}/account/orders/{req.order.uid}"},
    )


@on("review.created")
def review_created(review_id):
    from apps.reviews.models import Review

    review = Review.objects.select_related("product", "user").get(pk=review_id)
    if review.status == Review.Status.PENDING:
        notify_staff(
            event="review.created",
            subject=f"Review awaiting moderation: {review.product.name}",
            context={"rating": f"{review.rating}★", "by": review.user.email, "summary": review.title or review.body[:80]},
            url=f"/admin/reviews/review/{review.pk}/change/",
        )
    notify_users(
        [review.user],
        kind=K.REVIEW,
        level=L.SUCCESS,
        title="Thanks for your review!",
        body="It's live." if review.status == Review.Status.APPROVED else "It will appear once approved.",
        url=f"/products/{review.product.slug}",
    )


@on("chat.message")
def chat_message(message_id):
    from apps.chat.models import Message

    message = Message.objects.select_related("conversation", "sender").get(pk=message_id)
    conversation = message.conversation
    participants = [p.user for p in conversation.participants.select_related("user")]
    if message.sender and message.sender.is_staff:
        recipients = [u for u in participants if not u.is_staff]
    else:
        recipients = [u for u in participants if u.is_staff]
    recipients = [u for u in recipients if u.pk != message.sender_id]
    notify_users(
        recipients,
        kind=K.CHAT,
        level=L.INFO,
        title=f"New message · {conversation.subject}",
        body=message.body[:140],
        url=f"/account/messages/{conversation.uid}",
        data={"conversation": str(conversation.uid)},
    )
