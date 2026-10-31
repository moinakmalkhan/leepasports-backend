"""Small helpers around the Django cache so keys stay consistent.

Every cached payload is versioned through a per-namespace counter. Bumping
the counter (`invalidate_namespace`) invalidates all keys in that namespace in
O(1) — no wildcard deletes against Redis.
"""

from functools import wraps

from django.core.cache import cache

NAMESPACES = ("catalog", "pricing", "search")


def _version_key(namespace: str) -> str:
    return f"ns:{namespace}:v"


def namespace_version(namespace: str) -> int:
    version = cache.get(_version_key(namespace))
    if version is None:
        cache.set(_version_key(namespace), 1, None)
        return 1
    return version


def invalidate_namespace(namespace: str) -> None:
    try:
        cache.incr(_version_key(namespace))
    except ValueError:
        cache.set(_version_key(namespace), 2, None)


def make_key(namespace: str, *parts) -> str:
    """Keys are language-scoped so translated payloads never leak across locales."""
    from django.utils import translation

    joined = ":".join(str(p) for p in parts)
    return f"{namespace}:v{namespace_version(namespace)}:{translation.get_language() or 'en'}:{joined}"


def cached(namespace: str, timeout: int = 300):
    """Cache a function's return value keyed on its positional/keyword args."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            key = make_key(namespace, fn.__module__, fn.__qualname__, args, sorted(kwargs.items()))
            hit = cache.get(key)
            if hit is not None:
                return hit
            value = fn(*args, **kwargs)
            cache.set(key, value, timeout)
            return value

        return wrapper

    return decorator
