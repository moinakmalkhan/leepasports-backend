from rest_framework import serializers

from apps.core.serializers import MoneyField

from .models import Order, OrderItem, OrderStatusHistory, ReturnItem, ReturnRequest, ShippingZone


class AddressInputSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=120)
    phone = serializers.CharField(max_length=20)
    line1 = serializers.CharField(max_length=200)
    line2 = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    city = serializers.CharField(max_length=100)
    province = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    postal_code = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    country = serializers.CharField(max_length=2, default="PK")


class CheckoutSerializer(serializers.Serializer):
    email = serializers.EmailField()
    address = AddressInputSerializer()
    payment_method = serializers.ChoiceField(choices=Order.PaymentMethod.choices)
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    save_address = serializers.BooleanField(required=False, default=False)
    is_gift = serializers.BooleanField(required=False, default=False)


class ShippingQuoteSerializer(serializers.Serializer):
    city = serializers.CharField(max_length=100)
    province = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    payment_method = serializers.ChoiceField(choices=Order.PaymentMethod.choices, default=Order.PaymentMethod.COD)


class ShippingZoneSerializer(serializers.ModelSerializer):
    rate = MoneyField(read_only=True)
    free_over = MoneyField(read_only=True)
    cod_fee = MoneyField(read_only=True)

    class Meta:
        model = ShippingZone
        fields = ("name", "rate", "free_over", "cod_fee", "min_days", "max_days")


class OrderItemSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="uid", read_only=True)
    product_slug = serializers.CharField(source="product.slug", read_only=True, default=None)
    unit_price = MoneyField(read_only=True)
    compare_at_price = MoneyField(read_only=True)
    line_total = MoneyField(read_only=True)
    can_review = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = (
            "id",
            "product_slug",
            "product_name",
            "variant_label",
            "sku",
            "image_url",
            "quantity",
            "unit_price",
            "compare_at_price",
            "line_total",
            "returned_quantity",
            "can_review",
        )

    def get_can_review(self, obj):
        return obj.order.status in (Order.Status.DELIVERED, Order.Status.COMPLETED) and not hasattr(obj, "review")


class OrderHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatusHistory
        fields = ("from_status", "to_status", "note", "created_at")


class OrderListSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="uid", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    grand_total = MoneyField(read_only=True)
    item_count = serializers.IntegerField(read_only=True, default=0)
    thumbnails = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id",
            "number",
            "status",
            "status_display",
            "payment_status",
            "payment_method",
            "currency",
            "grand_total",
            "total_quantity",
            "item_count",
            "thumbnails",
            "estimated_delivery",
            "tracking_number",
            "created_at",
        )

    def get_thumbnails(self, obj):
        return (
            [i.image_url for i in obj.items.all()[:3] if i.image_url]
            if hasattr(obj, "_prefetched_objects_cache") and "items" in obj._prefetched_objects_cache
            else []
        )


class ReturnItemSerializer(serializers.ModelSerializer):
    order_item = serializers.UUIDField(source="order_item.uid", read_only=True)
    product_name = serializers.CharField(source="order_item.product_name", read_only=True)
    variant_label = serializers.CharField(source="order_item.variant_label", read_only=True)
    exchange_variant = serializers.CharField(source="exchange_variant.label", read_only=True, default=None)

    class Meta:
        model = ReturnItem
        fields = ("order_item", "product_name", "variant_label", "quantity", "exchange_variant")


class ReturnRequestSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="uid", read_only=True)
    order_number = serializers.CharField(source="order.number", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    reason_display = serializers.CharField(source="get_reason_display", read_only=True)
    items = ReturnItemSerializer(many=True, read_only=True)
    refund_amount = MoneyField(read_only=True)

    class Meta:
        model = ReturnRequest
        fields = (
            "id",
            "number",
            "order_number",
            "kind",
            "status",
            "status_display",
            "reason",
            "reason_display",
            "details",
            "image",
            "items",
            "refund_amount",
            "refund_method",
            "staff_notes",
            "resolved_at",
            "created_at",
        )


class OrderDetailSerializer(OrderListSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    history = serializers.SerializerMethodField()
    subtotal = MoneyField(read_only=True)
    discount_total = MoneyField(read_only=True)
    shipping_total = MoneyField(read_only=True)
    cod_fee = MoneyField(read_only=True)
    refunded_total = MoneyField(read_only=True)
    shipping_zone = ShippingZoneSerializer(read_only=True)
    returns = ReturnRequestSerializer(many=True, read_only=True)
    can_cancel = serializers.SerializerMethodField()
    can_return = serializers.BooleanField(read_only=True)

    class Meta(OrderListSerializer.Meta):
        fields = OrderListSerializer.Meta.fields + (
            "email",
            "phone",
            "items",
            "history",
            "subtotal",
            "discount_total",
            "shipping_total",
            "cod_fee",
            "refunded_total",
            "coupon_code",
            "shipping_zone",
            "shipping_address",
            "carrier",
            "tracking_url",
            "customer_notes",
            "is_gift",
            "cancel_reason",
            "confirmed_at",
            "shipped_at",
            "delivered_at",
            "cancelled_at",
            "paid_at",
            "returns",
            "can_cancel",
            "can_return",
        )

    def get_history(self, obj):
        return OrderHistorySerializer([h for h in obj.history.all() if h.is_customer_visible], many=True).data

    def get_can_cancel(self, obj):
        return obj.status in Order.CANCELLABLE_STATUSES


class CancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class ReturnItemInputSerializer(serializers.Serializer):
    order_item = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1, default=1)
    exchange_variant = serializers.UUIDField(required=False, allow_null=True)


class ReturnRequestInputSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=ReturnRequest.Kind.choices, default=ReturnRequest.Kind.REFUND)
    reason = serializers.ChoiceField(choices=ReturnRequest.Reason.choices)
    details = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
    items = ReturnItemInputSerializer(many=True, allow_empty=False)
    image = serializers.ImageField(required=False, allow_null=True)


class StaffTransitionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Order.Status.choices)
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    carrier = serializers.CharField(max_length=60, required=False, allow_blank=True)
    tracking_number = serializers.CharField(max_length=100, required=False, allow_blank=True)
    tracking_url = serializers.URLField(required=False, allow_blank=True)
    estimated_delivery = serializers.DateField(required=False, allow_null=True)
