from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel, UUIDModel


class ShippingMethod(models.Model):
    """Freight options. B2B freight is usually re-quoted; we show an estimate."""

    name = models.CharField(max_length=80)
    code = models.SlugField(max_length=40, unique=True)
    description = models.CharField(max_length=200, blank=True)
    base_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price_per_kg = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    min_days = models.PositiveSmallIntegerField(default=5)
    max_days = models.PositiveSmallIntegerField(default=10)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("sort_order",)

    def __str__(self):
        return self.name

    def estimate(self, weight_kg):
        from apps.core.utils import money

        return money(self.base_price + self.price_per_kg * weight_kg)


class Order(UUIDModel):
    class Status(models.TextChoices):
        PENDING_APPROVAL = "pending_approval", "Pending approval"
        PENDING_PAYMENT = "pending_payment", "Awaiting payment"
        CONFIRMED = "confirmed", "Confirmed"
        IN_PRODUCTION = "in_production", "In production"
        QUALITY_CHECK = "quality_check", "Quality check"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", "Unpaid"
        DEPOSIT_PAID = "deposit_paid", "Deposit paid"
        PAID = "paid", "Paid"
        OVERDUE = "overdue", "Overdue"
        REFUNDED = "refunded", "Refunded"

    class PaymentMethod(models.TextChoices):
        BANK_TRANSFER = "bank_transfer", "Bank transfer / Wire"
        NET_TERMS = "net_terms", "Net terms (invoice)"
        CARD = "card", "Card"

    OPEN_STATUSES = (
        Status.PENDING_APPROVAL,
        Status.PENDING_PAYMENT,
        Status.CONFIRMED,
        Status.IN_PRODUCTION,
        Status.QUALITY_CHECK,
        Status.SHIPPED,
    )
    CANCELLABLE_STATUSES = (Status.PENDING_APPROVAL, Status.PENDING_PAYMENT, Status.CONFIRMED)
    TRANSITIONS = {
        Status.PENDING_APPROVAL: {Status.PENDING_PAYMENT, Status.CONFIRMED, Status.CANCELLED},
        Status.PENDING_PAYMENT: {Status.CONFIRMED, Status.CANCELLED},
        Status.CONFIRMED: {Status.IN_PRODUCTION, Status.CANCELLED},
        Status.IN_PRODUCTION: {Status.QUALITY_CHECK, Status.SHIPPED},
        Status.QUALITY_CHECK: {Status.IN_PRODUCTION, Status.SHIPPED},
        Status.SHIPPED: {Status.DELIVERED},
        Status.DELIVERED: {Status.COMPLETED},
        Status.COMPLETED: set(),
        Status.CANCELLED: set(),
    }

    number = models.CharField(max_length=24, unique=True)
    company = models.ForeignKey("accounts.Company", on_delete=models.PROTECT, related_name="orders")
    placed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="orders")
    quote = models.ForeignKey("quotes.Quote", null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING_PAYMENT)
    payment_status = models.CharField(max_length=14, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID)
    payment_method = models.CharField(max_length=16, choices=PaymentMethod.choices)
    payment_terms = models.CharField(max_length=20, default="prepaid")
    po_number = models.CharField(max_length=64, blank=True, help_text="Buyer's purchase order reference")
    currency = models.CharField(max_length=3, default=settings.DEFAULT_CURRENCY)

    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    shipping_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_quantity = models.PositiveIntegerField(default=0)

    shipping_method = models.ForeignKey(ShippingMethod, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    shipping_address = models.JSONField(default=dict)
    billing_address = models.JSONField(default=dict)
    carrier = models.CharField(max_length=60, blank=True)
    tracking_number = models.CharField(max_length=100, blank=True)
    tracking_url = models.URLField(blank=True)

    customer_notes = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)
    requested_delivery_date = models.DateField(null=True, blank=True)
    estimated_ship_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True, help_text="Invoice due date for net terms")

    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["company", "-created_at"]),
            models.Index(fields=["company", "status"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["payment_status", "due_date"]),
            models.Index(fields=["po_number"]),
        ]

    def __str__(self):
        return self.number

    @property
    def balance_due(self):
        return max(self.grand_total - self.amount_paid, 0)

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES

    def can_transition(self, new_status) -> bool:
        return new_status in self.TRANSITIONS.get(self.status, set())


class OrderItem(UUIDModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("catalog.Product", null=True, on_delete=models.SET_NULL, related_name="order_items")
    fabric = models.ForeignKey("catalog.Fabric", null=True, on_delete=models.SET_NULL, related_name="+")
    # Snapshots: an order must render identically forever, even if the catalog changes.
    product_name = models.CharField(max_length=200)
    sku = models.CharField(max_length=40)
    fabric_name = models.CharField(max_length=140)
    image_url = models.URLField(blank=True)
    breakdown = models.JSONField(default=list)
    quantity = models.PositiveIntegerField()
    color = models.CharField(max_length=40, blank=True)
    customization = models.JSONField(default=dict, blank=True)
    artwork = models.FileField(upload_to="artwork/orders/%Y/%m/", blank=True)
    notes = models.CharField(max_length=500, blank=True)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)
    price_breakdown = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("id",)
        indexes = [models.Index(fields=["product", "-created_at"])]


class OrderStatusHistory(TimeStampedModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="history")
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    note = models.CharField(max_length=500, blank=True)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    is_customer_visible = models.BooleanField(default=True)

    class Meta:
        ordering = ("created_at",)
