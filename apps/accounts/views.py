from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.core.exceptions import BusinessError
from apps.core.mixins import CompanyContextMixin
from apps.core.pagination import SmallPagination
from apps.core.permissions import CompanyRolePermission, HasCompany
from apps.core.throttling import AuthBurstRateThrottle, AuthRateThrottle

from . import services
from .models import Address, Company, CompanyInvitation, CompanyMember
from .serializers.accounts import (
    AddressSerializer,
    CompanyMemberSerializer,
    CompanySerializer,
    InvitationSerializer,
    UserSerializer,
)
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

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class LoginView(TokenObtainPairView):
    throttle_classes = (AuthRateThrottle, AuthBurstRateThrottle)


class RefreshView(TokenRefreshView):
    throttle_classes = ()


class LogoutView(APIView):
    """Blacklist the refresh token so it cannot be reused after logout."""

    permission_classes = (IsAuthenticated,)

    @extend_schema(request=LogoutSerializer, responses={204: None})
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            RefreshToken(serializer.validated_data["refresh"]).blacklist()
        except TokenError:
            pass  # Already expired/blacklisted — logout is idempotent.
        return Response(status=status.HTTP_204_NO_CONTENT)


class RegisterView(APIView):
    permission_classes = (AllowAny,)
    throttle_classes = (AuthRateThrottle, AuthBurstRateThrottle)

    @extend_schema(request=RegisterSerializer)
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.register_user(**serializer.validated_data)
        return Response({**build_token_pair(user), "user": UserSerializer(user).data}, status=status.HTTP_201_CREATED)


class GoogleLoginView(APIView):
    permission_classes = (AllowAny,)
    throttle_classes = (AuthRateThrottle, AuthBurstRateThrottle)

    @extend_schema(request=GoogleLoginSerializer)
    def post(self, request):
        serializer = GoogleLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.google_login(serializer.validated_data["id_token"])
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


# ---------------------------------------------------------------------------
# Profile & company
# ---------------------------------------------------------------------------


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = (IsAuthenticated,)

    def get_object(self):
        self.request.user.touch_last_seen()
        return self.request.user

    def get_queryset(self):  # pragma: no cover - required by generics
        return type(self.request.user).objects.none()


class CompanyViewSet(CompanyContextMixin, viewsets.GenericViewSet):
    """`/accounts/company/` – the acting company. Create one if the user has none."""

    serializer_class = CompanySerializer
    permission_classes = (IsAuthenticated,)

    def _require_company(self):
        if not self.request.company:
            raise BusinessError("You have not joined a company yet.")
        return Company.objects.annotate(member_count=Count("members", distinct=True)).get(pk=self.request.company.pk)

    def list(self, request):
        company = self._require_company()
        return Response(self.get_serializer(company).data)

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company = services.create_company(user=request.user, **serializer.validated_data)
        return Response(self.get_serializer(company).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["patch"], permission_classes=(IsAuthenticated, HasCompany, CompanyRolePermission))
    def update_company(self, request):
        company = self._require_company()
        serializer = self.get_serializer(company, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=False, methods=["post"], url_path="switch")
    def switch(self, request):
        company = Company.objects.filter(uid=request.data.get("company_id")).first()
        if not company:
            raise BusinessError("Company not found.")
        services.set_default_company(request.user, company)
        return Response({**build_token_pair(request.user), "user": UserSerializer(request.user).data})

    required_roles = {"update_company": CompanyMember.CAN_MANAGE}


class CompanyMemberViewSet(
    CompanyContextMixin, mixins.ListModelMixin, mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet
):
    serializer_class = CompanyMemberSerializer
    permission_classes = (IsAuthenticated, HasCompany, CompanyRolePermission)
    pagination_class = SmallPagination
    required_roles = {
        "partial_update": CompanyMember.CAN_MANAGE,
        "update": CompanyMember.CAN_MANAGE,
        "destroy": CompanyMember.CAN_MANAGE,
        "invite": CompanyMember.CAN_MANAGE,
        "invitations": CompanyMember.CAN_MANAGE,
        "revoke_invitation": CompanyMember.CAN_MANAGE,
    }

    def get_queryset(self):
        return CompanyMember.objects.filter(company=self.request.company).select_related("user").order_by("-role", "id")

    def perform_update(self, serializer):
        target = serializer.instance
        if target.role == CompanyMember.Role.OWNER and self.request.membership.role != CompanyMember.Role.OWNER:
            raise BusinessError("Only an owner can change another owner.")
        if (
            serializer.validated_data.get("role") == CompanyMember.Role.OWNER
            and self.request.membership.role != CompanyMember.Role.OWNER
        ):
            raise BusinessError("Only an owner can promote members to owner.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.pk == self.request.membership.pk:
            raise BusinessError("You cannot remove yourself. Transfer ownership first.")
        if instance.role == CompanyMember.Role.OWNER:
            raise BusinessError("Owners cannot be removed.")
        instance.delete()

    @action(detail=False, methods=["post"])
    def invite(self, request):
        serializer = InvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation = services.invite_member(
            company=request.company,
            inviter=request.user,
            email=serializer.validated_data["email"],
            role=serializer.validated_data.get("role", CompanyMember.Role.BUYER),
        )
        return Response(InvitationSerializer(invitation).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def invitations(self, request):
        qs = CompanyInvitation.objects.filter(company=request.company).select_related("invited_by").order_by("-created_at")
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(InvitationSerializer(page, many=True).data)

    @action(detail=False, methods=["post"], url_path=r"invitations/(?P<uid>[0-9a-f-]+)/revoke")
    def revoke_invitation(self, request, uid=None):
        updated = CompanyInvitation.objects.filter(
            company=request.company, uid=uid, status=CompanyInvitation.Status.PENDING
        ).update(status=CompanyInvitation.Status.REVOKED)
        if not updated:
            raise BusinessError("Invitation not found or already handled.")
        return Response({"detail": "Invitation revoked."})


class AcceptInvitationView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, token):
        invitation = CompanyInvitation.objects.select_related("company", "invited_by").filter(token=token).first()
        if not invitation or not invitation.is_valid:
            raise BusinessError("This invitation is invalid or has expired.")
        return Response(InvitationSerializer(invitation).data)

    def post(self, request, token):
        services.accept_invitation(token=token, user=request.user)
        return Response({**build_token_pair(request.user), "user": UserSerializer(request.user).data})


class AddressViewSet(CompanyContextMixin, viewsets.ModelViewSet):
    serializer_class = AddressSerializer
    permission_classes = (IsAuthenticated, HasCompany, CompanyRolePermission)
    pagination_class = None
    lookup_field = "uid"
    required_roles = {
        "create": CompanyMember.CAN_ORDER,
        "update": CompanyMember.CAN_ORDER,
        "partial_update": CompanyMember.CAN_ORDER,
        "destroy": CompanyMember.CAN_MANAGE,
    }

    def get_queryset(self):
        return Address.objects.filter(company=self.request.company)

    @transaction.atomic
    def perform_create(self, serializer):
        self._clear_default(serializer.validated_data)
        serializer.save(company=self.request.company)

    @transaction.atomic
    def perform_update(self, serializer):
        self._clear_default(serializer.validated_data, exclude=serializer.instance.pk)
        serializer.save()

    def _clear_default(self, data, exclude=None):
        if data.get("is_default"):
            kind = data.get("kind") or Address.Kind.SHIPPING
            qs = Address.objects.filter(company=self.request.company, kind=kind, is_default=True)
            if exclude:
                qs = qs.exclude(pk=exclude)
            qs.update(is_default=False)
