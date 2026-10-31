from rest_framework import serializers

from apps.core.serializers import MoneyField
from apps.orders.models import Order

from .models import Quote, QuoteItem


class QuoteItemSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="uid", read_only=True)
    product_slug = serializers.CharField(source="product.slug", read_only=True, default=None)
    requested_unit_price = MoneyField(read_only=True)
    quoted_unit_price = MoneyField(read_only=True)
    line_total = MoneyField(read_only=True)

    class Meta:
        model = QuoteItem
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
            "requested_unit_price",
            "quoted_unit_price",
            "line_total",
        )


class QuoteListSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="uid", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    requested_by = serializers.CharField(source="requested_by.full_name", read_only=True, default="")
    requested_total = MoneyField(read_only=True)
    quoted_total = MoneyField(read_only=True)
    item_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Quote
        fields = (
            "id",
            "number",
            "status",
            "status_display",
            "currency",
            "requested_total",
            "quoted_total",
            "total_quantity",
            "item_count",
            "requested_by",
            "valid_until",
            "delivery_deadline",
            "created_at",
            "quoted_at",
        )


class QuoteDetailSerializer(QuoteListSerializer):
    items = QuoteItemSerializer(many=True, read_only=True)
    target_budget = MoneyField(read_only=True)
    handled_by = serializers.CharField(source="handled_by.full_name", read_only=True, default="")
    orders = serializers.SlugRelatedField(slug_field="uid", many=True, read_only=True)
    company = serializers.CharField(source="company.name", read_only=True)

    class Meta(QuoteListSerializer.Meta):
        fields = QuoteListSerializer.Meta.fields + (
            "company",
            "items",
            "target_budget",
            "shipping_address",
            "customer_notes",
            "response_message",
            "handled_by",
            "orders",
        )


class QuoteRequestSerializer(serializers.Serializer):
    customer_notes = serializers.CharField(max_length=3000, required=False, allow_blank=True, default="")
    target_budget = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    delivery_deadline = serializers.DateField(required=False, allow_null=True)
    shipping_address = serializers.UUIDField(required=False, allow_null=True)


class QuoteAcceptSerializer(serializers.Serializer):
    shipping_address = serializers.UUIDField()
    payment_method = serializers.ChoiceField(choices=Order.PaymentMethod.choices)
    po_number = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")


class QuoteRespondSerializer(serializers.Serializer):
    item_prices = serializers.DictField(child=serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0))
    message = serializers.CharField(max_length=3000, required=False, allow_blank=True, default="")
    valid_days = serializers.IntegerField(min_value=1, max_value=120, required=False)
    internal_notes = serializers.CharField(max_length=3000, required=False, allow_blank=True, default="")
