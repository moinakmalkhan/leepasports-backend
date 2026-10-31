from django.core.cache import cache
from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.cache import make_key

from . import services
from .filters import ProductFilter
from .models import Category, Fabric, Product, SizeGroup
from .serializers import (
    CategoryNodeSerializer,
    FabricSerializer,
    ProductCardSerializer,
    ProductDetailSerializer,
    SizeGroupSerializer,
)


class CategoryTreeView(APIView):
    permission_classes = (AllowAny,)

    @extend_schema(responses=CategoryNodeSerializer(many=True))
    def get(self, request):
        include_empty = request.query_params.get("include_empty") == "1" and request.user.is_staff
        return Response(services.category_tree(include_empty=include_empty))


class CategoryDetailView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request, slug):
        category = get_object_or_404(Category.objects.active(), slug=slug)
        tree = services.category_tree()

        def find(nodes):
            for node in nodes:
                if node["slug"] == slug:
                    return node
                hit = find(node["children"])
                if hit:
                    return hit
            return None

        node = find(tree) or {"children": [], "product_count": 0}
        return Response(
            {
                "id": str(category.uid),
                "name": category.name,
                "slug": category.slug,
                "description": category.description,
                "image": request.build_absolute_uri(category.image.url) if category.image else None,
                "meta_title": category.meta_title,
                "meta_description": category.meta_description,
                "breadcrumbs": services.category_breadcrumbs(category),
                "children": node["children"],
                "product_count": node["product_count"],
            }
        )


class FabricViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = (AllowAny,)
    serializer_class = FabricSerializer
    queryset = Fabric.objects.filter(is_active=True)
    lookup_field = "slug"
    pagination_class = None
    filterset_fields = ("quality", "is_available_in_pakistan")
    ordering_fields = ("price_pkr", "gsm", "quality_rank")


class SizeGroupViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = (AllowAny,)
    serializer_class = SizeGroupSerializer
    queryset = SizeGroup.objects.prefetch_related("sizes")
    pagination_class = None


class ProductViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = (AllowAny,)
    lookup_field = "slug"
    filterset_class = ProductFilter
    ordering_fields = ("base_price", "created_at", "order_count", "name", "min_order_quantity")
    ordering = ("-is_featured", "-order_count")

    def get_queryset(self):
        if self.action == "retrieve":
            return Product.objects.for_detail()
        return Product.objects.for_listing()

    def get_serializer_class(self):
        return ProductDetailSerializer if self.action == "retrieve" else ProductCardSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        company = getattr(self.request, "company", None)
        ctx["currency"] = company.currency if company else None
        return ctx

    def retrieve(self, request, *args, **kwargs):
        product = self.get_object()
        services.record_view(product, user=request.user, session_key=request.headers.get("X-Session-Key", ""))
        return Response(self.get_serializer(product).data)

    @action(detail=True, methods=["get"])
    def related(self, request, slug=None):
        """Same-category products first, then siblings from the parent category.
        Cached per product for 15 minutes."""
        key = make_key("catalog", "related", slug)
        data = cache.get(key)
        if data is None:
            product = get_object_or_404(Product.objects.active().select_related("category"), slug=slug)
            parent_path = product.category.parent.path if product.category.parent_id else product.category.path
            qs = (
                Product.objects.for_listing()
                .exclude(pk=product.pk)
                .filter(
                    Q(category=product.category)
                    | Q(category__path__startswith=parent_path)
                    | Q(tags__overlap=product.tags or ["__none__"])
                )
                .order_by("-order_count", "-view_count")[:8]
            )
            data = ProductCardSerializer(qs, many=True, context=self.get_serializer_context()).data
            cache.set(key, data, 900)
        return Response(data)

    @action(detail=False, methods=["get"])
    def featured(self, request):
        key = make_key("catalog", "featured")
        data = cache.get(key)
        if data is None:
            qs = Product.objects.for_listing().filter(is_featured=True).order_by("-order_count")[:12]
            data = ProductCardSerializer(qs, many=True, context=self.get_serializer_context()).data
            cache.set(key, data, 600)
        return Response(data)

    @action(detail=False, methods=["get"], url_path="price-range")
    def price_range(self, request):
        from django.db.models import Max, Min

        key = make_key("catalog", "price_range")
        data = cache.get(key)
        if data is None:
            agg = Product.objects.active().aggregate(min=Min("base_price"), max=Max("base_price"))
            data = {"min": agg["min"] or 0, "max": agg["max"] or 0}
            cache.set(key, data, 900)
        return Response(data)
