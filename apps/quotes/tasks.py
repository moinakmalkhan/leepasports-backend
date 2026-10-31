from celery import shared_task
from django.utils import timezone


@shared_task
def expire_stale_quotes():
    from .models import Quote

    Quote.objects.filter(status=Quote.Status.QUOTED, valid_until__lt=timezone.localdate()).update(status=Quote.Status.EXPIRED)
