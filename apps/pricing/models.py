from django.conf import settings
from django.db import models
from django.db.models import Q
from django_extensions.db.fields import AutoSlugField

from apps.core.models import TimeStampedModel


class CustomerGroup(TimeStampedModel):
    """Tiered customer segments (Retail club, Distributor, Key account...)."""

    name = models.CharField(max_length=80, unique=True)
    slug = AutoSlugField(populate_from="name", max_length=80, unique=True)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    description = models.CharField(max_length=200, blank=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ("discount_percent",)

    def __str__(self):
        return f"{self.name} (-{self.discount_percent}%)"


class ExchangeRate(TimeStampedModel):
    """How many PKR one unit of `currency` buys. Fabric cost (PKR/kg) is divided
    by this to reach the selling currency."""

    currency = models.CharField(max_length=3, unique=True)
    pkr_per_unit = models.DecimalField(max_digits=10, decimal_places=4)
    source = models.CharField(max_length=60, blank=True, default="manual")

    def __str__(self):
        return f"1 {self.currency} = {self.pkr_per_unit} PKR"


class VolumeTier(models.Model):
    """Quantity-break discounts. `product=NULL` rows are the global ladder;
    product-specific rows override it entirely."""

    product = models.ForeignKey("catalog.Product", null=True, blank=True, on_delete=models.CASCADE, related_name="volume_tiers")
    min_quantity = models.PositiveIntegerField()
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        ordering = ("min_quantity",)
        constraints = [
            models.UniqueConstraint(fields=["product", "min_quantity"], name="uniq_tier_product_qty"),
            models.UniqueConstraint(fields=["min_quantity"], condition=Q(product__isnull=True), name="uniq_global_tier_qty"),
        ]
        indexes = [models.Index(fields=["product", "min_quantity"])]

    def __str__(self):
        scope = self.product.sku if self.product_id else "global"
        return f"{scope}: {self.min_quantity}+ → -{self.discount_percent}%"


class PriceListItem(TimeStampedModel):
    """Contract / negotiated unit price for a company (or whole group)."""

    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="price_list_items")
    company = models.ForeignKey(
        "accounts.Company", null=True, blank=True, on_delete=models.CASCADE, related_name="price_list_items"
    )
    customer_group = models.ForeignKey(
        CustomerGroup, null=True, blank=True, on_delete=models.CASCADE, related_name="price_list_items"
    )
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default=settings.DEFAULT_CURRENCY)
    min_quantity = models.PositiveIntegerField(default=1)
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(company__isnull=False) | Q(customer_group__isnull=False), name="pricelist_has_target"
            )
        ]
        indexes = [
            models.Index(fields=["company", "product", "is_active"]),
            models.Index(fields=["customer_group", "product", "is_active"]),
        ]

    def __str__(self):
        target = self.company or self.customer_group
        return f"{self.product.sku} for {target}: {self.unit_price}"
