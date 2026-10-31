from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.filters import ProductFilter
from apps.catalog.models import Product
from apps.catalog.serializers import ProductCardSerializer
from apps.core.mixins import client_identity
from apps.core.pagination import StandardPagination
from apps.core.throttling import SearchRateThrottle

from . import services
from .tasks import log_search


class SuggestView(APIView):
    """Autocomplete: products + categories + collections for the search dropdown."""

    permission_classes = (AllowAny,)
    throttle_classes = (SearchRateThrottle,)

    def get(self, request):
        return Response(services.suggest(request.query_params.get("q", ""), user=request.user, request=request))


class SearchView(APIView):
    """Full results page: ranked FTS + trigram, with the same filters as the catalog list."""

    permission_classes = (AllowAny,)
    throttle_classes = (SearchRateThrottle,)

    def get(self, request):
        q = services.normalize(request.query_params.get("q", ""))
        qs = services.product_search_queryset(q, user=request.user)
        qs = ProductFilter(request.query_params, queryset=qs, request=request).qs
        ordering = request.query_params.get("ordering")
        if ordering in ("price", "-price", "-created_at", "name", "-rating_avg", "-sales_count"):
            qs = qs.order_by(ordering)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        if q and paginator.page.number == 1:
            log_search.delay(q, q, paginator.page.paginator.count, request.user.pk if request.user.is_authenticated else None)
        response = paginator.get_paginated_response(ProductCardSerializer(page, many=True, context={"request": request}).data)
        response.data["query"] = q
        if paginator.page.paginator.count == 0 and q:
            response.data["suggestions"] = services.trending_queries(5)
        return response


class TrendingView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        return Response({"queries": services.trending_queries()})


class RecommendationsView(APIView):
    """`?product=<slug>` → frequently ordered together; otherwise personalised picks."""

    permission_classes = (AllowAny,)

    def get(self, request):
        slug = request.query_params.get("product")
        session_key = client_identity(request)
        if slug:
            product = Product.objects.active().filter(slug=slug).first()
            items = services.recommendations_for_product(product) if product else []
        else:
            items = services.recommendations_for_user(request.user, session_key)
        return Response(ProductCardSerializer(items, many=True, context={"request": request}).data)


class RecentlyViewedView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        items = services.recently_viewed(request.user, client_identity(request))
        return Response(ProductCardSerializer(items, many=True, context={"request": request}).data)
