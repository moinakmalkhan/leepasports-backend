from rest_framework import serializers

from apps.core.serializers import MoneyField
from apps.core.translation import TranslatedSerializerMixin

from .models import Collection, Product, ProductImage, ProductVariant, Size, SizeGroup, StockAlert


class CategoryNodeSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.SlugField()
    icon = serializers.CharField(allow_blank=True)
    image = serializers.CharField(allow_null=True)
    description = serializers.CharField(allow_blank=True)
    product_count = serializers.IntegerField()
    depth = serializers.IntegerField()
    show_in_menu = serializers.BooleanField()
    children = serializers.ListField(child=serializers.DictField())


class CollectionSerializer(TranslatedSerializerMixin, serializers.ModelSerializer):
    id = serializers.UUIDField(source="uid", read_only=True)
    product_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Collection
        fields = ("id", "name", "slug", "tagline", "description", "image", "is_featured", "product_count", "starts_at", "ends_at")
        translated_fields = ("name", "tagline", "description")


class ProductImageSerializer(serializers.ModelSerializer):
    url = serializers.ImageField(source="image", read_only=True)
    color = serializers.SlugRelatedField(slug_field="slug", read_only=True)

    class Meta:
        model = ProductImage
        fields = ("id", "url", "alt", "color", "is_primary", "width", "height")


class SizeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Size
        fields = ("id", "label", "sort_order")


class SizeGroupSerializer(serializers.ModelSerializer):
    sizes = SizeSerializer(many=True, read_only=True)

    class Meta:
        model = SizeGroup
        fields = ("id", "name", "slug", "sizes", "guide")


class VariantSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="uid", read_only=True)
    color = serializers.SerializerMethodField()
    size = serializers.CharField(source="size.label", read_only=True, default=None)
    size_id = serializers.IntegerField(read_only=True)
    price = MoneyField(read_only=True)
    label = serializers.CharField(read_only=True)
    in_stock = serializers.BooleanField(read_only=True)
    low_stock = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariant
        fields = ("id", "sku", "color", "size", "size_id", "price", "stock", "in_stock", "low_stock", "label")

    def get_color(self, obj):
        from apps.core.i18n import translate

        return {"name": translate(obj.color, "name"), "slug": obj.color.slug, "hex": obj.color.hex} if obj.color_id else None

    def get_low_stock(self, obj):
        from django.conf import settings

        return 0 < obj.stock <= settings.SHOP["LOW_STOCK_THRESHOLD"]


class ProductCardSerializer(TranslatedSerializerMixin, serializers.ModelSerializer):
    """Grid / search / recommendation card."""

    id = serializers.UUIDField(source="uid", read_only=True)
    category = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    category_name = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    hover_image = serializers.SerializerMethodField()
    price = MoneyField(read_only=True)
    compare_at_price = MoneyField(read_only=True)
    discount_percent = serializers.IntegerField(read_only=True)
    is_on_sale = serializers.BooleanField(read_only=True)
    in_stock = serializers.BooleanField(read_only=True)
    rating_avg = serializers.DecimalField(max_digits=3, decimal_places=2, coerce_to_string=False, read_only=True)
    colors = serializers.SerializerMethodField()
    sizes = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "slug",
            "sku",
            "brand",
            "gender",
            "category",
            "category_name",
            "short_description",
            "image",
            "hover_image",
            "price",
            "compare_at_price",
            "discount_percent",
            "is_on_sale",
            "in_stock",
            "rating_avg",
            "rating_count",
            "colors",
            "sizes",
            "is_featured",
            "is_new",
        )
        translated_fields = ("name", "short_description")

    def get_category_name(self, obj):
        from apps.core.i18n import translate

        return translate(obj.category, "name")

    def _img(self, image, obj):
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

    def get_image(self, obj):
        return self._img(obj.primary_image, obj)

    def get_hover_image(self, obj):
        images = getattr(obj, "all_images", None) or []
        return self._img(images[1], obj) if len(images) > 1 else None

    def get_colors(self, obj):
        seen = {}
        for v in getattr(obj, "active_variants", []):
            if v.color_id and v.color.slug not in seen:
                from apps.core.i18n import translate

                seen[v.color.slug] = {"name": translate(v.color, "name"), "slug": v.color.slug, "hex": v.color.hex}
        return list(seen.values())

    def get_sizes(self, obj):
        labels = []
        for v in sorted(getattr(obj, "active_variants", []), key=lambda v: v.size.sort_order if v.size_id else 0):
            if v.size_id and v.size.label not in labels and v.stock > 0:
                labels.append(v.size.label)
        return labels


class ProductDetailSerializer(ProductCardSerializer):
    images = ProductImageSerializer(source="all_images", many=True, read_only=True)
    variants = VariantSerializer(source="active_variants", many=True, read_only=True)
    size_group = SizeGroupSerializer(read_only=True)
    collections = CollectionSerializer(many=True, read_only=True)
    breadcrumbs = serializers.SerializerMethodField()

    class Meta(ProductCardSerializer.Meta):
        fields = ProductCardSerializer.Meta.fields + (
            "description",
            "material",
            "care_instructions",
            "specifications",
            "tags",
            "images",
            "variants",
            "size_group",
            "collections",
            "weight_grams",
            "total_stock",
            "breadcrumbs",
            "meta_title",
            "meta_description",
        )
        translated_fields = (
            "name",
            "short_description",
            "description",
            "material",
            "care_instructions",
            "meta_title",
            "meta_description",
        )

    def get_breadcrumbs(self, obj):
        from .services import category_breadcrumbs

        return category_breadcrumbs(obj.category)


class StockAlertSerializer(serializers.ModelSerializer):
    variant = serializers.SlugRelatedField(slug_field="uid", queryset=ProductVariant.objects.filter(is_active=True))

    class Meta:
        model = StockAlert
        fields = ("variant", "email")
