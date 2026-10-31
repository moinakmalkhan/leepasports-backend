import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger("apps.notifications")


def _enrich(context: dict) -> dict:
    """Celery args must be JSON; handlers pass ids and we hydrate models here."""
    ctx = dict(context)
    if "order_id" in ctx:
        from apps.orders.models import Order

        order = Order.objects.select_related("user", "shipping_zone").prefetch_related("items").get(pk=ctx.pop("order_id"))
        ctx.update(order=order, items=list(order.items.all()), address=order.shipping_address)
    if "return_id" in ctx:
        from apps.orders.models import ReturnRequest

        req = ReturnRequest.objects.select_related("order").prefetch_related("items__order_item").get(pk=ctx.pop("return_id"))
        ctx.update(return_request=req, order=req.order, items=list(req.items.all()))
    return ctx


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_email_task(
    self, *, template: str, to: list[str], context: dict, subject: str | None = None, reply_to: list[str] | None = None
):
    """Render `templates/email/<template>.{subject.txt,html,txt}` and send."""
    ctx = {
        **_enrich(context),
        "site_name": settings.SITE_NAME,
        "frontend_url": settings.FRONTEND_URL,
        "support_email": settings.SHOP["SUPPORT_EMAIL"],
        "support_phone": settings.SHOP["SUPPORT_PHONE"],
        **context,
    }
    subject = subject or render_to_string(f"email/{template}.subject.txt", ctx).strip()
    html = render_to_string(f"email/{template}.html", ctx)
    text = render_to_string("email/base.txt", {**ctx, "subject": subject, "html": html})
    message = EmailMultiAlternatives(subject=subject, body=text, to=to, reply_to=reply_to)
    message.attach_alternative(html, "text/html")
    try:
        message.send()
    except Exception as exc:  # pragma: no cover
        logger.warning("Email send failed (%s), retrying", exc)
        raise self.retry(exc=exc)


@shared_task
def dispatch_event(event: str, payload: dict):
    from .events import dispatch

    dispatch(event, payload)
