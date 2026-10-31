from rest_framework import serializers

from apps.core.serializers import MoneyField

from .models import Order, OrderItem, OrderStatusHistory, ShippingMethod


class ShippingMethodSerializer(serializers.ModelSerializer):
    base_price = MoneyField(read_only=True)
    price_per_kg = MoneyField(read_only=True)

    class Meta:
        model = ShippingMethod
        fields = ("name", "code", "description", "base_price", "price_per_kg", "min_days", "max_days")


class OrderItemSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="uid", read_only=True)
    product_slug = serializers.CharField(source="product.slug", read_only=True, default=None)
    unit_price = MoneyField(read_only=True)
    line_total = MoneyField(read_only=True)

    class Meta:
        model = OrderItem
        fields = (
            "id",
            "product_slug",
            "product_name",
            "sku",
            "fabric_name",
            "image_url",
            "breakdown",
            "quantity",
            "color",
            "customization",
            "artwork",
            "notes",
            "unit_price",
            "line_total",
            "price_breakdown",
        )


class OrderHistorySerializer(serializers.ModelSerializer):
    changed_by = serializers.CharField(source="changed_by.full_name", read_only=True, default="")

    class Meta:
        model = OrderStatusHistory
        fields = ("from_status", "to_status", "note", "changed_by", "created_at")


class OrderListSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="uid", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    placed_by = serializers.CharField(source="placed_by.full_name", read_only=True, default="")
    grand_total = MoneyField(read_only=True)
    amount_paid = MoneyField(read_only=True)
    balance_due = MoneyField(read_only=True)
    item_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Order
        fields = (
            "id",
            "number",
            "status",
            "status_display",
            "payment_status",
            "payment_method",
            "po_number",
            "currency",
            "grand_total",
            "amount_paid",
            "balance_due",
            "total_quantity",
            "item_count",
            "placed_by",
            "estimated_ship_date",
            "tracking_number",
            "created_at",
        )


class OrderDetailSerializer(OrderListSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    history = serializers.SerializerMethodField()
    shipping_method = ShippingMethodSerializer(read_only=True)
    subtotal = MoneyField(read_only=True)
    discount_total = MoneyField(read_only=True)
    shipping_total = MoneyField(read_only=True)
    tax_total = MoneyField(read_only=True)
    approved_by = serializers.CharField(source="approved_by.full_name", read_only=True, default="")
    can_cancel = serializers.SerializerMethodField()
    company = serializers.CharField(source="company.name", read_only=True)

    class Meta(OrderListSerializer.Meta):
        fields = OrderListSerializer.Meta.fields + (
            "company",
            "items",
            "history",
            "shipping_method",
            "subtotal",
            "discount_total",
            "shipping_total",
            "tax_total",
            "shipping_address",
            "billing_address",
            "carrier",
            "tracking_url",
            "customer_notes",
            "requested_delivery_date",
            "due_date",
            "payment_terms",
            "approved_by",
            "approved_at",
            "confirmed_at",
            "shipped_at",
            "delivered_at",
            "cancelled_at",
            "cancel_reason",
            "can_cancel",
            "quote",
        )

    def get_history(self, obj):
        return OrderHistorySerializer([h for h in obj.history.all() if h.is_customer_visible], many=True).data

    def get_can_cancel(self, obj):
        return obj.status in Order.CANCELLABLE_STATUSES


class CheckoutSerializer(serializers.Serializer):
    shipping_address = serializers.UUIDField()
    billing_address = serializers.UUIDField(required=False, allow_null=True)
    shipping_method = serializers.SlugField()
    payment_method = serializers.ChoiceField(choices=Order.PaymentMethod.choices)
    po_number = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    customer_notes = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
    requested_delivery_date = serializers.DateField(required=False, allow_null=True)


class CancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class StaffTransitionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Order.Status.choices)
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    carrier = serializers.CharField(max_length=60, required=False, allow_blank=True)
    tracking_number = serializers.CharField(max_length=100, required=False, allow_blank=True)
    tracking_url = serializers.URLField(required=False, allow_blank=True)
    estimated_ship_date = serializers.DateField(required=False, allow_null=True)
