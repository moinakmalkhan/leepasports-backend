from rest_framework import serializers

from apps.core.serializers import MoneyField

from ..models import Address, NewsletterSubscriber, User

PK_PROVINCES = [
    "Punjab",
    "Sindh",
    "Khyber Pakhtunkhwa",
    "Balochistan",
    "Islamabad Capital Territory",
    "Gilgit-Baltistan",
    "Azad Kashmir",
]


class UserSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="uid", read_only=True)
    full_name = serializers.CharField(read_only=True)
    has_password = serializers.SerializerMethodField()
    total_spent = MoneyField(read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone",
            "avatar_url",
            "date_of_birth",
            "shop_for",
            "language",
            "is_staff",
            "is_email_verified",
            "auth_provider",
            "marketing_opt_in",
            "notification_preferences",
            "has_password",
            "order_count",
            "total_spent",
            "created_at",
        )
        read_only_fields = ("email", "is_staff", "is_email_verified", "auth_provider", "order_count", "created_at")

    def get_has_password(self, obj) -> bool:
        return obj.has_usable_password()


class AddressSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="uid", read_only=True)

    class Meta:
        model = Address
        fields = (
            "id",
            "label",
            "full_name",
            "phone",
            "line1",
            "line2",
            "city",
            "province",
            "postal_code",
            "country",
            "is_default",
            "created_at",
        )
        read_only_fields = ("created_at",)

    def validate_country(self, value):
        return value.upper()

    def validate_phone(self, value):
        digits = "".join(ch for ch in value if ch.isdigit() or ch == "+")
        if len(digits.lstrip("+")) < 10:
            raise serializers.ValidationError("Enter a valid phone number (e.g. 03001234567).")
        return value


class NewsletterSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsletterSubscriber
        fields = ("email",)
