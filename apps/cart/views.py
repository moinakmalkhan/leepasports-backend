from django.db.models import Count
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import CompanyMember
from apps.core.mixins import CompanyContextMixin
from apps.core.pagination import SmallPagination
from apps.core.permissions import CompanyRolePermission, HasCompany

from . import services
from .models import CartItem, SavedList
from .serializers import (
    CartItemSerializer,
    CartItemUpdateSerializer,
    CartItemWriteSerializer,
    CartSerializer,
    SavedListSerializer,
)


class CartView(CompanyContextMixin, APIView):
    """GET current cart (prices refreshed), POST add line, DELETE clear."""

    permission_classes = (AllowAny,)

    def _response(self, request, cart, status_code=200):
        totals = services.reprice_cart(cart, request.company)
        return Response(CartSerializer({"cart": cart, **totals}).data, status=status_code)

    def get(self, request):
        cart = services.get_or_create_cart(request)
        return self._response(request, cart)

    @extend_schema(request=CartItemWriteSerializer, responses=CartSerializer)
    def post(self, request):
        serializer = CartItemWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        cart = services.get_or_create_cart(request)
        services.add_item(
            cart,
            request.company,
            product_slug=data["product"],
            fabric_slug=data.get("fabric"),
            breakdown=data["breakdown"],
            color=data.get("color", ""),
            customization=data.get("customization"),
            notes=data.get("notes", ""),
            artwork=data.get("artwork"),
        )
        return self._response(request, cart, status.HTTP_201_CREATED)

    def patch(self, request):
        cart = services.get_or_create_cart(request)
        notes = request.data.get("notes")
        if notes is not None:
            cart.notes = str(notes)[:2000]
            cart.save(update_fields=["notes"])
        return self._response(request, cart)

    def delete(self, request):
        cart = services.get_or_create_cart(request)
        cart.items.all().delete()
        return self._response(request, cart)


class QuickOrderView(CompanyContextMixin, APIView):
    """Bulk add by SKU — paste from a spreadsheet:
    `{"lines": [{"sku": "LS-JRS-001", "gender": "men", "size": "XL", "quantity": 12}, ...]}`
    Lines for the same SKU are merged into one configured cart item (default fabric).
    """

    permission_classes = (AllowAny,)

    def post(self, request):
        from collections import defaultdict

        from apps.catalog.models import Product, ProductSizeOption
        from apps.core.exceptions import BusinessError

        lines = request.data.get("lines") or []
        if not isinstance(lines, list) or not lines:
            raise BusinessError("Add at least one line.")
        if len(lines) > 200:
            raise BusinessError("Maximum 200 lines per quick order.")
        grouped = defaultdict(list)
        for raw in lines:
            sku = str(raw.get("sku", "")).strip().upper()
            if sku:
                grouped[sku].append(raw)
        products = {p.sku.upper(): p for p in Product.objects.active().filter(sku__in=grouped.keys())}
        cart = services.get_or_create_cart(request)
        added, errors = 0, []
        for sku, rows in grouped.items():
            product = products.get(sku)
            if not product:
                errors.append({"sku": sku, "error": "Unknown SKU"})
                continue
            sizes = {
                (o.gender, o.size.label.upper()): o.size_id
                for o in ProductSizeOption.objects.select_related("size").filter(product=product, is_active=True)
            }
            breakdown = []
            for row in rows:
                key = (str(row.get("gender", "men")).lower(), str(row.get("size", "")).strip().upper())
                size_id = sizes.get(key)
                try:
                    qty = int(row.get("quantity", 0))
                except (TypeError, ValueError):
                    qty = 0
                if size_id is None or qty <= 0:
                    errors.append({"sku": sku, "error": f"Size {key[1]} ({key[0]}) not available"})
                    continue
                breakdown.append({"gender": key[0], "size_id": size_id, "quantity": qty})
            if not breakdown:
                continue
            try:
                services.add_item(cart, request.company, product_slug=product.slug, fabric_slug=None, breakdown=breakdown)
                added += 1
            except BusinessError as exc:
                errors.append({"sku": sku, "error": str(exc.detail)})
        totals = services.reprice_cart(cart, request.company)
        return Response(
            {"added": added, "errors": errors, "cart": CartSerializer({"cart": cart, **totals}).data},
            status=201 if added else 400,
        )


class CartItemView(CompanyContextMixin, APIView):
    permission_classes = (AllowAny,)

    def _item(self, request, uid) -> CartItem:
        cart = services.get_or_create_cart(request)
        return get_object_or_404(CartItem.objects.select_related("product", "fabric"), cart=cart, uid=uid)

    @extend_schema(request=CartItemUpdateSerializer, responses=CartItemSerializer)
    def patch(self, request, uid):
        item = self._item(request, uid)
        serializer = CartItemUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        changes = {k: v for k, v in data.items() if k not in ("fabric",)}
        if "fabric" in data:
            changes["fabric_slug"] = data["fabric"]
        services.update_item(item, request.company, **changes)
        return Response(CartItemSerializer(item, context={"request": request}).data)

    def delete(self, request, uid):
        item = self._item(request, uid)
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SavedListViewSet(CompanyContextMixin, viewsets.ModelViewSet):
    serializer_class = SavedListSerializer
    permission_classes = (IsAuthenticated, HasCompany, CompanyRolePermission)
    pagination_class = SmallPagination
    lookup_field = "uid"
    required_roles = {
        "create": CompanyMember.CAN_ORDER,
        "update": CompanyMember.CAN_ORDER,
        "partial_update": CompanyMember.CAN_ORDER,
        "destroy": CompanyMember.CAN_ORDER,
        "add_to_cart": CompanyMember.CAN_ORDER,
        "from_cart": CompanyMember.CAN_ORDER,
    }

    def get_queryset(self):
        qs = (
            SavedList.objects.filter(company=self.request.company)
            .annotate(item_count=Count("items"))
            .select_related("created_by")
        )
        if self.action == "retrieve":
            qs = qs.prefetch_related(
                "items__product__category", "items__product__base_fabric", "items__product__images", "items__fabric"
            )
        return qs

    def perform_create(self, serializer):
        serializer.save(company=self.request.company, created_by=self.request.user)

    @action(detail=True, methods=["post"], url_path="add-to-cart")
    def add_to_cart(self, request, uid=None):
        saved = self.get_object()
        cart = services.get_or_create_cart(request)
        added = services.add_saved_list_to_cart(saved, cart, request.company)
        return Response({"detail": f"{added} item(s) added to your cart.", "added": added})

    @action(detail=False, methods=["post"], url_path="from-cart")
    def from_cart(self, request):
        name = (request.data.get("name") or "").strip()
        if not name:
            return Response({"detail": "Give the list a name.", "code": "validation_error"}, status=400)
        cart = services.get_or_create_cart(request)
        if not cart.items.exists():
            return Response({"detail": "Your cart is empty.", "code": "business_error"}, status=400)
        saved = services.save_cart_as_list(cart, request.company, request.user, name, request.data.get("description", ""))
        saved.item_count = saved.items.count()
        return Response(SavedListSerializer(saved, context={"request": request}).data, status=201)
