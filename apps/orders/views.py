from django.db.models import Count, Q
from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import CompanyMember
from apps.core.mixins import CompanyContextMixin
from apps.core.permissions import CompanyRolePermission, HasCompany, IsStaff
from apps.core.throttling import AuthRateThrottle

from . import services
from .models import Order, ShippingMethod
from .serializers import (
    CancelSerializer,
    CheckoutSerializer,
    OrderDetailSerializer,
    OrderListSerializer,
    ShippingMethodSerializer,
    StaffTransitionSerializer,
)


class OrderFilter(filters.FilterSet):
    status = filters.MultipleChoiceFilter(choices=Order.Status.choices)
    payment_status = filters.MultipleChoiceFilter(choices=Order.PaymentStatus.choices)
    q = filters.CharFilter(method="filter_q")
    date_from = filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    date_to = filters.DateFilter(field_name="created_at", lookup_expr="date__lte")
    open = filters.BooleanFilter(method="filter_open")

    class Meta:
        model = Order
        fields = ()

    def filter_q(self, qs, name, value):
        return qs.filter(
            Q(number__icontains=value) | Q(po_number__icontains=value) | Q(items__product_name__icontains=value)
        ).distinct()

    def filter_open(self, qs, name, value):
        return qs.filter(status__in=Order.OPEN_STATUSES) if value else qs.exclude(status__in=Order.OPEN_STATUSES)


class ShippingMethodListView(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = (AllowAny,)
    serializer_class = ShippingMethodSerializer
    queryset = ShippingMethod.objects.filter(is_active=True)
    pagination_class = None


class OrderViewSet(CompanyContextMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = (IsAuthenticated, HasCompany, CompanyRolePermission)
    lookup_field = "uid"
    filterset_class = OrderFilter
    ordering_fields = ("created_at", "grand_total", "status")
    ordering = ("-created_at",)
    required_roles = {
        "checkout": CompanyMember.CAN_ORDER,
        "cancel": CompanyMember.CAN_ORDER,
        "approve": CompanyMember.CAN_APPROVE,
        "reorder": CompanyMember.CAN_ORDER,
    }

    def get_queryset(self):
        qs = Order.objects.filter(company=self.request.company).select_related("placed_by")
        if self.action == "retrieve":
            return qs.select_related("shipping_method", "approved_by", "company", "quote").prefetch_related(
                "items__product", "history__changed_by"
            )
        return qs.annotate(item_count=Count("items"))

    def get_serializer_class(self):
        return OrderDetailSerializer if self.action in ("retrieve", "checkout", "cancel", "approve") else OrderListSerializer

    @extend_schema(request=CheckoutSerializer, responses=OrderDetailSerializer)
    @action(detail=False, methods=["post"])
    def checkout(self, request):
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        order = services.checkout(
            request=request,
            shipping_address_uid=data["shipping_address"],
            billing_address_uid=data.get("billing_address"),
            shipping_method_code=data["shipping_method"],
            payment_method=data["payment_method"],
            po_number=data.get("po_number", ""),
            customer_notes=data.get("customer_notes", ""),
            requested_delivery_date=data.get("requested_delivery_date"),
        )
        order = self._reload(order)
        return Response(OrderDetailSerializer(order, context=self.get_serializer_context()).data, status=status.HTTP_201_CREATED)

    def _reload(self, order):
        return (
            Order.objects.select_related("shipping_method", "approved_by", "company", "placed_by")
            .prefetch_related("items", "history__changed_by")
            .get(pk=order.pk)
        )

    @extend_schema(request=CancelSerializer, responses=OrderDetailSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, uid=None):
        order = self.get_object()
        serializer = CancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.cancel(order, by=request.user, reason=serializer.validated_data["reason"])
        return Response(OrderDetailSerializer(self._reload(order), context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, uid=None):
        order = self.get_object()
        services.approve(order, by=request.user, membership=request.membership)
        return Response(OrderDetailSerializer(self._reload(order), context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def reorder(self, request, uid=None):
        order = self.get_object()
        added = services.reorder(order, request)
        return Response({"detail": f"{added} item(s) added to your cart.", "added": added})

    @action(detail=True, methods=["get"])
    def invoice(self, request, uid=None):
        """Invoice / pro-forma data for the printable document (frontend renders & prints to PDF)."""
        from apps.payments.models import BankAccount
        from apps.payments.serializers import BankAccountSerializer

        order = self.get_object()
        data = OrderDetailSerializer(order, context=self.get_serializer_context()).data
        data["document_type"] = (
            "Invoice"
            if order.payment_method == Order.PaymentMethod.NET_TERMS or order.payment_status == Order.PaymentStatus.PAID
            else "Pro-forma invoice"
        )
        data["bank_accounts"] = BankAccountSerializer(
            BankAccount.objects.filter(is_active=True, currency=order.currency) or BankAccount.objects.filter(is_active=True),
            many=True,
        ).data
        data["seller"] = {
            "name": "Leepa Sports",
            "address": "Sialkot, Punjab, Pakistan",
            "email": __import__("django.conf", fromlist=["settings"]).settings.LEEPA["SUPPORT_EMAIL"],
        }
        return Response(data)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Dashboard numbers for the company: one aggregate query."""
        from django.db.models import Sum

        qs = Order.objects.filter(company=request.company)
        agg = qs.aggregate(
            total=Count("id"),
            open=Count("id", filter=Q(status__in=Order.OPEN_STATUSES)),
            pending_approval=Count("id", filter=Q(status=Order.Status.PENDING_APPROVAL)),
            awaiting_payment=Count("id", filter=Q(status=Order.Status.PENDING_PAYMENT)),
            in_production=Count("id", filter=Q(status__in=[Order.Status.IN_PRODUCTION, Order.Status.QUALITY_CHECK])),
            shipped=Count("id", filter=Q(status=Order.Status.SHIPPED)),
            spent=Sum(
                "grand_total",
                filter=Q(
                    status__in=[
                        Order.Status.COMPLETED,
                        Order.Status.DELIVERED,
                        Order.Status.SHIPPED,
                        Order.Status.IN_PRODUCTION,
                        Order.Status.CONFIRMED,
                        Order.Status.QUALITY_CHECK,
                    ]
                ),
            ),
            outstanding=Sum(
                "grand_total",
                filter=Q(
                    payment_status__in=[Order.PaymentStatus.UNPAID, Order.PaymentStatus.DEPOSIT_PAID, Order.PaymentStatus.OVERDUE]
                )
                & ~Q(status=Order.Status.CANCELLED),
            ),
        )
        agg["spent"] = agg["spent"] or 0
        agg["outstanding"] = agg["outstanding"] or 0
        return Response(agg)


class StaffOrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Operations endpoints for Leepa staff (status updates, tracking)."""

    permission_classes = (IsStaff,)
    lookup_field = "uid"
    filterset_class = OrderFilter
    ordering = ("-created_at",)
    queryset = Order.objects.select_related("company", "placed_by").annotate(item_count=Count("items"))

    def get_serializer_class(self):
        return OrderDetailSerializer if self.action != "list" else OrderListSerializer

    @extend_schema(request=StaffTransitionSerializer, responses=OrderDetailSerializer)
    @action(detail=True, methods=["post"])
    def transition(self, request, uid=None):
        order = self.get_object()
        serializer = StaffTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        extra = {
            k: v
            for k, v in data.items()
            if k in ("carrier", "tracking_number", "tracking_url", "estimated_ship_date") and v is not None
        }
        services.transition(order, data["status"], by=request.user, note=data.get("note", ""), **extra)
        order.refresh_from_db()
        return Response(OrderDetailSerializer(order, context=self.get_serializer_context()).data)


class PublicOrderTrackingView(APIView):
    """Track an order without signing in: order number + the email it was placed with.

    Returns only what a shipping label would reveal (status timeline, carrier,
    tracking, ETA). Throttled to avoid enumeration."""

    permission_classes = (AllowAny,)
    throttle_classes = (AuthRateThrottle,)

    def get(self, request):
        number = (request.query_params.get("number") or "").strip().upper()
        email = (request.query_params.get("email") or "").strip().lower()
        if not number or not email:
            return Response({"detail": "Enter your order number and email.", "code": "validation_error"}, status=400)
        order = (
            Order.objects.filter(number=number)
            .filter(
                Q(placed_by__email__iexact=email)
                | Q(company__email__iexact=email)
                | Q(company__members__user__email__iexact=email)
            )
            .select_related("shipping_method")
            .prefetch_related("history")
            .distinct()
            .first()
        )
        if not order:
            return Response({"detail": "We couldn't find an order with those details.", "code": "not_found"}, status=404)
        steps = [s for s in Order.Status if s not in (Order.Status.PENDING_APPROVAL, Order.Status.CANCELLED)]
        history = [h for h in order.history.all() if h.is_customer_visible]
        return Response(
            {
                "number": order.number,
                "status": order.status,
                "status_display": order.get_status_display(),
                "steps": [
                    {
                        "status": s.value,
                        "label": s.label,
                        "reached": any(h.to_status == s.value for h in history) or order.status == s.value,
                    }
                    for s in steps
                ],
                "timeline": [{"status": h.to_status, "note": h.note, "at": h.created_at} for h in history],
                "carrier": order.carrier,
                "tracking_number": order.tracking_number,
                "tracking_url": order.tracking_url,
                "estimated_ship_date": order.estimated_ship_date,
                "shipped_at": order.shipped_at,
                "delivered_at": order.delivered_at,
                "total_quantity": order.total_quantity,
                "ship_to": {"city": order.shipping_address.get("city"), "country": order.shipping_address.get("country")},
            }
        )
