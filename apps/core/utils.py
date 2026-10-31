import secrets
import string
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone
from django.utils.text import slugify

TWO_PLACES = Decimal("0.01")


def money(value) -> Decimal:
    """Quantise to 2dp with banker-safe rounding for display/storage."""
    return (Decimal(value or 0)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def unique_slug(model, value: str, slug_field: str = "slug", instance=None, max_length: int = 140) -> str:
    base = slugify(value)[: max_length - 6] or "item"
    slug = base
    qs = model._default_manager.all()
    if instance is not None and instance.pk:
        qs = qs.exclude(pk=instance.pk)
    counter = 2
    while qs.filter(**{slug_field: slug}).exists():
        slug = f"{base}-{counter}"
        counter += 1
    return slug


def generate_number(prefix: str) -> str:
    """Human-friendly order/quote number: LS-240531-7F3K9Q."""
    alphabet = string.ascii_uppercase + string.digits
    token = "".join(secrets.choice(alphabet) for _ in range(6))
    return f"{prefix}-{timezone.now():%y%m%d}-{token}"


def client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def after_commit(fn):
    """Run `fn` after the surrounding transaction commits.

    In tests every test runs inside a transaction that is rolled back, so
    `on_commit` hooks would never fire; `RUN_ON_COMMIT_IMMEDIATELY` makes them
    run inline there (and anywhere else you explicitly opt in).
    """
    from django.conf import settings
    from django.db import transaction

    if getattr(settings, "RUN_ON_COMMIT_IMMEDIATELY", False):
        fn()
    else:
        transaction.on_commit(fn)


def jsonable(value):
    """Recursively convert Decimals (→ float) so a dict can live in a JSONField."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value
