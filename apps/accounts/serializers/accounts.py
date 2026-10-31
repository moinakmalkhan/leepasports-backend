from rest_framework import serializers

from apps.core.serializers import MoneyField

from ..models import Address, Company, CompanyInvitation, CompanyMember, User


class CompanyBriefSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="uid", read_only=True)
    customer_group = serializers.CharField(source="customer_group.name", read_only=True, default=None)

    class Meta:
        model = Company
        fields = (
            "id",
            "name",
            "slug",
            "business_type",
            "country",
            "currency",
            "payment_terms",
            "is_verified",
            "customer_group",
            "approval_threshold",
            "logo",
        )
        read_only_fields = fields


class MembershipSerializer(serializers.ModelSerializer):
    company = CompanyBriefSerializer(read_only=True)

    class Meta:
        model = CompanyMember
        fields = ("company", "role", "is_default", "order_limit")


class UserSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="uid", read_only=True)
    full_name = serializers.CharField(read_only=True)
    memberships = MembershipSerializer(many=True, read_only=True)
    has_password = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone",
            "job_title",
            "avatar_url",
            "is_staff",
            "is_email_verified",
            "auth_provider",
            "marketing_opt_in",
            "notification_preferences",
            "memberships",
            "has_password",
            "created_at",
        )
        read_only_fields = ("email", "is_staff", "is_email_verified", "auth_provider", "created_at")

    def get_has_password(self, obj) -> bool:
        return obj.has_usable_password()


class CompanySerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="uid", read_only=True)
    customer_group = serializers.CharField(source="customer_group.name", read_only=True, default=None)
    credit_limit = MoneyField(read_only=True)
    credit_used = MoneyField(read_only=True)
    credit_available = MoneyField(read_only=True)
    approval_threshold = MoneyField(required=False)
    member_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Company
        fields = (
            "id",
            "name",
            "slug",
            "legal_name",
            "business_type",
            "tax_id",
            "website",
            "email",
            "phone",
            "logo",
            "country",
            "currency",
            "customer_group",
            "payment_terms",
            "credit_limit",
            "credit_used",
            "credit_available",
            "approval_threshold",
            "is_verified",
            "member_count",
            "created_at",
        )
        read_only_fields = ("slug", "payment_terms", "is_verified", "currency", "created_at")


class CompanyMemberSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    user = UserSerializer(read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    order_limit = MoneyField(required=False)

    class Meta:
        model = CompanyMember
        fields = ("id", "email", "full_name", "user", "role", "is_active", "order_limit", "created_at")
        read_only_fields = ("created_at",)


class InvitationSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="uid", read_only=True)
    invited_by = serializers.CharField(source="invited_by.full_name", read_only=True, default="")
    company = serializers.CharField(source="company.name", read_only=True)

    class Meta:
        model = CompanyInvitation
        fields = ("id", "email", "role", "status", "invited_by", "company", "expires_at", "created_at")
        read_only_fields = ("status", "expires_at", "created_at")


class AddressSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="uid", read_only=True)

    class Meta:
        model = Address
        fields = (
            "id",
            "kind",
            "label",
            "contact_name",
            "contact_phone",
            "line1",
            "line2",
            "city",
            "state",
            "postal_code",
            "country",
            "is_default",
            "created_at",
        )
        read_only_fields = ("created_at",)

    def validate_country(self, value):
        return value.upper()
