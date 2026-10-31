from django.db.models import Count
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.catalog.models import Product
from apps.core.pagination import SmallPagination

from . import services
from .models import Review
from .serializers import ReviewCreateSerializer, ReviewSerializer


class ReviewViewSet(mixins.ListModelMixin, mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """`?product=<slug>` → approved reviews for a product; `?mine=1` → the user's own reviews."""

    serializer_class = ReviewSerializer
    pagination_class = SmallPagination
    lookup_field = "uid"
    ordering_fields = ("created_at", "rating", "helpful_count")
    ordering = ("-helpful_count", "-created_at")

    def get_permissions(self):
        return [AllowAny()] if self.action in ("list", "summary") else [IsAuthenticated()]

    def get_queryset(self):
        qs = Review.objects.select_related("user", "product")
        if self.request.query_params.get("mine") == "1" and self.request.user.is_authenticated:
            return qs.filter(user=self.request.user)
        if self.action in ("update", "partial_update", "destroy"):
            return qs.filter(user=self.request.user)
        qs = qs.filter(status=Review.Status.APPROVED)
        product = self.request.query_params.get("product")
        if product:
            qs = qs.filter(product__slug=product)
        rating = self.request.query_params.get("rating")
        if rating:
            qs = qs.filter(rating=rating)
        return qs

    @extend_schema(request=ReviewCreateSerializer, responses=ReviewSerializer)
    def create(self, request):
        serializer = ReviewCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        product = get_object_or_404(Product.objects.active(), slug=data.pop("product"))
        review = services.create_review(user=request.user, product=product, data=data)
        return Response(ReviewSerializer(review, context={"request": request}).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        review = serializer.save(
            status=Review.Status.PENDING if not serializer.instance.is_verified_purchase else Review.Status.APPROVED
        )
        services.recompute_rating(review.product_id)

    def perform_destroy(self, instance):
        product_id = instance.product_id
        instance.delete()
        services.recompute_rating(product_id)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Rating histogram for a product."""
        slug = request.query_params.get("product")
        rows = Review.objects.filter(product__slug=slug, status=Review.Status.APPROVED).values("rating").annotate(n=Count("id"))
        counts = {i: 0 for i in range(1, 6)}
        for row in rows:
            counts[row["rating"]] = row["n"]
        total = sum(counts.values())
        avg = round(sum(r * n for r, n in counts.items()) / total, 2) if total else 0
        return Response({"average": avg, "total": total, "distribution": counts})

    @action(detail=True, methods=["post"])
    def helpful(self, request, uid=None):
        review = get_object_or_404(Review, uid=uid, status=Review.Status.APPROVED)
        added = services.toggle_helpful(review, request.user)
        review.refresh_from_db(fields=["helpful_count"])
        return Response({"helpful": added, "helpful_count": review.helpful_count})
