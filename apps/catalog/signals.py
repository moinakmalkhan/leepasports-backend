from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.core.cache import invalidate_namespace

from .models import Category, Fabric, Product, ProductFabricOption, ProductImage, ProductSizeOption


def _bump(*args, **kwargs):
    invalidate_namespace("catalog")
    invalidate_namespace("search")


for model in (Category, Product, ProductImage, ProductFabricOption, ProductSizeOption):
    post_save.connect(_bump, sender=model, weak=False, dispatch_uid=f"catalog_bump_save_{model.__name__}")
    post_delete.connect(_bump, sender=model, weak=False, dispatch_uid=f"catalog_bump_delete_{model.__name__}")


@receiver(post_save, sender=Product, dispatch_uid="catalog_product_base_price")
def refresh_product_base_price(sender, instance: Product, **kwargs):
    from apps.pricing.services import base_price_for

    price = base_price_for(instance)
    if price != instance.base_price:
        Product.objects.filter(pk=instance.pk).update(base_price=price)
        instance.base_price = price


@receiver(post_save, sender=Fabric, dispatch_uid="catalog_fabric_reprice")
def reprice_products_on_fabric_change(sender, instance: Fabric, **kwargs):
    """Mill price moved → recompute the denormalised base price of every
    product using this fabric as its base (runs in the background)."""
    from .tasks import reprice_products_for_fabric

    invalidate_namespace("catalog")
    invalidate_namespace("pricing")
    reprice_products_for_fabric.delay(instance.pk)
