from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone


@shared_task
def purge_abandoned_guest_carts():
    from .models import Cart

    cutoff = timezone.now() - timedelta(days=settings.LEEPA["CART_GUEST_TTL_DAYS"])
    Cart.objects.filter(user__isnull=True, updated_at__lt=cutoff).delete()
