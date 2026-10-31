from django.contrib.auth import password_validation
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from ..models import User
from .accounts import UserSerializer


def build_token_pair(user: User) -> dict:
    refresh = RefreshToken.for_user(user)
    refresh["email"] = user.email
    refresh["is_staff"] = user.is_staff
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


class TokenObtainSerializer(TokenObtainPairSerializer):
    default_error_messages = {"no_active_account": "Incorrect email or password."}

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["email"] = user.email
        token["is_staff"] = user.is_staff
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
    password = serializers.CharField(write_only=True, min_length=8, max_length=128)
    first_name = serializers.CharField(max_length=80)
    last_name = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    marketing_opt_in = serializers.BooleanField(required=False, default=True)

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("An account with this email already exists. Try signing in.")
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
    password = serializers.CharField(min_length=8, max_length=128)

    def validate_password(self, value):
        password_validation.validate_password(value)
        return value


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(required=False, allow_blank=True)
    new_password = serializers.CharField(min_length=8, max_length=128)

    def validate(self, attrs):
        user = self.context["request"].user
        if user.has_usable_password() and not user.check_password(attrs.get("current_password", "")):
            raise serializers.ValidationError({"current_password": "Current password is incorrect."})
        password_validation.validate_password(attrs["new_password"], user)
        return attrs


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()
