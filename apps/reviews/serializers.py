from rest_framework import serializers

from .models import Review


class ReviewSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="uid", read_only=True)
    author = serializers.SerializerMethodField()
    product_slug = serializers.CharField(source="product.slug", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = Review
        fields = (
            "id",
            "product_slug",
            "product_name",
            "author",
            "rating",
            "title",
            "body",
            "size_purchased",
            "fit",
            "image",
            "status",
            "is_verified_purchase",
            "helpful_count",
            "staff_reply",
            "replied_at",
            "created_at",
        )
        read_only_fields = ("status", "is_verified_purchase", "helpful_count", "staff_reply", "replied_at", "created_at")

    def get_author(self, obj):
        name = obj.user.first_name or obj.user.email.split("@")[0]
        initial = (obj.user.last_name[:1] + ".") if obj.user.last_name else ""
        return {"name": f"{name} {initial}".strip(), "avatar_url": obj.user.avatar_url}


class ReviewCreateSerializer(serializers.Serializer):
    product = serializers.SlugField()
    rating = serializers.IntegerField(min_value=1, max_value=5)
    title = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    body = serializers.CharField(max_length=3000, required=False, allow_blank=True, default="")
    size_purchased = serializers.CharField(max_length=12, required=False, allow_blank=True, default="")
    fit = serializers.ChoiceField(choices=["small", "true", "large", ""], required=False, default="")
    image = serializers.ImageField(required=False, allow_null=True)
