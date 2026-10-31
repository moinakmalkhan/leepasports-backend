from django.core.cache import cache
from django.db import connection
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    permission_classes = (AllowAny,)
    throttle_classes = ()

    def get(self, request):
        status = {"database": "ok", "cache": "ok"}
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:  # pragma: no cover
            status["database"] = "error"
        try:
            cache.set("health", "1", 5)
            if cache.get("health") != "1":
                status["cache"] = "degraded"
        except Exception:  # pragma: no cover
            status["cache"] = "error"
        code = 200 if status["database"] == "ok" else 503
        return Response(status, status=code)


class LocaleView(APIView):
    """What the client should render: detected country + language, and what's supported."""

    permission_classes = (AllowAny,)
    throttle_classes = ()

    def get(self, request):
        from django.conf import settings

        from .i18n import RTL, detect_country, detect_language

        lang, source = detect_language(request)
        return Response(
            {
                "language": lang,
                "source": source,
                "country": detect_country(request),
                "rtl": lang in RTL,
                "currency": settings.DEFAULT_CURRENCY,
                "supported": [{"code": code, "name": name, "rtl": code in RTL} for code, name in settings.LANGUAGES],
            }
        )
