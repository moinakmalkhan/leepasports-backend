from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import Product, ProductVariant
from apps.catalog.serializers import ProductCardSerializer

from . import services
from .models import CartItem
from .serializers import AddItemSerializer, CartSerializer, CouponSerializer, QuantitySerializer, WishlistItemSerializer


def _user(request):
    return request.user if request.user.is_authenticated else None


class CartView(APIView):
    """GET bag · POST add line · PATCH notes · DELETE empty."""

    permission_classes = (AllowAny,)

    def _response(self, request, cart, status_code=200):
        totals = services.compute_totals(cart, user=_user(request))
        return Response(CartSerializer(totals, context={"request": request}).data, status=status_code)

    def get(self, request):
        return self._response(request, services.get_or_create_cart(request))

    @extend_schema(request=AddItemSerializer, responses=CartSerializer)
    def post(self, request):
        serializer = AddItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cart = services.get_or_create_cart(request)
        services.add_item(cart, variant_uid=serializer.validated_data["variant"], quantity=serializer.validated_data["quantity"])
        return self._response(request, cart, status.HTTP_201_CREATED)

    def patch(self, request):
        cart = services.get_or_create_cart(request)
        if "notes" in request.data:
            cart.notes = str(request.data.get("notes") or "")[:500]
            cart.save(update_fields=["notes", "updated_at"])
        return self._response(request, cart)

    def delete(self, request):
        cart = services.get_or_create_cart(request)
        cart.items.all().delete()
        services.remove_coupon(cart)
        return self._response(request, cart)


class CartItemView(APIView):
    permission_classes = (AllowAny,)

    def _item(self, request, uid):
        cart = services.get_or_create_cart(request)
        return cart, get_object_or_404(CartItem.objects.select_related("variant__product"), cart=cart, uid=uid)

    @extend_schema(request=QuantitySerializer, responses=CartSerializer)
    def patch(self, request, uid):
        cart, item = self._item(request, uid)
        serializer = QuantitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.set_quantity(item, serializer.validated_data["quantity"])
        return Response(CartSerializer(services.compute_totals(cart, user=_user(request)), context={"request": request}).data)

    def delete(self, request, uid):
        cart, item = self._item(request, uid)
        item.delete()
        return Response(CartSerializer(services.compute_totals(cart, user=_user(request)), context={"request": request}).data)


class CartCouponView(APIView):
    permission_classes = (AllowAny,)

    @extend_schema(request=CouponSerializer, responses=CartSerializer)
    def post(self, request):
        serializer = CouponSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cart = services.get_or_create_cart(request)
        services.apply_coupon(
            cart, serializer.validated_data["code"], user=_user(request), email=serializer.validated_data.get("email", "")
        )
        return Response(CartSerializer(services.compute_totals(cart, user=_user(request)), context={"request": request}).data)

    def delete(self, request):
        cart = services.get_or_create_cart(request)
        services.remove_coupon(cart)
        return Response(CartSerializer(services.compute_totals(cart, user=_user(request)), context={"request": request}).data)


class WishlistView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        wishlist = services.get_wishlist(request.user)
        items = wishlist.items.select_related("variant__color", "variant__size").prefetch_related(
            "product__images", "product__variants__color", "product__variants__size", "product__category"
        )
        # Reuse listing prefetch names so the card serializer stays cheap.
        products = list(Product.objects.for_listing().filter(pk__in=[i.product_id for i in items]))
        by_id = {p.pk: p for p in products}
        data = [
            {
                "product": ProductCardSerializer(by_id[i.product_id], context={"request": request}).data,
                "variant": WishlistItemSerializer(i, context={"request": request}).data["variant"],
                "added_at": i.added_at,
            }
            for i in items
            if i.product_id in by_id
        ]
        return Response(
            {
                "count": len(data),
                "results": data,
                "product_ids": [str(by_id[i.product_id].uid) for i in items if i.product_id in by_id],
            }
        )

    def post(self, request):
        product = get_object_or_404(Product.objects.active(), slug=request.data.get("product"))
        variant = (
            ProductVariant.objects.filter(uid=request.data.get("variant"), product=product).first()
            if request.data.get("variant")
            else None
        )
        added = services.toggle_wishlist(request.user, product, variant)
        return Response({"wishlisted": added, "detail": "Saved to your wishlist" if added else "Removed from your wishlist"})
