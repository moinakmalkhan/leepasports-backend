from rest_framework import serializers

from apps.catalog.models import Gender
from apps.catalog.serializers import ProductCardSerializer
from apps.core.serializers import MoneyField

from .models import Cart, CartItem, SavedList, SavedListItem


class BreakdownInputSerializer(serializers.Serializer):
    gender = serializers.ChoiceField(choices=Gender.choices)
    size_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=0, max_value=100000)


class CartItemWriteSerializer(serializers.Serializer):
    product = serializers.SlugField()
    fabric = serializers.SlugField(required=False, allow_null=True)
    breakdown = BreakdownInputSerializer(many=True, allow_empty=False)
    color = serializers.CharField(max_length=40, required=False, allow_blank=True)
    customization = serializers.JSONField(required=False)
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True)
    artwork = serializers.FileField(required=False, allow_null=True)

    def validate_customization(self, value):
        if value is not None and not isinstance(value, dict):
            raise serializers.ValidationError("Customization must be an object.")
        return value or {}

    def validate_artwork(self, value):
        if value and value.size > 15 * 1024 * 1024:
            raise serializers.ValidationError("Artwork must be under 15 MB.")
        allowed = {"image/png", "image/jpeg", "image/svg+xml", "application/pdf", "application/postscript", "image/webp"}
        if value and getattr(value, "content_type", None) not in allowed:
            raise serializers.ValidationError("Upload PNG, JPG, SVG, WEBP, PDF or AI/EPS files.")
        return value


class CartItemUpdateSerializer(CartItemWriteSerializer):
    product = None
    breakdown = BreakdownInputSerializer(many=True, required=False)


class CartItemSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="uid", read_only=True)
    product = ProductCardSerializer(read_only=True)
    fabric = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    fabric_name = serializers.CharField(source="fabric.name", read_only=True)
    unit_price = MoneyField(read_only=True)
    line_total = MoneyField(read_only=True)

    class Meta:
        model = CartItem
        fields = (
            "id",
            "product",
            "fabric",
            "fabric_name",
            "breakdown",
            "quantity",
            "color",
            "customization",
            "artwork",
            "notes",
            "unit_price",
            "line_total",
            "price_breakdown",
            "updated_at",
        )


class CartSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="cart.uid")
    guest_token = serializers.SerializerMethodField()
    currency = serializers.CharField(source="cart.currency")
    items = CartItemSerializer(many=True)
    item_count = serializers.IntegerField()
    quantity = serializers.IntegerField()
    subtotal = MoneyField()
    savings = MoneyField()
    notes = serializers.CharField(source="cart.notes")

    def get_guest_token(self, obj):
        cart: Cart = obj["cart"]
        return cart.guest_token if cart.user_id is None else None


class SavedListItemSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="uid", read_only=True)
    product = ProductCardSerializer(read_only=True)
    fabric = serializers.SlugRelatedField(slug_field="slug", read_only=True)

    class Meta:
        model = SavedListItem
        fields = ("id", "product", "fabric", "breakdown", "color", "customization", "notes")


class SavedListSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="uid", read_only=True)
    items = SavedListItemSerializer(many=True, read_only=True)
    item_count = serializers.IntegerField(read_only=True, default=0)
    created_by = serializers.CharField(source="created_by.full_name", read_only=True, default="")

    class Meta:
        model = SavedList
        fields = ("id", "name", "description", "is_shared", "created_by", "item_count", "items", "updated_at")
        read_only_fields = ("updated_at",)
