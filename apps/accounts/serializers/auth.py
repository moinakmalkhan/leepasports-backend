from django.contrib.auth import password_validation
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from ..models import Company, User
from .accounts import UserSerializer


def _membership_claims(user: User) -> dict:
    membership = user.memberships.select_related("company").filter(is_active=True).order_by("-is_default", "id").first()
    if not membership:
        return {"company_id": None, "role": None}
    return {"company_id": str(membership.company.uid), "role": membership.role}


def build_token_pair(user: User) -> dict:
    refresh = RefreshToken.for_user(user)
    for key, value in {"email": user.email, "is_staff": user.is_staff, **_membership_claims(user)}.items():
        refresh[key] = value
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


class TokenObtainSerializer(TokenObtainPairSerializer):
    """Email + password login returning tokens and the user profile."""

    default_error_messages = {"no_active_account": "Incorrect email or password."}

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["email"] = user.email
        token["is_staff"] = user.is_staff
        for key, value in _membership_claims(user).items():
            token[key] = value
        return token

    def validate(self, attrs):
        attrs["email"] = attrs.get("email", "").lower()
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user, context=self.context).data
        return data


class GoogleLoginSerializer(serializers.Serializer):
    id_token = serializers.CharField()


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=10, max_length=128)
    first_name = serializers.CharField(max_length=80)
    last_name = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    company_name = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    business_type = serializers.ChoiceField(
        choices=Company.BusinessType.choices, required=False, default=Company.BusinessType.CLUB
    )
    country = serializers.CharField(max_length=2, required=False, default="US")

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate_password(self, value):
        password_validation.validate_password(value)
        return value


class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField()


class TokenSerializer(serializers.Serializer):
    token = serializers.CharField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField()
    password = serializers.CharField(min_length=10, max_length=128)

    def validate_password(self, value):
        password_validation.validate_password(value)
        return value


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(required=False, allow_blank=True)
    new_password = serializers.CharField(min_length=10, max_length=128)

    def validate(self, attrs):
        user = self.context["request"].user
        if user.has_usable_password() and not user.check_password(attrs.get("current_password", "")):
            raise serializers.ValidationError({"current_password": "Current password is incorrect."})
        password_validation.validate_password(attrs["new_password"], user)
        return attrs


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()
