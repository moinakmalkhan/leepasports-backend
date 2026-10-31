from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone


@shared_task
def prune_product_views(days: int = 90):
    from .models import ProductView

    ProductView.objects.filter(viewed_at__lt=timezone.now() - timedelta(days=days)).delete()


@shared_task
def notify_back_in_stock(variant_id: int):
    from apps.notifications.tasks import send_email_task

    from .models import StockAlert

    alerts = StockAlert.objects.filter(variant_id=variant_id, notified_at__isnull=True).select_related("variant__product")
    for alert in alerts:
        product = alert.variant.product
        send_email_task.delay(
            template="back_in_stock",
            to=[alert.email],
            context={
                "product": product.name,
                "variant": alert.variant.label,
                "url": f"{settings.FRONTEND_URL}/products/{product.slug}",
            },
        )
    alerts.update(notified_at=timezone.now())
