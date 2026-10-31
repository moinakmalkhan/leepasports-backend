"""Recompute every product's denormalised base price.

python manage.py runscript reprice_catalog
"""

from apps.catalog.models import Product
from apps.pricing.services import base_price_for


def run(*args):
    changed = 0
    for product in Product.objects.select_related("base_fabric").iterator(chunk_size=200):
        price = base_price_for(product)
        if price != product.base_price:
            Product.objects.filter(pk=product.pk).update(base_price=price)
            changed += 1
    print(f"Re-priced {changed} product(s).")
