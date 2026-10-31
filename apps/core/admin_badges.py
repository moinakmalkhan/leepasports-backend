"""Sidebar badge counters (cached 60 s so the sidebar never costs a query burst)."""

from django.conf import settings
from django.core.cache import cache


def _cached(key, fn, timeout=60):
    value = cache.get(key)
    if value is None:
        value = fn()
        cache.set(key, value, timeout)
    return value or None


def open_orders(request):
    from apps.orders.models import Order

    return _cached(
        "badge:orders", lambda: Order.objects.filter(status__in=[Order.Status.PENDING_PAYMENT, Order.Status.CONFIRMED]).count()
    )


def pending_quotes(request):
    from apps.quotes.models import Quote

    return _cached(
        "badge:quotes", lambda: Quote.objects.filter(status__in=[Quote.Status.SUBMITTED, Quote.Status.UNDER_REVIEW]).count()
    )


def payments_to_confirm(request):
    from apps.payments.models import Payment

    return _cached("badge:payments", lambda: Payment.objects.filter(status=Payment.Status.SUBMITTED).count())


def open_conversations(request):
    from apps.chat.models import Conversation

    return _cached("badge:chat", lambda: Conversation.objects.filter(status=Conversation.Status.OPEN).count())


def unverified_companies(request):
    from apps.accounts.models import Company

    return _cached("badge:companies", lambda: Company.objects.filter(is_verified=False, is_active=True).count())


def environment(request):
    return ["Development", "warning"] if settings.DEBUG else ["Production", "success"]
