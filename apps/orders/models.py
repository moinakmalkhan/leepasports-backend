from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel, UUIDModel


class ShippingZone(models.Model):
    """Delivery pricing by region. Cities listed on a zone win over province; province wins over the default zone."""

    name = models.CharField(max_length=80)
    provinces = models.JSONField(default=list, blank=True, help_text='["Punjab", "Sindh"]')
    cities = models.JSONField(default=list, blank=True, help_text='["Lahore", "Karachi"] — case-insensitive')
    is_default = models.BooleanField(default=False, help_text="Fallback when no zone matches")
    rate = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    free_over = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, help_text="Free delivery when subtotal ≥ this"
    )
    cod_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0, help_text="Extra charge for cash on delivery")
    min_days = models.PositiveSmallIntegerField(default=2)
    max_days = models.PositiveSmallIntegerField(default=5)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("sort_order",)

    def __str__(self):
        return self.name


class Order(UUIDModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"  # placed, awaiting confirmation (COD call / bank transfer)
        CONFIRMED = "confirmed", "Confirmed"
        PROCESSING = "processing", "Packing"
        SHIPPED = "shipped", "Shipped"
        OUT_FOR_DELIVERY = "out_for_delivery", "Out for delivery"
        DELIVERED = "delivered", "Delivered"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        RETURNED = "returned", "Returned"

    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", "Unpaid"
        PAID = "paid", "Paid"
        COD_PENDING = "cod_pending", "Pay on delivery"
        REFUNDED = "refunded", "Refunded"
        PARTIALLY_REFUNDED = "partially_refunded", "Partially refunded"

    class PaymentMethod(models.TextChoices):
        COD = "cod", "Cash on delivery"
        BANK_TRANSFER = "bank_transfer", "Bank transfer"
        CARD = "card", "Card / wallet"

    OPEN_STATUSES = (Status.PENDING, Status.CONFIRMED, Status.PROCESSING, Status.SHIPPED, Status.OUT_FOR_DELIVERY)
    CANCELLABLE_STATUSES = (Status.PENDING, Status.CONFIRMED)
    TRANSITIONS = {
        Status.PENDING: {Status.CONFIRMED, Status.CANCELLED},
        Status.CONFIRMED: {Status.PROCESSING, Status.CANCELLED},
        Status.PROCESSING: {Status.SHIPPED, Status.CANCELLED},
        Status.SHIPPED: {Status.OUT_FOR_DELIVERY, Status.DELIVERED, Status.RETURNED},
        Status.OUT_FOR_DELIVERY: {Status.DELIVERED, Status.RETURNED},
        Status.DELIVERED: {Status.COMPLETED, Status.RETURNED},
        Status.COMPLETED: {Status.RETURNED},
        Status.CANCELLED: set(),
        Status.RETURNED: set(),
    }

    number = models.CharField(max_length=24, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")
    email = models.EmailField(db_index=True, help_text="Guest or account email at time of order")
    phone = models.CharField(max_length=20)

    status = models.CharField(max_length=18, choices=Status.choices, default=Status.PENDING)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID)
    payment_method = models.CharField(max_length=14, choices=PaymentMethod.choices)
    currency = models.CharField(max_length=3, default=settings.DEFAULT_CURRENCY)

    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    shipping_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cod_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    refunded_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_quantity = models.PositiveIntegerField(default=0)
    coupon_code = models.CharField(max_length=30, blank=True)

    shipping_zone = models.ForeignKey(ShippingZone, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    shipping_address = models.JSONField(default=dict)
    carrier = models.CharField(max_length=60, blank=True)
    tracking_number = models.CharField(max_length=100, blank=True)
    tracking_url = models.URLField(blank=True)
    estimated_delivery = models.DateField(null=True, blank=True)

    customer_notes = models.CharField(max_length=500, blank=True)
    internal_notes = models.TextField(blank=True)
    cancel_reason = models.CharField(max_length=300, blank=True)
    is_gift = models.BooleanField(default=False)
    source = models.CharField(max_length=20, default="web")

    confirmed_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["email", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["payment_status", "payment_method"]),
            models.Index(fields=["phone"]),
        ]

    def __str__(self):
        return self.number

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES

    def can_transition(self, new_status) -> bool:
        return new_status in self.TRANSITIONS.get(self.status, set())

    @property
    def can_return(self) -> bool:
        from datetime import timedelta

        from django.utils import timezone

        if self.status not in (self.Status.DELIVERED, self.Status.COMPLETED) or not self.delivered_at:
            return False
        return timezone.now() <= self.delivered_at + timedelta(days=settings.SHOP["RETURN_WINDOW_DAYS"])


class OrderItem(UUIDModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey("catalog.ProductVariant", null=True, on_delete=models.SET_NULL, related_name="order_items")
    product = models.ForeignKey("catalog.Product", null=True, on_delete=models.SET_NULL, related_name="order_items")
    # Snapshots keep the order readable forever.
    product_name = models.CharField(max_length=200)
    variant_label = models.CharField(max_length=80, blank=True)
    sku = models.CharField(max_length=60)
    image_url = models.URLField(blank=True)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    compare_at_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)
    returned_quantity = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("id",)
        indexes = [models.Index(fields=["product", "-created_at"])]

    def __str__(self):
        return f"{self.product_name} × {self.quantity}"


class OrderStatusHistory(TimeStampedModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="history")
    from_status = models.CharField(max_length=18, blank=True)
    to_status = models.CharField(max_length=18)
    note = models.CharField(max_length=500, blank=True)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    is_customer_visible = models.BooleanField(default=True)

    class Meta:
        ordering = ("created_at",)

    def __str__(self):
        return f"{self.order_id}: {self.from_status} → {self.to_status}"


class ReturnRequest(UUIDModel):
    class Kind(models.TextChoices):
        REFUND = "refund", "Refund"
        EXCHANGE = "exchange", "Exchange (size/colour)"

    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        APPROVED = "approved", "Approved — send it back"
        RECEIVED = "received", "Received"
        COMPLETED = "completed", "Completed"
        REJECTED = "rejected", "Rejected"

    class Reason(models.TextChoices):
        SIZE = "size", "Wrong size / fit"
        DEFECT = "defect", "Damaged or defective"
        NOT_AS_DESCRIBED = "not_as_described", "Not as described"
        CHANGED_MIND = "changed_mind", "Changed my mind"
        WRONG_ITEM = "wrong_item", "Received wrong item"
        OTHER = "other", "Other"

    number = models.CharField(max_length=24, unique=True)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="returns")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="returns")
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.REFUND)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REQUESTED)
    reason = models.CharField(max_length=16, choices=Reason.choices)
    details = models.TextField(max_length=2000, blank=True)
    image = models.ImageField(upload_to="returns/%Y/%m/", blank=True)
    refund_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    refund_method = models.CharField(max_length=30, blank=True, help_text="bank transfer / store credit / original method")
    staff_notes = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["status", "-created_at"]), models.Index(fields=["order"])]

    def __str__(self):
        return self.number


class ReturnItem(models.Model):
    request = models.ForeignKey(ReturnRequest, on_delete=models.CASCADE, related_name="items")
    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, related_name="return_items")
    quantity = models.PositiveIntegerField(default=1)
    exchange_variant = models.ForeignKey(
        "catalog.ProductVariant", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(quantity__gte=1), name="return_item_qty_positive")]

    def __str__(self):
        return f"{self.order_item_id} × {self.quantity}"
