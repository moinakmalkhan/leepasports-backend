from django.db.models import Count
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import CompanyMember
from apps.core.mixins import CompanyContextMixin
from apps.core.permissions import CompanyRolePermission, HasCompany, IsStaff
from apps.orders.serializers import OrderDetailSerializer

from . import services
from .models import Quote
from .serializers import (
    QuoteAcceptSerializer,
    QuoteDetailSerializer,
    QuoteListSerializer,
    QuoteRequestSerializer,
    QuoteRespondSerializer,
)


class QuoteViewSet(CompanyContextMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = (IsAuthenticated, HasCompany, CompanyRolePermission)
    lookup_field = "uid"
    filterset_fields = ("status",)
    ordering = ("-created_at",)
    required_roles = {"create": CompanyMember.CAN_ORDER, "accept": CompanyMember.CAN_ORDER, "decline": CompanyMember.CAN_ORDER}

    def get_queryset(self):
        qs = Quote.objects.filter(company=self.request.company).select_related("requested_by")
        if self.action == "retrieve":
            return qs.select_related("handled_by", "company").prefetch_related("items__product", "orders")
        return qs.annotate(item_count=Count("items"))

    def get_serializer_class(self):
        return QuoteListSerializer if self.action == "list" else QuoteDetailSerializer

    @extend_schema(request=QuoteRequestSerializer, responses=QuoteDetailSerializer)
    def create(self, request):
        serializer = QuoteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        quote = services.request_quote(
            request=request,
            customer_notes=data.get("customer_notes", ""),
            target_budget=data.get("target_budget"),
            delivery_deadline=data.get("delivery_deadline"),
            shipping_address_uid=data.get("shipping_address"),
        )
        quote = (
            Quote.objects.select_related("requested_by", "handled_by", "company")
            .prefetch_related("items", "orders")
            .get(pk=quote.pk)
        )
        return Response(QuoteDetailSerializer(quote, context=self.get_serializer_context()).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=QuoteAcceptSerializer, responses=OrderDetailSerializer)
    @action(detail=True, methods=["post"])
    def accept(self, request, uid=None):
        quote = self.get_object()
        serializer = QuoteAcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        order = services.accept(
            quote,
            request=request,
            shipping_address_uid=data["shipping_address"],
            payment_method=data["payment_method"],
            po_number=data.get("po_number", ""),
        )
        return Response(OrderDetailSerializer(order, context=self.get_serializer_context()).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def decline(self, request, uid=None):
        quote = self.get_object()
        services.decline(quote, by=request.user, reason=str(request.data.get("reason", ""))[:300])
        return Response(QuoteDetailSerializer(quote, context=self.get_serializer_context()).data)


class StaffQuoteViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = (IsStaff,)
    lookup_field = "uid"
    filterset_fields = ("status", "company")
    ordering = ("-created_at",)
    queryset = Quote.objects.select_related("company", "requested_by", "handled_by").annotate(item_count=Count("items"))

    def get_serializer_class(self):
        return QuoteListSerializer if self.action == "list" else QuoteDetailSerializer

    @extend_schema(request=QuoteRespondSerializer, responses=QuoteDetailSerializer)
    @action(detail=True, methods=["post"])
    def respond(self, request, uid=None):
        quote = self.get_object()
        serializer = QuoteRespondSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        services.respond(
            quote,
            by=request.user,
            item_prices=data["item_prices"],
            message=data.get("message", ""),
            valid_days=data.get("valid_days"),
            internal_notes=data.get("internal_notes", ""),
        )
        quote.refresh_from_db()
        return Response(QuoteDetailSerializer(quote, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"], url_path="start-review")
    def start_review(self, request, uid=None):
        quote = self.get_object()
        if quote.status == Quote.Status.SUBMITTED:
            quote.status = Quote.Status.UNDER_REVIEW
            quote.handled_by = request.user
            quote.save(update_fields=["status", "handled_by", "updated_at"])
        return Response(QuoteDetailSerializer(quote, context=self.get_serializer_context()).data)
