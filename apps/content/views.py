from django.core.cache import cache
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import FAQ, Announcement, Banner, Page
from .serializers import AnnouncementSerializer, BannerSerializer, FAQSerializer, PageSerializer


def _shipping_summary() -> dict:
    """Zones for client-side delivery hints (free-delivery progress, ETA); checkout still prices server-side."""
    from apps.orders.models import ShippingZone

    zones = [
        {
            "name": z.name,
            "cities": z.cities,
            "provinces": z.provinces,
            "is_default": z.is_default,
            "rate": float(z.rate),
            "free_over": float(z.free_over) if z.free_over is not None else None,
            "cod_fee": float(z.cod_fee),
            "min_days": z.min_days,
            "max_days": z.max_days,
        }
        for z in ShippingZone.objects.filter(is_active=True).order_by("sort_order")
    ]
    thresholds = [z["free_over"] for z in zones if z["free_over"]]
    return {"free_over_min": min(thresholds) if thresholds else None, "zones": zones}


class StorefrontView(APIView):
    """Everything the shell needs in one call: banners, announcement bar, footer pages. Cached 5 min."""

    permission_classes = (AllowAny,)

    def get(self, request):
        from django.utils import translation

        key = f"content:storefront:{translation.get_language()}"
        data = cache.get(key)
        if data is None:
            now = timezone.now()
            banners = (
                Banner.objects.filter(is_active=True)
                .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
                .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
            )
            data = {
                "banners": BannerSerializer(banners, many=True, context={"request": request}).data,
                "announcements": AnnouncementSerializer(Announcement.objects.filter(is_active=True), many=True).data,
                "shipping": _shipping_summary(),
                "pages": [
                    {"title": PageSerializer(p).data["title"], "slug": p.slug}
                    for p in Page.objects.filter(is_published=True, show_in_footer=True)
                ],
            }
            cache.set(key, data, 300)
        return Response(data)


class PageView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request, slug):
        return Response(PageSerializer(get_object_or_404(Page, slug=slug, is_published=True)).data)


class FAQView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        return Response(FAQSerializer(FAQ.objects.filter(is_active=True), many=True).data)
