from django.core.cache import cache
from django.db.models.signals import post_delete, post_save

from .models import FAQ, Announcement, Banner, Page


def _clear(*args, **kwargs):
    from django.conf import settings

    cache.delete_many([f"content:storefront:{code}" for code, _ in settings.LANGUAGES])


def _models():
    from apps.orders.models import ShippingZone

    return (Banner, Announcement, Page, FAQ, ShippingZone)


for model in _models():
    post_save.connect(_clear, sender=model, weak=False, dispatch_uid=f"content_clear_{model.__name__}")
    post_delete.connect(_clear, sender=model, weak=False, dispatch_uid=f"content_clear_del_{model.__name__}")
