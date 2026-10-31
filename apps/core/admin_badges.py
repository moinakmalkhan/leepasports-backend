"""Sidebar badge counters (cached 60 s)."""

from django.conf import settings
from django.core.cache import cache


def _cached(key, fn, timeout=60):
    value = cache.get(key)
    if value is None:
        value = fn()
        cache.set(key, value, timeout)
    return value or None


def new_orders(request):
    from apps.orders.models import Order

    return _cached("badge:orders", lambda: Order.objects.filter(status=Order.Status.PENDING).count())


def payments_to_confirm(request):
    from apps.payments.models import Payment

    return _cached("badge:payments", lambda: Payment.objects.filter(status=Payment.Status.SUBMITTED).count())


def open_returns(request):
    from apps.orders.models import ReturnRequest

    return _cached(
        "badge:returns",
        lambda: ReturnRequest.objects.filter(
            status__in=[ReturnRequest.Status.REQUESTED, ReturnRequest.Status.APPROVED, ReturnRequest.Status.RECEIVED]
        ).count(),
    )


def pending_reviews(request):
    from apps.reviews.models import Review

    return _cached("badge:reviews", lambda: Review.objects.filter(status=Review.Status.PENDING).count())


def open_conversations(request):
    from apps.chat.models import Conversation

    return _cached("badge:chat", lambda: Conversation.objects.filter(status=Conversation.Status.OPEN).count())


def low_stock(request):
    from apps.catalog.models import ProductVariant

    return _cached(
        "badge:stock",
        lambda: ProductVariant.objects.filter(
            is_active=True, stock__lte=settings.SHOP["LOW_STOCK_THRESHOLD"], product__is_active=True
        ).count(),
    )


def environment(request):
    return ["Development", "warning"] if settings.DEBUG else ["Live", "success"]
