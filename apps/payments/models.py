from django.conf import settings
from django.db import models

from apps.core.models import UUIDModel


class BankAccount(models.Model):
    """Shown to customers paying by bank transfer / Raast / wallet."""

    label = models.CharField(max_length=80, help_text="e.g. Meezan Bank, JazzCash")
    bank_name = models.CharField(max_length=120)
    account_name = models.CharField(max_length=120)
    account_number = models.CharField(max_length=64)
    iban = models.CharField(max_length=64, blank=True)
    instructions = models.CharField(max_length=200, blank=True, help_text="e.g. Send the screenshot on WhatsApp")
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("sort_order",)

    def __str__(self):
        return self.label


class Payment(UUIDModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Awaiting payment"
        SUBMITTED = "submitted", "Proof submitted"
        CONFIRMED = "confirmed", "Confirmed"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="payments")
    method = models.CharField(max_length=14)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default=settings.DEFAULT_CURRENCY)
    reference = models.CharField(max_length=120, blank=True, help_text="Transaction id / sender name")
    proof = models.ImageField(upload_to="payments/proofs/%Y/%m/", blank=True)
    provider = models.CharField(max_length=30, blank=True, help_text="Gateway name for card/wallet payments")
    provider_ref = models.CharField(max_length=120, blank=True)
    note = models.CharField(max_length=300, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["order", "status"]), models.Index(fields=["status", "-created_at"])]

    def __str__(self):
        return f"{self.order_id} {self.method} {self.amount}"
