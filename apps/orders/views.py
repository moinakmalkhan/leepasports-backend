import json

from django.db.models import Count, Prefetch, Q
from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cart import services as cart_services
from apps.core.permissions import IsStaff
from apps.core.throttling import AuthRateThrottle

from . import services
from .models import Order, OrderItem, ReturnRequest
from .serializers import (
    CancelSerializer,
    CheckoutSerializer,
    OrderDetailSerializer,
    OrderListSerializer,
    ReturnRequestInputSerializer,
    ReturnRequestSerializer,
    ShippingQuoteSerializer,
    StaffTransitionSerializer,
)


class OrderFilter(filters.FilterSet):
    status = filters.MultipleChoiceFilter(choices=Order.Status.choices)
    q = filters.CharFilter(method="filter_q")
    open = filters.BooleanFilter(method="filter_open")

    class Meta:
        model = Order
        fields = ()

    def filter_q(self, qs, name, value):
        return qs.filter(Q(number__icontains=value) | Q(items__product_name__icontains=value)).distinct()

    def filter_open(self, qs, name, value):
        return qs.filter(status__in=Order.OPEN_STATUSES) if value else qs.exclude(status__in=Order.OPEN_STATUSES)


class ShippingQuoteView(APIView):
    """Delivery charge + ETA for a city before the customer commits."""

    permission_classes = (AllowAny,)

    @extend_schema(request=ShippingQuoteSerializer)
    def post(self, request):
        serializer = ShippingQuoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        cart = cart_services.get_or_create_cart(request)
        totals = cart_services.compute_totals(cart, user=request.user if request.user.is_authenticated else None)
        quote = services.shipping_quote(
            subtotal=totals.subtotal - totals.discount,
            city=d["city"],
            province=d["province"],
            payment_method=d["payment_method"],
            free_shipping=totals.free_shipping,
        )
        zone = quote["zone"]
        return Response(
            {
                "zone": zone.name if zone else None,
                "rate": quote["rate"],
                "cod_fee": quote["cod_fee"],
                "is_free": quote["is_free"],
                "free_over": quote["free_over"],
                "min_days": quote["min_days"],
                "max_days": quote["max_days"],
                "subtotal": totals.subtotal,
                "discount": totals.discount,
                "total": totals.subtotal - totals.discount + quote["rate"] + quote["cod_fee"],
            }
        )


class CheckoutView(APIView):
    """Guest or signed-in checkout. Returns the order (guests get a tracking token via email)."""

    permission_classes = (AllowAny,)
    throttle_classes = (AuthRateThrottle,)

    @extend_schema(request=CheckoutSerializer, responses=OrderDetailSerializer)
    def post(self, request):
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        order = services.checkout(
            request=request,
            address=dict(d["address"]),
            payment_method=d["payment_method"],
            email=d["email"],
            phone=d["address"]["phone"],
            notes=d.get("notes", ""),
            save_address=d.get("save_address", False),
            is_gift=d.get("is_gift", False),
        )
        order = Order.objects.select_related("shipping_zone").prefetch_related("items", "history", "returns").get(pk=order.pk)
        return Response(OrderDetailSerializer(order, context={"request": request}).data, status=status.HTTP_201_CREATED)


class OrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = (IsAuthenticated,)
    lookup_field = "uid"
    filterset_class = OrderFilter
    ordering = ("-created_at",)

    def get_queryset(self):
        qs = Order.objects.filter(user=self.request.user)
        if self.action == "retrieve":
            return qs.select_related("shipping_zone").prefetch_related(
                Prefetch("items", queryset=OrderItem.objects.select_related("product", "review")),
                "history",
                "returns__items__order_item",
                "returns__items__exchange_variant",
            )
        return qs.annotate(item_count=Count("items")).prefetch_related("items")

    def get_serializer_class(self):
        return OrderListSerializer if self.action == "list" else OrderDetailSerializer

    def _detail(self, order):
        return OrderDetailSerializer(
            self.get_queryset().get(pk=order.pk) if self.action != "retrieve" else order, context=self.get_serializer_context()
        ).data

    @extend_schema(request=CancelSerializer, responses=OrderDetailSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, uid=None):
        order = self.get_object()
        serializer = CancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.cancel(order, by=request.user, reason=serializer.validated_data["reason"])
        order.refresh_from_db()
        return Response(OrderDetailSerializer(order, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def reorder(self, request, uid=None):
        added = services.reorder(self.get_object(), request)
        return Response(
            {"added": added, "detail": f"{added} item(s) added to your bag." if added else "Those items are no longer available."}
        )

    @extend_schema(request=ReturnRequestInputSerializer, responses=ReturnRequestSerializer)
    @action(detail=True, methods=["post"], url_path="returns")
    def request_return(self, request, uid=None):
        order = self.get_object()
        data = request.data.dict() if hasattr(request.data, "dict") else dict(request.data)
        if isinstance(data.get("items"), str):
            data["items"] = json.loads(data["items"])
        serializer = ReturnRequestInputSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        req = services.request_return(
            order,
            user=request.user,
            kind=d["kind"],
            reason=d["reason"],
            details=d.get("details", ""),
            items=d["items"],
            image=d.get("image"),
        )
        return Response(ReturnRequestSerializer(req, context=self.get_serializer_context()).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        qs = Order.objects.filter(user=request.user)
        agg = qs.aggregate(
            total=Count("id"),
            open=Count("id", filter=Q(status__in=Order.OPEN_STATUSES)),
            delivered=Count("id", filter=Q(status__in=[Order.Status.DELIVERED, Order.Status.COMPLETED])),
        )
        agg["returns"] = (
            ReturnRequest.objects.filter(order__user=request.user)
            .exclude(status__in=[ReturnRequest.Status.COMPLETED, ReturnRequest.Status.REJECTED])
            .count()
        )
        return Response(agg)


class ReturnViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = (IsAuthenticated,)
    serializer_class = ReturnRequestSerializer
    lookup_field = "uid"

    def get_queryset(self):
        return (
            ReturnRequest.objects.filter(order__user=self.request.user)
            .select_related("order")
            .prefetch_related("items__order_item", "items__exchange_variant")
        )


class PublicOrderTrackingView(APIView):
    """Track without signing in: order number + email or phone used at checkout."""

    permission_classes = (AllowAny,)
    throttle_classes = (AuthRateThrottle,)

    def get(self, request):
        number = (request.query_params.get("number") or "").strip().upper()
        contact = (request.query_params.get("contact") or request.query_params.get("email") or "").strip().lower()
        if not number or not contact:
            return Response(
                {"detail": "Enter your order number and the email or phone used at checkout.", "code": "validation_error"},
                status=400,
            )
        digits = "".join(ch for ch in contact if ch.isdigit())
        order = (
            Order.objects.filter(number=number)
            .filter(Q(email__iexact=contact) | (Q(phone__endswith=digits[-9:]) if len(digits) >= 9 else Q(pk=None)))
            .prefetch_related("history", "items")
            .first()
        )
        if not order:
            return Response({"detail": "We couldn't find an order with those details.", "code": "not_found"}, status=404)
        steps = [
            Order.Status.PENDING,
            Order.Status.CONFIRMED,
            Order.Status.PROCESSING,
            Order.Status.SHIPPED,
            Order.Status.OUT_FOR_DELIVERY,
            Order.Status.DELIVERED,
        ]
        history = [h for h in order.history.all() if h.is_customer_visible]
        reached = {h.to_status for h in history} | {order.status}
        return Response(
            {
                "number": order.number,
                "status": order.status,
                "status_display": order.get_status_display(),
                "steps": [{"status": s.value, "label": s.label, "reached": s.value in reached} for s in steps],
                "timeline": [{"status": h.to_status, "note": h.note, "at": h.created_at} for h in history],
                "carrier": order.carrier,
                "tracking_number": order.tracking_number,
                "tracking_url": order.tracking_url,
                "estimated_delivery": order.estimated_delivery,
                "shipped_at": order.shipped_at,
                "delivered_at": order.delivered_at,
                "items": [
                    {"name": i.product_name, "variant": i.variant_label, "quantity": i.quantity, "image_url": i.image_url}
                    for i in order.items.all()
                ],
                "total_quantity": order.total_quantity,
                "grand_total": order.grand_total,
                "payment_method": order.payment_method,
                "ship_to": {"city": order.shipping_address.get("city"), "name": order.shipping_address.get("full_name")},
            }
        )


class StaffOrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = (IsStaff,)
    lookup_field = "uid"
    filterset_class = OrderFilter
    ordering = ("-created_at",)
    queryset = Order.objects.select_related("user").annotate(item_count=Count("items")).prefetch_related("items")

    def get_serializer_class(self):
        return OrderDetailSerializer if self.action != "list" else OrderListSerializer

    @extend_schema(request=StaffTransitionSerializer, responses=OrderDetailSerializer)
    @action(detail=True, methods=["post"])
    def transition(self, request, uid=None):
        order = self.get_object()
        serializer = StaffTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        extra = {
            k: v
            for k, v in d.items()
            if k in ("carrier", "tracking_number", "tracking_url", "estimated_delivery") and v is not None
        }
        services.transition(order, d["status"], by=request.user, note=d.get("note", ""), **extra)
        order.refresh_from_db()
        return Response(OrderDetailSerializer(order, context=self.get_serializer_context()).data)
