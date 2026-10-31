from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.core.exceptions import BusinessError
from apps.core.throttling import AuthBurstRateThrottle, AuthRateThrottle

from . import services
from .models import Address
from .serializers.accounts import PK_PROVINCES, AddressSerializer, NewsletterSerializer, UserSerializer
from .serializers.auth import (
    ChangePasswordSerializer,
    EmailSerializer,
    GoogleLoginSerializer,
    LogoutSerializer,
    PasswordResetConfirmSerializer,
    RegisterSerializer,
    TokenSerializer,
    build_token_pair,
)


class LoginView(TokenObtainPairView):
    throttle_classes = (AuthRateThrottle, AuthBurstRateThrottle)


class RefreshView(TokenRefreshView):
    throttle_classes = ()


class LogoutView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(request=LogoutSerializer, responses={204: None})
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            RefreshToken(serializer.validated_data["refresh"]).blacklist()
        except TokenError:
            pass
        return Response(status=status.HTTP_204_NO_CONTENT)


class RegisterView(APIView):
    permission_classes = (AllowAny,)
    throttle_classes = (AuthRateThrottle, AuthBurstRateThrottle)

    @extend_schema(request=RegisterSerializer)
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from django.utils import translation

        user = services.register_user(**serializer.validated_data, language=translation.get_language() or "")
        return Response({**build_token_pair(user), "user": UserSerializer(user).data}, status=status.HTTP_201_CREATED)


class GoogleLoginView(APIView):
    permission_classes = (AllowAny,)
    throttle_classes = (AuthRateThrottle, AuthBurstRateThrottle)

    @extend_schema(request=GoogleLoginSerializer)
    def post(self, request):
        serializer = GoogleLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from django.utils import translation

        user = services.google_login(serializer.validated_data["id_token"], language=translation.get_language() or "")
        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])
        return Response({**build_token_pair(user), "user": UserSerializer(user).data})


class VerifyEmailView(APIView):
    permission_classes = (AllowAny,)
    throttle_classes = (AuthRateThrottle,)

    @extend_schema(request=TokenSerializer)
    def post(self, request):
        serializer = TokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.verify_email(serializer.validated_data["token"])
        return Response({"detail": "Your email has been verified."})


class ResendVerificationView(APIView):
    permission_classes = (IsAuthenticated,)
    throttle_classes = (AuthRateThrottle,)

    def post(self, request):
        if request.user.is_email_verified:
            raise BusinessError("Your email is already verified.")
        services.send_verification_email(request.user)
        return Response({"detail": "Verification email sent."})


class PasswordResetRequestView(APIView):
    permission_classes = (AllowAny,)
    throttle_classes = (AuthRateThrottle, AuthBurstRateThrottle)

    @extend_schema(request=EmailSerializer)
    def post(self, request):
        serializer = EmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.request_password_reset(serializer.validated_data["email"])
        return Response({"detail": "If an account exists for that email, a reset link has been sent."})


class PasswordResetConfirmView(APIView):
    permission_classes = (AllowAny,)
    throttle_classes = (AuthRateThrottle,)

    @extend_schema(request=PasswordResetConfirmSerializer)
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.reset_password(serializer.validated_data["token"], serializer.validated_data["password"])
        return Response({"detail": "Your password has been updated. You can sign in now."})


class ChangePasswordView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(request=ChangePasswordSerializer)
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        return Response({"detail": "Password changed successfully."})


class MeView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = UserSerializer
    permission_classes = (IsAuthenticated,)

    def get_object(self):
        self.request.user.touch_last_seen()
        return self.request.user

    def perform_update(self, serializer):
        before = serializer.instance.marketing_opt_in
        user = serializer.save()
        # Keep the newsletter list in step with the "drops & offers" toggle.
        if user.marketing_opt_in != before:
            if user.marketing_opt_in:
                services.subscribe_newsletter(user.email, user=user, source="account")
            else:
                services.unsubscribe_newsletter(user.email)

    def perform_destroy(self, instance):
        """Soft-delete: deactivate and scrub personal data (GDPR-style)."""
        instance.is_active = False
        instance.first_name = instance.last_name = instance.phone = instance.avatar_url = ""
        instance.email = f"deleted-{instance.uid}@chobbar.invalid"
        instance.google_sub = None
        instance.set_unusable_password()
        instance.save()


class AddressViewSet(viewsets.ModelViewSet):
    serializer_class = AddressSerializer
    permission_classes = (IsAuthenticated,)
    pagination_class = None
    lookup_field = "uid"

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.instance = services.save_address(self.request.user, dict(serializer.validated_data))

    def perform_update(self, serializer):
        services.save_address(self.request.user, dict(serializer.validated_data), instance=serializer.instance)


class ProvincesView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        return Response(PK_PROVINCES)


class NewsletterView(APIView):
    permission_classes = (AllowAny,)
    throttle_classes = (AuthRateThrottle,)

    @extend_schema(request=NewsletterSerializer)
    def post(self, request):
        serializer = NewsletterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.subscribe_newsletter(
            serializer.validated_data["email"],
            user=request.user if request.user.is_authenticated else None,
            source=request.data.get("source", "footer"),
        )
        return Response({"detail": "You're on the list. Welcome to Chobbar!"}, status=status.HTTP_201_CREATED)

    def delete(self, request):
        email = request.data.get("email") or (request.user.email if request.user.is_authenticated else None)
        if email:
            services.unsubscribe_newsletter(email)
        return Response({"detail": "Unsubscribed."})
