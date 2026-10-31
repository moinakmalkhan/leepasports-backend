"""List variants at or below the low-stock threshold.

python manage.py runscript low_stock_report
"""

from django.conf import settings

from apps.catalog.models import ProductVariant


def run(*args):
    threshold = int(args[0]) if args else settings.SHOP["LOW_STOCK_THRESHOLD"]
    qs = (
        ProductVariant.objects.filter(is_active=True, product__is_active=True, stock__lte=threshold)
        .select_related("product", "color", "size")
        .order_by("stock", "product__name")
    )
    for v in qs:
        print(f"{v.sku:<28} {v.product.name:<32} {v.label:<18} stock={v.stock}")
    print(f"\n{qs.count()} variant(s) at or below {threshold}.")
