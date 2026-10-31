from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import CompanyMember
from apps.core.mixins import CompanyContextMixin
from apps.core.permissions import CompanyRolePermission, HasCompany, IsStaff

from . import services
from .models import BankAccount, Payment
from .serializers import BankAccountSerializer, ConfirmSerializer, PaymentSerializer, ProofSerializer


class BankAccountView(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = (IsAuthenticated,)
    serializer_class = BankAccountSerializer
    queryset = BankAccount.objects.filter(is_active=True)
    pagination_class = None


class PaymentViewSet(CompanyContextMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = (IsAuthenticated, HasCompany, CompanyRolePermission)
    serializer_class = PaymentSerializer
    lookup_field = "uid"
    filterset_fields = ("status", "kind")
    ordering = ("-created_at",)
    required_roles = {"submit_proof": CompanyMember.CAN_ORDER}

    def get_queryset(self):
        qs = Payment.objects.filter(order__company=self.request.company).select_related("order")
        order_uid = self.request.query_params.get("order")
        return qs.filter(order__uid=order_uid) if order_uid else qs

    @extend_schema(request=ProofSerializer, responses=PaymentSerializer)
    @action(detail=True, methods=["post"], url_path="submit-proof")
    def submit_proof(self, request, uid=None):
        payment = self.get_object()
        serializer = ProofSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        services.submit_proof(payment, reference=data["reference"], proof=data.get("proof"), note=data.get("note", ""))
        return Response(PaymentSerializer(payment, context=self.get_serializer_context()).data)


class StaffPaymentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = (IsStaff,)
    serializer_class = PaymentSerializer
    lookup_field = "uid"
    filterset_fields = ("status", "kind")
    ordering = ("-created_at",)
    queryset = Payment.objects.select_related("order")

    @extend_schema(request=ConfirmSerializer, responses=PaymentSerializer)
    @action(detail=True, methods=["post"])
    def confirm(self, request, uid=None):
        payment = self.get_object()
        serializer = ConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.confirm(payment, by=request.user, amount=serializer.validated_data.get("amount"))
        payment.refresh_from_db()
        return Response(PaymentSerializer(payment, context=self.get_serializer_context()).data)
