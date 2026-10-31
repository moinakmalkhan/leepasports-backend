from rest_framework import serializers

from apps.core.serializers import MoneyField
from apps.pricing.services import fabric_cost

from .models import Fabric, Product, ProductFabricOption, ProductImage, ProductSizeOption, Size, SizeGroup


class CategoryNodeSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.SlugField()
    icon = serializers.CharField(allow_blank=True)
    image = serializers.CharField(allow_null=True)
    description = serializers.CharField(allow_blank=True)
    product_count = serializers.IntegerField()
    depth = serializers.IntegerField()
    children = serializers.ListField(child=serializers.DictField())


class FabricSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="uid", read_only=True)
    price_pkr = MoneyField(read_only=True)

    class Meta:
        model = Fabric
        fields = (
            "id",
            "name",
            "slug",
            "composition",
            "gsm",
            "quality",
            "quality_rank",
            "price_pkr",
            "price_unit",
            "width_inches",
            "description",
            "features",
            "best_for",
            "typical_mills",
            "is_available_in_pakistan",
            "image",
            "swatch_color",
            "price_updated_at",
        )


class ProductImageSerializer(serializers.ModelSerializer):
    url = serializers.ImageField(source="image", read_only=True)

    class Meta:
        model = ProductImage
        fields = ("id", "url", "alt", "is_primary", "width", "height")


class SizeSerializer(serializers.ModelSerializer):
    surcharge_percent = MoneyField(max_digits=5, read_only=True)

    class Meta:
        model = Size
        fields = ("id", "label", "sort_order", "surcharge_percent", "chest_cm", "length_cm")


class SizeGroupSerializer(serializers.ModelSerializer):
    sizes = SizeSerializer(many=True, read_only=True)

    class Meta:
        model = SizeGroup
        fields = ("id", "name", "slug", "sizes")


class ProductCardSerializer(serializers.ModelSerializer):
    """Compact representation for grids, search dropdowns and recommendations."""

    id = serializers.UUIDField(source="uid", read_only=True)
    category = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    image = serializers.SerializerMethodField()
    base_price = MoneyField(read_only=True)
    compare_at_price = MoneyField(read_only=True)
    base_fabric = serializers.CharField(source="base_fabric.name", read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "slug",
            "sku",
            "category",
            "category_name",
            "short_description",
            "image",
            "base_price",
            "compare_at_price",
            "min_order_quantity",
            "lead_time_days",
            "genders",
            "colors",
            "base_fabric",
            "is_featured",
            "is_new",
            "is_customizable",
        )

    def get_image(self, obj):
        image = obj.primary_image
        if not image:
            return None
        request = self.context.get("request")
        url = image.image.url
        return {
            "url": request.build_absolute_uri(url) if request else url,
            "alt": image.alt or obj.name,
            "width": image.width,
            "height": image.height,
        }


class FabricOptionSerializer(serializers.ModelSerializer):
    fabric = FabricSerializer(read_only=True)
    price_adjustment = MoneyField(read_only=True)
    unit_fabric_cost = serializers.SerializerMethodField()

    class Meta:
        model = ProductFabricOption
        fields = ("fabric", "price_adjustment", "is_default", "unit_fabric_cost")

    def get_unit_fabric_cost(self, obj):
        product = self.context.get("product")
        currency = self.context.get("currency")
        if not product:
            return None
        return fabric_cost(obj.fabric, product.fabric_consumption_kg, currency) + obj.price_adjustment


class SizeOptionSerializer(serializers.ModelSerializer):
    size = SizeSerializer(read_only=True)

    class Meta:
        model = ProductSizeOption
        fields = ("gender", "size")


class ProductDetailSerializer(ProductCardSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    fabric_options = serializers.SerializerMethodField()
    size_options = SizeOptionSerializer(many=True, read_only=True)
    size_group = SizeGroupSerializer(read_only=True)
    labor_price = MoneyField(read_only=True)
    volume_tiers = serializers.SerializerMethodField()
    breadcrumbs = serializers.SerializerMethodField()

    class Meta(ProductCardSerializer.Meta):
        fields = ProductCardSerializer.Meta.fields + (
            "description",
            "specifications",
            "tags",
            "images",
            "fabric_options",
            "size_options",
            "size_group",
            "labor_price",
            "fabric_consumption_kg",
            "order_increment",
            "is_made_to_order",
            "stock_quantity",
            "customization_options",
            "volume_tiers",
            "breadcrumbs",
            "meta_title",
            "meta_description",
        )

    def get_fabric_options(self, obj):
        ctx = {**self.context, "product": obj}
        return FabricOptionSerializer(obj.fabric_options.all(), many=True, context=ctx).data

    def get_volume_tiers(self, obj):
        from apps.pricing.services import volume_tiers_for

        return [{"min_quantity": t.min_quantity, "discount_percent": t.discount_percent} for t in volume_tiers_for(obj)]

    def get_breadcrumbs(self, obj):
        from .services import category_breadcrumbs

        return category_breadcrumbs(obj.category)
