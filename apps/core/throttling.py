from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle


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
