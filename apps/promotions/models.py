from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.models import TimeStampedModel


class Coupon(TimeStampedModel):
    class Kind(models.TextChoices):
        PERCENT = "percent", "Percentage off"
        FIXED = "fixed", "Fixed amount off"
        FREE_SHIPPING = "free_shipping", "Free shipping"

    code = models.CharField(max_length=30, unique=True, help_text="Customers type this at checkout (case-insensitive)")
    description = models.CharField(max_length=200, blank=True)
    kind = models.CharField(max_length=14, choices=Kind.choices, default=Kind.PERCENT)
    value = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Percent (e.g. 15) or PKR amount")
    max_discount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, help_text="Cap for percentage coupons"
    )
    min_subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_uses = models.PositiveIntegerField(null=True, blank=True, help_text="Total redemptions allowed (blank = unlimited)")
    max_uses_per_user = models.PositiveIntegerField(default=1)
    first_order_only = models.BooleanField(default=False)
    categories = models.ManyToManyField(
        "catalog.Category", blank=True, related_name="coupons", help_text="Restrict to these categories (and sub-categories)"
    )
    products = models.ManyToManyField("catalog.Product", blank=True, related_name="coupons")
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    uses_count = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["is_active", "starts_at", "ends_at"])]
        constraints = [models.CheckConstraint(condition=Q(value__gte=0), name="coupon_value_non_negative")]

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    @property
    def is_live(self) -> bool:
        now = timezone.now()
        if not self.is_active:
            return False
        if self.starts_at and self.starts_at > now:
            return False
        if self.ends_at and self.ends_at < now:
            return False
        return self.max_uses is None or self.uses_count < self.max_uses


class CouponRedemption(TimeStampedModel):
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name="redemptions")
    order = models.OneToOneField("orders.Order", on_delete=models.CASCADE, related_name="coupon_redemption")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="coupon_redemptions"
    )
    email = models.EmailField(blank=True)
    discount = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        indexes = [models.Index(fields=["coupon", "user"]), models.Index(fields=["coupon", "email"])]

    def __str__(self):
        return f"{self.coupon.code} on {self.order_id}"
