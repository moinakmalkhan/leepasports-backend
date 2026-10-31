from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone


@shared_task
def cancel_unpaid_bank_transfer_orders():
    """Release stock from bank-transfer orders that were never paid."""
    from . import services
    from .models import Order

    cutoff = timezone.now() - timedelta(hours=settings.SHOP["BANK_TRANSFER_HOLD_HOURS"])
    stale = Order.objects.filter(
        status=Order.Status.PENDING,
        payment_method=Order.PaymentMethod.BANK_TRANSFER,
        payment_status=Order.PaymentStatus.UNPAID,
        created_at__lt=cutoff,
    )
    for order in stale:
        services.cancel(order, reason="Payment not received in time", by_customer=False)


@shared_task
def auto_complete_delivered_orders(days: int = 14):
    from . import services
    from .models import Order

    cutoff = timezone.now() - timedelta(days=days)
    for order in Order.objects.filter(status=Order.Status.DELIVERED, delivered_at__lt=cutoff):
        services.transition(order, Order.Status.COMPLETED, note="Auto-completed", customer_visible=False)
