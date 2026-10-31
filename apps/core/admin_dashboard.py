"""Store dashboard: sales KPIs, work queues, charts and top lists."""

import json
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncDate
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from apps.accounts.models import NewsletterSubscriber, User
from apps.cart.models import Cart
from apps.catalog.models import ProductVariant
from apps.chat.models import Conversation
from apps.orders.models import Order, OrderItem, ReturnRequest
from apps.payments.models import Payment
from apps.reviews.models import Review

from .admin_utils import STATUS_COLORS

REVENUE_STATUSES = [s for s in Order.Status if s not in (Order.Status.CANCELLED, Order.Status.RETURNED)]


def _money(value):
    return f"Rs {Decimal(value or 0):,.0f}"


def _badge(status, label=None):
    return format_html(
        '<span class="inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-{}-100 text-{}-700 dark:bg-{}-500/20 dark:text-{}-300">{}</span>',
        *(STATUS_COLORS.get(status, "default"),) * 4,
        label or status.replace("_", " ").title(),
    )


def _link(url, text):
    return format_html(
        '<a class="text-primary-600 font-medium hover:underline dark:text-primary-400" href="{}">{}</a>', url, text
    )


def _pct(current, previous):
    if not previous:
        return None
    return round((current - previous) / previous * 100, 1)


def dashboard_callback(request, context):
    now = timezone.now()
    today = now.date()
    d7, d30, d60 = now - timedelta(days=7), now - timedelta(days=30), now - timedelta(days=60)
    revenue = Order.objects.filter(status__in=REVENUE_STATUSES)
    stats = revenue.aggregate(
        rev_30=Sum("grand_total", filter=Q(created_at__gte=d30)),
        rev_prev=Sum("grand_total", filter=Q(created_at__gte=d60, created_at__lt=d30)),
        orders_30=Count("id", filter=Q(created_at__gte=d30)),
        orders_prev=Count("id", filter=Q(created_at__gte=d60, created_at__lt=d30)),
        today_rev=Sum("grand_total", filter=Q(created_at__date=today)),
        today_n=Count("id", filter=Q(created_at__date=today)),
        pcs_30=Sum("total_quantity", filter=Q(created_at__gte=d30)),
    )
    aov = (stats["rev_30"] or 0) / stats["orders_30"] if stats["orders_30"] else 0
    queues = {
        "new": Order.objects.filter(status=Order.Status.PENDING).count(),
        "to_pack": Order.objects.filter(status=Order.Status.CONFIRMED).count(),
        "packing": Order.objects.filter(status=Order.Status.PROCESSING).count(),
        "shipped": Order.objects.filter(status__in=[Order.Status.SHIPPED, Order.Status.OUT_FOR_DELIVERY]).count(),
        "payments": Payment.objects.filter(status=Payment.Status.SUBMITTED).count(),
        "returns": ReturnRequest.objects.filter(
            status__in=[ReturnRequest.Status.REQUESTED, ReturnRequest.Status.APPROVED, ReturnRequest.Status.RECEIVED]
        ).count(),
        "reviews": Review.objects.filter(status=Review.Status.PENDING).count(),
        "chats": Conversation.objects.filter(status=Conversation.Status.OPEN).count(),
        "low_stock": ProductVariant.objects.filter(
            is_active=True, product__is_active=True, stock__lte=settings.SHOP["LOW_STOCK_THRESHOLD"]
        ).count(),
    }
    customers_7 = User.objects.filter(created_at__gte=d7, is_staff=False).count()
    subscribers = NewsletterSubscriber.objects.filter(is_active=True).count()
    abandoned = (
        Cart.objects.annotate(n=Count("items"))
        .filter(n__gt=0, updated_at__lt=now - timedelta(hours=2), updated_at__gte=d7)
        .count()
    )

    daily = (
        revenue.filter(created_at__gte=d30)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Sum("grand_total"), n=Count("id"))
        .order_by("day")
    )
    by_day = {r["day"]: r for r in daily}
    labels, rev_series, count_series = [], [], []
    for i in range(29, -1, -1):
        day = today - timedelta(days=i)
        labels.append(day.strftime("%d %b"))
        row = by_day.get(day)
        rev_series.append(float(row["total"]) if row else 0)
        count_series.append(row["n"] if row else 0)

    cats = (
        OrderItem.objects.filter(order__created_at__gte=d30, order__status__in=REVENUE_STATUSES, product__isnull=False)
        .values(name=F("product__category__name"))
        .annotate(pcs=Sum("quantity"))
        .order_by("-pcs")[:8]
    )
    methods = list(revenue.filter(created_at__gte=d30).values("payment_method").annotate(n=Count("id")).order_by("-n"))
    top_products = (
        OrderItem.objects.filter(order__created_at__gte=d30, order__status__in=REVENUE_STATUSES)
        .values("product_name", "sku")
        .annotate(pcs=Sum("quantity"), rev=Sum("line_total"))
        .order_by("-pcs")[:6]
    )
    top_cities = (
        revenue.filter(created_at__gte=d30)
        .values(city=F("shipping_address__city"))
        .annotate(n=Count("id"), rev=Sum("grand_total"))
        .order_by("-n")[:6]
    )
    recent = Order.objects.order_by("-created_at")[:8]
    low = (
        ProductVariant.objects.filter(is_active=True, product__is_active=True, stock__lte=settings.SHOP["LOW_STOCK_THRESHOLD"])
        .select_related("product")
        .order_by("stock")[:8]
    )
    pending_reviews = (
        Review.objects.filter(status=Review.Status.PENDING).select_related("product", "user").order_by("created_at")[:5]
    )

    context.update(
        {
            "kpis": [
                {
                    "title": "Revenue (30d)",
                    "value": _money(stats["rev_30"]),
                    "change": _pct(stats["rev_30"] or 0, stats["rev_prev"] or 0),
                    "icon": "payments",
                    "footer": f"{stats['pcs_30'] or 0:,} items sold",
                },
                {
                    "title": "Orders (30d)",
                    "value": f"{stats['orders_30']:,}",
                    "change": _pct(stats["orders_30"], stats["orders_prev"]),
                    "icon": "shopping_bag",
                    "footer": f"{stats['today_n']} today · {_money(stats['today_rev'])}",
                },
                {"title": "Avg order value", "value": _money(aov), "icon": "receipt_long", "footer": "last 30 days"},
                {
                    "title": "New orders to confirm",
                    "value": queues["new"],
                    "icon": "ring_volume",
                    "href": reverse("admin:orders_order_changelist") + "?status__exact=pending",
                    "footer": "COD confirmation calls",
                    "tone": "warning" if queues["new"] else None,
                },
                {
                    "title": "Payments to verify",
                    "value": queues["payments"],
                    "icon": "fact_check",
                    "href": reverse("admin:payments_payment_changelist") + "?status__exact=submitted",
                    "footer": "bank transfer receipts",
                    "tone": "warning" if queues["payments"] else None,
                },
                {
                    "title": "New customers (7d)",
                    "value": customers_7,
                    "icon": "person_add",
                    "href": reverse("admin:accounts_user_changelist"),
                    "footer": f"{subscribers:,} newsletter subscribers",
                },
            ],
            "queues": [
                {
                    "label": "Awaiting confirmation",
                    "count": queues["new"],
                    "href": reverse("admin:orders_order_changelist") + "?status__exact=pending",
                },
                {
                    "label": "Ready to pack",
                    "count": queues["to_pack"],
                    "href": reverse("admin:orders_order_changelist") + "?status__exact=confirmed",
                },
                {
                    "label": "Being packed",
                    "count": queues["packing"],
                    "href": reverse("admin:orders_order_changelist") + "?status__exact=processing",
                },
                {
                    "label": "In transit",
                    "count": queues["shipped"],
                    "href": reverse("admin:orders_order_changelist") + "?status__in=shipped,out_for_delivery",
                },
                {
                    "label": "Returns to handle",
                    "count": queues["returns"],
                    "href": reverse("admin:orders_returnrequest_changelist") + "?status__in=requested,approved,received",
                },
                {
                    "label": "Reviews to moderate",
                    "count": queues["reviews"],
                    "href": reverse("admin:reviews_review_changelist") + "?status__exact=pending",
                },
                {
                    "label": "Open support chats",
                    "count": queues["chats"],
                    "href": reverse("admin:chat_conversation_changelist") + "?status__exact=open",
                },
                {
                    "label": "Low-stock variants",
                    "count": queues["low_stock"],
                    "href": reverse("admin:catalog_productvariant_changelist")
                    + f"?stock_to={settings.SHOP['LOW_STOCK_THRESHOLD']}",
                },
                {"label": "Abandoned bags (7d)", "count": abandoned, "href": reverse("admin:cart_cart_changelist")},
            ],
            "revenue_chart": json.dumps(
                {
                    "labels": labels,
                    "datasets": [
                        {
                            "label": "Revenue",
                            "data": rev_series,
                            "borderColor": "oklch(64.5% .246 16.439)",
                            "backgroundColor": "oklch(64.5% .246 16.439 / .15)",
                            "fill": True,
                            "tension": 0.35,
                            "pointRadius": 0,
                        }
                    ],
                }
            ),
            "orders_chart": json.dumps(
                {
                    "labels": labels,
                    "datasets": [
                        {
                            "label": "Orders",
                            "data": count_series,
                            "backgroundColor": "oklch(55.3% .013 58.071 / .7)",
                            "borderRadius": 4,
                        }
                    ],
                }
            ),
            "category_chart": json.dumps(
                {
                    "labels": [c["name"] for c in cats],
                    "datasets": [
                        {
                            "label": "Items",
                            "data": [c["pcs"] for c in cats],
                            "backgroundColor": "oklch(64.5% .246 16.439 / .8)",
                            "borderRadius": 4,
                        }
                    ],
                }
            ),
            "payment_mix": [{"label": Order.PaymentMethod(m["payment_method"]).label, "n": m["n"]} for m in methods],
            "recent_orders": {
                "headers": ["Order", "Customer", "City", "Status", "Payment", "Total", "Placed"],
                "rows": [
                    [
                        _link(reverse("admin:orders_order_change", args=[o.pk]), o.number),
                        o.shipping_address.get("full_name", o.email),
                        o.shipping_address.get("city", ""),
                        _badge(o.status, o.get_status_display()),
                        _badge(o.payment_status, o.get_payment_status_display()),
                        _money(o.grand_total),
                        o.created_at.strftime("%d %b %H:%M"),
                    ]
                    for o in recent
                ],
            },
            "top_products": {
                "headers": ["Product", "SKU", "Sold", "Revenue"],
                "rows": [[t["product_name"], t["sku"], f"{t['pcs']:,}", _money(t["rev"])] for t in top_products],
            },
            "top_cities": {
                "headers": ["City", "Orders", "Revenue"],
                "rows": [[c["city"] or "—", c["n"], _money(c["rev"])] for c in top_cities],
            },
            "low_stock": {
                "headers": ["Product", "Variant", "SKU", "Stock"],
                "rows": [
                    [_link(reverse("admin:catalog_product_change", args=[v.product_id]), v.product.name), v.label, v.sku, v.stock]
                    for v in low
                ],
            },
            "pending_reviews": {
                "headers": ["Product", "Rating", "By", "Waiting"],
                "rows": [
                    [
                        _link(reverse("admin:reviews_review_change", args=[r.pk]), r.product.name),
                        "★" * r.rating,
                        r.user.email,
                        f"{(now - r.created_at).days}d",
                    ]
                    for r in pending_reviews
                ],
            },
            "quick_links": [
                {"title": "Add product", "icon": "add_box", "href": reverse("admin:catalog_product_add")},
                {"title": "New coupon", "icon": "confirmation_number", "href": reverse("admin:promotions_coupon_add")},
                {"title": "Edit banners", "icon": "view_carousel", "href": reverse("admin:content_banner_changelist")},
                {"title": "Reports & exports", "icon": "monitoring", "href": reverse("admin:reports")},
                {"title": "Storefront", "icon": "storefront", "href": settings.FRONTEND_URL},
                {"title": "API docs", "icon": "api", "href": "/api/docs/"},
            ],
        }
    )
    return context
