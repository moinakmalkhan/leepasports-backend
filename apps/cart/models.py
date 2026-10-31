from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import UUIDModel


class Cart(UUIDModel):
    """One open cart per (company, user). Guests get a token-based cart that is
    merged into the company cart on sign-in."""

    company = models.ForeignKey("accounts.Company", null=True, blank=True, on_delete=models.CASCADE, related_name="carts")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="carts")
    guest_token = models.CharField(max_length=64, blank=True, db_index=True)
    currency = models.CharField(max_length=3, default=settings.DEFAULT_CURRENCY)
    notes = models.TextField(blank=True)
    coupon_code = models.CharField(max_length=40, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "user"], condition=Q(user__isnull=False), name="uniq_cart_company_user"),
        ]
        indexes = [models.Index(fields=["updated_at"])]

    def __str__(self):
        return f"Cart {self.uid}"


class CartItem(UUIDModel):
    """A configured line: product + fabric + size/gender quantity matrix.

    `breakdown` is the source of truth for quantities:
      [{"gender": "men", "size_id": 12, "size": "XL", "quantity": 5}, ...]
    Prices are recomputed server-side on every read (never trusted from client).
    """

    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="+")
    fabric = models.ForeignKey("catalog.Fabric", on_delete=models.PROTECT, related_name="+")
    breakdown = models.JSONField(default=list)
    quantity = models.PositiveIntegerField(default=0)
    color = models.CharField(max_length=40, blank=True)
    customization = models.JSONField(default=dict, blank=True)
    artwork = models.FileField(upload_to="artwork/%Y/%m/", blank=True)
    notes = models.CharField(max_length=500, blank=True)
    # Snapshot of the last computed price so list views don't recompute for every row.
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    price_breakdown = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("created_at",)
        indexes = [models.Index(fields=["cart", "product"])]


class SavedList(UUIDModel):
    """Requisition list: reusable product sets ("Season kit", "Academy order")."""

    company = models.ForeignKey("accounts.Company", on_delete=models.CASCADE, related_name="saved_lists")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=300, blank=True)
    is_shared = models.BooleanField(default=True, help_text="Visible to all company members")

    class Meta:
        ordering = ("-updated_at",)
        indexes = [models.Index(fields=["company", "-updated_at"])]

    def __str__(self):
        return self.name


class SavedListItem(UUIDModel):
    saved_list = models.ForeignKey(SavedList, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="+")
    fabric = models.ForeignKey("catalog.Fabric", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    breakdown = models.JSONField(default=list)
    color = models.CharField(max_length=40, blank=True)
    customization = models.JSONField(default=dict, blank=True)
    notes = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ("created_at",)
