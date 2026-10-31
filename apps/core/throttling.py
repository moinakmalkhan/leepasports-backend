import hmac

from django.conf import settings
from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle, UserRateThrottle


def is_internal(request) -> bool:
    """Server-side rendering (Next.js) sends a shared secret; those requests share one IP and must not be throttled."""
    token = getattr(settings, "INTERNAL_API_TOKEN", "")
    sent = request.headers.get("X-Internal-Token", "")
    return bool(token) and bool(sent) and hmac.compare_digest(token, sent)


class SiteAnonRateThrottle(AnonRateThrottle):
    def allow_request(self, request, view):
        return True if is_internal(request) else super().allow_request(request, view)


class SiteUserRateThrottle(UserRateThrottle):
    def allow_request(self, request, view):
        return True if is_internal(request) else super().allow_request(request, view)


class AuthRateThrottle(AnonRateThrottle):
    """Tight per-IP limit for login / register / password reset."""

    scope = "auth"


class AuthBurstRateThrottle(AnonRateThrottle):
    scope = "auth_burst"


class SearchRateThrottle(SimpleRateThrottle):
    scope = "search"

    def get_cache_key(self, request, view):
        ident = request.user.pk if request.user.is_authenticated else self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class ChatRateThrottle(SimpleRateThrottle):
    scope = "chat"

    def get_cache_key(self, request, view):
        if not request.user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.user.pk}
