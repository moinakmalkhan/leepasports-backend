from django.conf import settings
from django.db import models

from apps.core.models import UUIDModel


class Quote(UUIDModel):
    """Request for quotation. Buyers submit their configured cart; sales
    responds with negotiated unit prices; accepting converts it to an order."""

    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        UNDER_REVIEW = "under_review", "Under review"
        QUOTED = "quoted", "Quote ready"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        EXPIRED = "expired", "Expired"
        CONVERTED = "converted", "Converted to order"

    number = models.CharField(max_length=24, unique=True)
    company = models.ForeignKey("accounts.Company", on_delete=models.PROTECT, related_name="quotes")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="quotes")
    handled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    status = models.CharField(max_length=14, choices=Status.choices, default=Status.SUBMITTED)
    currency = models.CharField(max_length=3, default=settings.DEFAULT_CURRENCY)
    requested_total = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="List price total at submission")
    quoted_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    total_quantity = models.PositiveIntegerField(default=0)
    target_budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    delivery_deadline = models.DateField(null=True, blank=True)
    shipping_address = models.JSONField(default=dict, blank=True)
    customer_notes = models.TextField(blank=True)
    response_message = models.TextField(blank=True, help_text="Sales reply shown to the customer")
    internal_notes = models.TextField(blank=True)
    valid_until = models.DateField(null=True, blank=True)
    quoted_at = models.DateTimeField(null=True, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["company", "-created_at"]),
            models.Index(fields=["status", "valid_until"]),
        ]

    def __str__(self):
        return self.number


class QuoteItem(UUIDModel):
    quote = models.ForeignKey(Quote, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("catalog.Product", null=True, on_delete=models.SET_NULL, related_name="+")
    fabric = models.ForeignKey("catalog.Fabric", null=True, on_delete=models.SET_NULL, related_name="+")
    product_name = models.CharField(max_length=200)
    sku = models.CharField(max_length=40)
    fabric_name = models.CharField(max_length=140)
    image_url = models.URLField(blank=True)
    breakdown = models.JSONField(default=list)
    quantity = models.PositiveIntegerField()
    color = models.CharField(max_length=40, blank=True)
    customization = models.JSONField(default=dict, blank=True)
    artwork = models.FileField(upload_to="artwork/quotes/%Y/%m/", blank=True)
    notes = models.CharField(max_length=500, blank=True)
    requested_unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quoted_unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)
    price_breakdown = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("id",)
