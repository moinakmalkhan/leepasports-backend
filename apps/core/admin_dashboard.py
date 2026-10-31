"""Operations dashboard: KPIs, charts and work queues for Leepa staff."""

import json
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncDate
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from apps.accounts.models import Company
from apps.catalog.models import Product
from apps.chat.models import Conversation
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.quotes.models import Quote

from .admin_utils import STATUS_COLORS

REVENUE_STATUSES = [s for s in Order.Status if s not in (Order.Status.CANCELLED, Order.Status.PENDING_APPROVAL)]


def _money(value, currency="USD"):
    return f"{currency} {Decimal(value or 0):,.2f}"


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


def _pct_change(current, previous):
    if not previous:
        return None
    return round((current - previous) / previous * 100, 1)


def dashboard_callback(request, context):
    now = timezone.now()
    today = now.date()
    d7 = now - timedelta(days=7)
    d30 = now - timedelta(days=30)
    d60 = now - timedelta(days=60)

    orders = Order.objects.exclude(status=Order.Status.CANCELLED)
    revenue = orders.filter(status__in=REVENUE_STATUSES)
    stats = revenue.aggregate(
        rev_30=Sum("grand_total", filter=Q(created_at__gte=d30)),
        rev_prev=Sum("grand_total", filter=Q(created_at__gte=d60, created_at__lt=d30)),
        orders_30=Count("id", filter=Q(created_at__gte=d30)),
        orders_prev=Count("id", filter=Q(created_at__gte=d60, created_at__lt=d30)),
        pcs_30=Sum("total_quantity", filter=Q(created_at__gte=d30)),
        today=Count("id", filter=Q(created_at__date=today)),
    )
    queues = {
        "approval": Order.objects.filter(status=Order.Status.PENDING_APPROVAL).count(),
        "awaiting_payment": Order.objects.filter(status=Order.Status.PENDING_PAYMENT).count(),
        "to_produce": Order.objects.filter(status=Order.Status.CONFIRMED).count(),
        "in_production": Order.objects.filter(status__in=[Order.Status.IN_PRODUCTION, Order.Status.QUALITY_CHECK]).count(),
        "shipped": Order.objects.filter(status=Order.Status.SHIPPED).count(),
        "overdue": Order.objects.filter(
            payment_status__in=[Order.PaymentStatus.UNPAID, Order.PaymentStatus.DEPOSIT_PAID], due_date__lt=today
        )
        .exclude(status=Order.Status.CANCELLED)
        .count(),
        "late": Order.objects.filter(
            status__in=[Order.Status.CONFIRMED, Order.Status.IN_PRODUCTION, Order.Status.QUALITY_CHECK],
            estimated_ship_date__lt=today,
        ).count(),
    }
    payments_to_confirm = Payment.objects.filter(status=Payment.Status.SUBMITTED).count()
    quotes_pending = Quote.objects.filter(status__in=[Quote.Status.SUBMITTED, Quote.Status.UNDER_REVIEW]).count()
    chats_open = Conversation.objects.filter(status=Conversation.Status.OPEN).count()
    new_companies = Company.objects.filter(created_at__gte=d7).count()
    unverified = Company.objects.filter(is_verified=False, is_active=True).count()

    # Revenue & orders per day (30 days) — one query.
    daily = (
        revenue.filter(created_at__gte=d30)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Sum("grand_total"), n=Count("id"))
        .order_by("day")
    )
    by_day = {row["day"]: row for row in daily}
    labels, rev_series, count_series = [], [], []
    for i in range(29, -1, -1):
        day = today - timedelta(days=i)
        labels.append(day.strftime("%d %b"))
        row = by_day.get(day)
        rev_series.append(float(row["total"]) if row else 0)
        count_series.append(row["n"] if row else 0)

    # Top categories by pieces (30d).
    from apps.orders.models import OrderItem

    cats = (
        OrderItem.objects.filter(order__created_at__gte=d30, order__status__in=REVENUE_STATUSES, product__isnull=False)
        .values(name=F("product__category__name"))
        .annotate(pcs=Sum("quantity"), rev=Sum("line_total"))
        .order_by("-pcs")[:8]
    )
    top_products = (
        OrderItem.objects.filter(order__created_at__gte=d30, order__status__in=REVENUE_STATUSES)
        .values("product_name", "sku")
        .annotate(pcs=Sum("quantity"), rev=Sum("line_total"))
        .order_by("-pcs")[:6]
    )
    top_companies = (
        revenue.filter(created_at__gte=d30)
        .values("company__name", "company_id")
        .annotate(rev=Sum("grand_total"), n=Count("id"))
        .order_by("-rev")[:6]
    )

    status_mix = list(
        Order.objects.filter(status__in=Order.OPEN_STATUSES).values("status").annotate(n=Count("id")).order_by("status")
    )

    recent_orders = Order.objects.select_related("company").order_by("-created_at")[:8]
    pending_quotes = (
        Quote.objects.filter(status__in=[Quote.Status.SUBMITTED, Quote.Status.UNDER_REVIEW])
        .select_related("company")
        .order_by("created_at")[:6]
    )
    payments = (
        Payment.objects.filter(status=Payment.Status.SUBMITTED).select_related("order__company").order_by("submitted_at")[:6]
    )
    low_stock = Product.objects.filter(is_active=True, is_made_to_order=False, stock_quantity__lte=20).order_by("stock_quantity")[
        :6
    ]

    def order_url(o):
        return reverse("admin:orders_order_change", args=[o.pk])

    context.update(
        {
            "kpis": [
                {
                    "title": "Revenue (30d)",
                    "value": _money(stats["rev_30"]),
                    "change": _pct_change(stats["rev_30"] or 0, stats["rev_prev"] or 0),
                    "icon": "payments",
                    "footer": f"{stats['pcs_30'] or 0:,} pieces ordered",
                },
                {
                    "title": "Orders (30d)",
                    "value": f"{stats['orders_30']:,}",
                    "change": _pct_change(stats["orders_30"], stats["orders_prev"]),
                    "icon": "shopping_bag",
                    "footer": f"{stats['today']} today",
                },
                {
                    "title": "Quotes awaiting reply",
                    "value": quotes_pending,
                    "icon": "request_quote",
                    "href": reverse("admin:quotes_quote_changelist") + "?status__in=submitted,under_review",
                    "footer": "Target: reply within 1 business day",
                    "tone": "warning" if quotes_pending else None,
                },
                {
                    "title": "Payments to confirm",
                    "value": payments_to_confirm,
                    "icon": "fact_check",
                    "href": reverse("admin:payments_payment_changelist") + "?status__exact=submitted",
                    "footer": f"{queues['overdue']} invoices overdue",
                    "tone": "warning" if payments_to_confirm else None,
                },
                {
                    "title": "Open conversations",
                    "value": chats_open,
                    "icon": "forum",
                    "href": reverse("admin:chat_conversation_changelist") + "?status__exact=open",
                    "footer": "Customers waiting on us",
                },
                {
                    "title": "New companies (7d)",
                    "value": new_companies,
                    "icon": "domain_add",
                    "href": reverse("admin:accounts_company_changelist") + "?is_verified__exact=0",
                    "footer": f"{unverified} awaiting verification",
                },
            ],
            "queues": [
                {
                    "label": "Needs company approval",
                    "count": queues["approval"],
                    "status": "pending_approval",
                    "href": reverse("admin:orders_order_changelist") + "?status__exact=pending_approval",
                },
                {
                    "label": "Awaiting payment",
                    "count": queues["awaiting_payment"],
                    "status": "pending_payment",
                    "href": reverse("admin:orders_order_changelist") + "?status__exact=pending_payment",
                },
                {
                    "label": "Ready for production",
                    "count": queues["to_produce"],
                    "status": "confirmed",
                    "href": reverse("admin:orders_order_changelist") + "?status__exact=confirmed",
                },
                {
                    "label": "In production / QC",
                    "count": queues["in_production"],
                    "status": "in_production",
                    "href": reverse("admin:orders_order_changelist") + "?status__in=in_production,quality_check",
                },
                {
                    "label": "Shipped, awaiting delivery",
                    "count": queues["shipped"],
                    "status": "shipped",
                    "href": reverse("admin:orders_order_changelist") + "?status__exact=shipped",
                },
                {
                    "label": "Behind estimated ship date",
                    "count": queues["late"],
                    "status": "overdue",
                    "href": reverse("admin:orders_order_changelist") + "?late=1",
                },
            ],
            "revenue_chart": json.dumps(
                {
                    "labels": labels,
                    "datasets": [
                        {
                            "label": "Revenue",
                            "data": rev_series,
                            "borderColor": "oklch(64.6% .222 41.116)",
                            "backgroundColor": "oklch(64.6% .222 41.116 / .15)",
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
                            "backgroundColor": "oklch(55.4% .046 257.417 / .7)",
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
                            "label": "Pieces",
                            "data": [c["pcs"] for c in cats],
                            "backgroundColor": "oklch(64.6% .222 41.116 / .8)",
                            "borderRadius": 4,
                        }
                    ],
                }
            ),
            "status_mix": [{"label": Order.Status(s["status"]).label, "n": s["n"], "status": s["status"]} for s in status_mix],
            "recent_orders": {
                "headers": ["Order", "Company", "Status", "Payment", "Total", "Placed"],
                "rows": [
                    [
                        _link(order_url(o), o.number),
                        o.company.name,
                        _badge(o.status, o.get_status_display()),
                        _badge(o.payment_status, o.get_payment_status_display()),
                        _money(o.grand_total, o.currency),
                        o.created_at.strftime("%d %b %H:%M"),
                    ]
                    for o in recent_orders
                ],
            },
            "pending_quotes": {
                "headers": ["Quote", "Company", "Pieces", "List total", "Waiting"],
                "rows": [
                    [
                        _link(reverse("admin:quotes_quote_change", args=[q.pk]), q.number),
                        q.company.name,
                        f"{q.total_quantity:,}",
                        _money(q.requested_total, q.currency),
                        f"{(now - q.created_at).days}d {(now - q.created_at).seconds // 3600}h",
                    ]
                    for q in pending_quotes
                ],
            },
            "payments": {
                "headers": ["Order", "Company", "Amount", "Reference", "Submitted"],
                "rows": [
                    [
                        _link(reverse("admin:payments_payment_change", args=[p.pk]), p.order.number),
                        p.order.company.name,
                        _money(p.amount, p.currency),
                        p.reference or "—",
                        p.submitted_at.strftime("%d %b") if p.submitted_at else "—",
                    ]
                    for p in payments
                ],
            },
            "top_products": {
                "headers": ["Product", "SKU", "Pieces", "Revenue"],
                "rows": [[t["product_name"], t["sku"], f"{t['pcs']:,}", _money(t["rev"])] for t in top_products],
            },
            "top_companies": {
                "headers": ["Company", "Orders", "Revenue"],
                "rows": [
                    [
                        _link(reverse("admin:accounts_company_change", args=[c["company_id"]]), c["company__name"]),
                        c["n"],
                        _money(c["rev"]),
                    ]
                    for c in top_companies
                ],
            },
            "low_stock": {
                "headers": ["Product", "SKU", "Stock"],
                "rows": [
                    [_link(reverse("admin:catalog_product_change", args=[p.pk]), p.name), p.sku, p.stock_quantity]
                    for p in low_stock
                ],
            },
            "quick_links": [
                {"title": "Add product", "icon": "add_box", "href": reverse("admin:catalog_product_add")},
                {"title": "Update mill prices", "icon": "texture", "href": reverse("admin:catalog_fabric_changelist")},
                {
                    "title": "Verify companies",
                    "icon": "verified",
                    "href": reverse("admin:accounts_company_changelist") + "?is_verified__exact=0",
                },
                {"title": "Reports & exports", "icon": "monitoring", "href": reverse("admin:reports")},
                {"title": "API docs", "icon": "api", "href": "/api/docs/"},
            ],
        }
    )
    return context
