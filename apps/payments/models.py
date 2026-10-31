from django.conf import settings
from django.db import models

from apps.core.models import UUIDModel


class BankAccount(models.Model):
    """Wire instructions shown to buyers paying by bank transfer."""

    label = models.CharField(max_length=80)
    bank_name = models.CharField(max_length=120)
    account_name = models.CharField(max_length=120)
    account_number = models.CharField(max_length=64)
    iban = models.CharField(max_length=64, blank=True)
    swift = models.CharField(max_length=20, blank=True)
    currency = models.CharField(max_length=3, default="USD")
    branch_address = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.label} ({self.currency})"


class Payment(UUIDModel):
    class Kind(models.TextChoices):
        FULL = "full", "Full payment"
        DEPOSIT = "deposit", "Deposit"
        BALANCE = "balance", "Balance"
        INVOICE = "invoice", "Invoice (net terms)"

    class Status(models.TextChoices):
        PENDING = "pending", "Awaiting payment"
        SUBMITTED = "submitted", "Proof submitted"
        CONFIRMED = "confirmed", "Confirmed"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="payments")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.FULL)
    method = models.CharField(max_length=16)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    reference = models.CharField(max_length=120, blank=True, help_text="Bank reference / transaction id")
    proof = models.FileField(upload_to="payments/proofs/%Y/%m/", blank=True)
    note = models.CharField(max_length=500, blank=True)
    due_date = models.DateField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["order", "status"]), models.Index(fields=["status", "due_date"])]

    def __str__(self):
        return f"{self.order.number} {self.kind} {self.amount} {self.currency}"
