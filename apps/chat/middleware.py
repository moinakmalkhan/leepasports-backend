"""JWT authentication for websockets.

Browsers cannot set an Authorization header on a WebSocket handshake, so the
client passes the access token as `?token=` (or `Sec-WebSocket-Protocol`). We
validate it exactly like REST does and attach `scope["user"]`.
"""

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken


@database_sync_to_async
def _user_from_token(raw: str):
    from apps.accounts.models import User

    try:
        token = AccessToken(raw)
        return User.objects.get(pk=token["user_id"], is_active=True)
    except (TokenError, InvalidToken, KeyError, User.DoesNotExist):
        return AnonymousUser()


class JWTAuthMiddleware:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode())
        raw = (query.get("token") or [None])[0]
        if not raw:
            for name, value in scope.get("headers", []):
                if name == b"sec-websocket-protocol":
                    parts = [p.strip() for p in value.decode().split(",")]
                    if len(parts) == 2 and parts[0] == "jwt":
                        raw = parts[1]
        scope["user"] = await _user_from_token(raw) if raw else AnonymousUser()
        return await self.inner(scope, receive, send)
