from rest_framework import serializers

from apps.catalog.serializers import ProductCardSerializer, VariantSerializer
from apps.core.serializers import MoneyField

from .models import WishlistItem


class CartItemSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="item.uid")
    product = serializers.SerializerMethodField()
    variant = VariantSerializer()
    quantity = serializers.IntegerField(source="item.quantity")
    unit_price = MoneyField()
    line_total = MoneyField()
    available = serializers.IntegerField()
    issue = serializers.CharField(allow_blank=True)

    def get_product(self, obj):
        return ProductCardSerializer(obj.variant.product, context=self.context).data


class CartSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="cart.uid")
    guest_token = serializers.SerializerMethodField()
    items = CartItemSerializer(many=True)
    item_count = serializers.SerializerMethodField()
    quantity = serializers.IntegerField()
    subtotal = MoneyField()
    discount = MoneyField()
    coupon_code = serializers.CharField(allow_blank=True)
    coupon_message = serializers.CharField(allow_blank=True)
    free_shipping = serializers.BooleanField()
    issues = serializers.ListField(child=serializers.CharField())
    notes = serializers.CharField(source="cart.notes", allow_blank=True)

    def get_guest_token(self, obj):
        return obj.cart.guest_token if obj.cart.user_id is None else None

    def get_item_count(self, obj):
        return len(obj.items)


class AddItemSerializer(serializers.Serializer):
    variant = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1, max_value=10, default=1)


class QuantitySerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=0, max_value=10)


class CouponSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=30)
    email = serializers.EmailField(required=False, allow_blank=True)


class WishlistItemSerializer(serializers.ModelSerializer):
    product = ProductCardSerializer(read_only=True)
    variant = VariantSerializer(read_only=True)

    class Meta:
        model = WishlistItem
        fields = ("product", "variant", "added_at")
