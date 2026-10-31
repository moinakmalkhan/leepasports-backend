from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsStaff
from apps.core.throttling import AuthRateThrottle
from apps.orders.models import Order

from . import services
from .models import BankAccount, Payment
from .serializers import BankAccountSerializer, ConfirmSerializer, PaymentSerializer, ProofSerializer


class BankAccountView(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = (AllowAny,)
    serializer_class = BankAccountSerializer
    queryset = BankAccount.objects.filter(is_active=True)
    pagination_class = None


class PaymentMethodsView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        return Response(
            [
                {
                    "code": "cod",
                    "label": "Cash on delivery",
                    "description": "Pay the rider when your order arrives.",
                    "enabled": True,
                },
                {
                    "code": "bank_transfer",
                    "label": "Bank transfer / JazzCash / EasyPaisa",
                    "description": "Transfer the total and upload the receipt. We ship after confirming.",
                    "enabled": True,
                },
                {"code": "card", "label": "Debit / credit card", "description": "Coming soon.", "enabled": False},
            ]
        )


class OrderPaymentView(APIView):
    """Payments for an order, reachable by the owner or (for guests) with the order email."""

    permission_classes = (AllowAny,)
    throttle_classes = (AuthRateThrottle,)

    def _order(self, request, uid):
        order = get_object_or_404(Order, uid=uid)
        if request.user.is_authenticated and order.user_id == request.user.pk:
            return order
        if (request.query_params.get("email") or request.data.get("email") or "").lower() == order.email:
            return order
        from django.http import Http404

        raise Http404

    def get(self, request, uid):
        order = self._order(request, uid)
        return Response(PaymentSerializer(order.payments.all(), many=True, context={"request": request}).data)

    @extend_schema(request=ProofSerializer, responses=PaymentSerializer)
    def post(self, request, uid):
        order = self._order(request, uid)
        payment = order.payments.filter(status__in=[Payment.Status.PENDING, Payment.Status.FAILED]).first()
        if not payment:
            payment = services.create_pending_payment(order)
        serializer = ProofSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        services.submit_proof(payment, reference=d["reference"], proof=d.get("proof"), note=d.get("note", ""))
        return Response(PaymentSerializer(payment, context={"request": request}).data)


class StaffPaymentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = (IsStaff,)
    serializer_class = PaymentSerializer
    lookup_field = "uid"
    filterset_fields = ("status", "method")
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
