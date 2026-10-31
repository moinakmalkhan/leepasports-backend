from datetime import timedelta

from celery import shared_task
from django.utils import timezone


@shared_task
def reprice_products_for_fabric(fabric_id: int):
    from apps.pricing.services import base_price_for

    from .models import Product

    for product in Product.objects.filter(base_fabric_id=fabric_id).select_related("base_fabric"):
        price = base_price_for(product)
        if price != product.base_price:
            Product.objects.filter(pk=product.pk).update(base_price=price)


@shared_task
def reprice_all_products():
    from apps.pricing.services import base_price_for

    from .models import Product

    for product in Product.objects.select_related("base_fabric").iterator(chunk_size=200):
        Product.objects.filter(pk=product.pk).update(base_price=base_price_for(product))


@shared_task
def prune_product_views(days: int = 90):
    from .models import ProductView

    ProductView.objects.filter(viewed_at__lt=timezone.now() - timedelta(days=days)).delete()
