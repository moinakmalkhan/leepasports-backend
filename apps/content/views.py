from django.core.cache import cache
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import FAQ, Announcement, Banner, Page
from .serializers import AnnouncementSerializer, BannerSerializer, FAQSerializer, PageSerializer


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
