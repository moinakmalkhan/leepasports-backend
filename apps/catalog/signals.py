from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.core.cache import invalidate_namespace

from .models import Category, Collection, Product, ProductImage, ProductVariant


def _bump(*args, **kwargs):
    invalidate_namespace("catalog")
    invalidate_namespace("search")


for model in (Category, Collection, Product, ProductImage, ProductVariant):
    post_save.connect(_bump, sender=model, weak=False, dispatch_uid=f"catalog_bump_save_{model.__name__}")
    post_delete.connect(_bump, sender=model, weak=False, dispatch_uid=f"catalog_bump_delete_{model.__name__}")


@receiver(post_save, sender=ProductVariant, dispatch_uid="catalog_variant_total_stock")
@receiver(post_delete, sender=ProductVariant, dispatch_uid="catalog_variant_total_stock_del")
def keep_total_stock(sender, instance: ProductVariant, **kwargs):
    from .services import refresh_total_stock

    refresh_total_stock(instance.product_id)
