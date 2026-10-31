from django.core.cache import cache
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.cache import make_key
from apps.core.i18n import translate
from apps.core.mixins import client_identity

from . import services
from .filters import ProductFilter
from .models import Category, Collection, Product, SizeGroup, StockAlert
from .serializers import (
    CategoryNodeSerializer,
    CollectionSerializer,
    ProductCardSerializer,
    ProductDetailSerializer,
    SizeGroupSerializer,
    StockAlertSerializer,
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
                "name": translate(category, "name"),
                "slug": category.slug,
                "description": translate(category, "description"),
                "image": request.build_absolute_uri(category.image.url) if category.image else None,
                "meta_title": translate(category, "meta_title"),
                "meta_description": translate(category, "meta_description"),
                "breadcrumbs": services.category_breadcrumbs(category),
                "children": node["children"],
                "product_count": node["product_count"],
            }
        )


class CollectionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = (AllowAny,)
    serializer_class = CollectionSerializer
    lookup_field = "slug"
    pagination_class = None

    def get_queryset(self):
        now = timezone.now()
        return (
            Collection.objects.filter(is_active=True)
            .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
            .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
            .annotate(product_count=Count("products", filter=Q(products__is_active=True)))
        )


class SizeGroupViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = (AllowAny,)
    serializer_class = SizeGroupSerializer
    queryset = SizeGroup.objects.prefetch_related("sizes")
    pagination_class = None


class ProductViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = (AllowAny,)
    lookup_field = "slug"
    filterset_class = ProductFilter
    ordering_fields = ("price", "created_at", "sales_count", "rating_avg", "name")
    ordering = ("-is_featured", "-sales_count")

    def get_queryset(self):
        return Product.objects.for_detail() if self.action == "retrieve" else Product.objects.for_listing()

    def get_serializer_class(self):
        return ProductDetailSerializer if self.action == "retrieve" else ProductCardSerializer

    def retrieve(self, request, *args, **kwargs):
        product = self.get_object()
        services.record_view(product, user=request.user, session_key=client_identity(request))
        return Response(self.get_serializer(product).data)

    @action(detail=False, methods=["get"])
    def facets(self, request):
        """Available sizes/colours/price bounds for the current filters (cached per query string)."""
        key = make_key("catalog", "facets", request.query_params.urlencode())
        data = cache.get(key)
        if data is None:
            qs = self.filter_queryset(Product.objects.active())
            data = services.facets(qs)
            cache.set(key, data, 300)
        return Response(data)

    @action(detail=True, methods=["get"])
    def related(self, request, slug=None):
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
                .order_by("-sales_count", "-view_count")[:8]
            )
            data = ProductCardSerializer(qs, many=True, context=self.get_serializer_context()).data
            cache.set(key, data, 900)
        return Response(data)

    @action(detail=False, methods=["get"])
    def featured(self, request):
        key = make_key("catalog", "featured")
        data = cache.get(key)
        if data is None:
            qs = Product.objects.for_listing().filter(is_featured=True).order_by("-sales_count")[:12]
            data = ProductCardSerializer(qs, many=True, context=self.get_serializer_context()).data
            cache.set(key, data, 600)
        return Response(data)

    @action(detail=False, methods=["get"], url_path="new-arrivals")
    def new_arrivals(self, request):
        key = make_key("catalog", "new")
        data = cache.get(key)
        if data is None:
            qs = Product.objects.for_listing().order_by("-published_at", "-created_at")[:12]
            data = ProductCardSerializer(qs, many=True, context=self.get_serializer_context()).data
            cache.set(key, data, 600)
        return Response(data)

    @action(detail=False, methods=["get"], url_path="best-sellers")
    def best_sellers(self, request):
        key = make_key("catalog", "best")
        data = cache.get(key)
        if data is None:
            qs = Product.objects.for_listing().order_by("-sales_count", "-rating_avg")[:12]
            data = ProductCardSerializer(qs, many=True, context=self.get_serializer_context()).data
            cache.set(key, data, 600)
        return Response(data)


class StockAlertView(APIView):
    permission_classes = (AllowAny,)

    @extend_schema(request=StockAlertSerializer)
    def post(self, request):
        data = dict(request.data)
        if request.user.is_authenticated and not data.get("email"):
            data["email"] = request.user.email
        serializer = StockAlertSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        StockAlert.objects.get_or_create(
            variant=serializer.validated_data["variant"],
            email=serializer.validated_data["email"].lower(),
            defaults={"user": request.user if request.user.is_authenticated else None},
        )
        return Response({"detail": "We'll email you the moment it's back."}, status=status.HTTP_201_CREATED)
