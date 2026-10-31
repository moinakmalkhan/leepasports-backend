"""Quick sales snapshot for the last N days (default 30).

python manage.py runscript sales_snapshot --script-args 7
"""

from datetime import timedelta

from django.db.models import Avg, Count, Sum
from django.utils import timezone

from apps.orders.models import Order


def run(*args):
    days = int(args[0]) if args else 30
    since = timezone.now() - timedelta(days=days)
    qs = Order.objects.filter(created_at__gte=since).exclude(status__in=[Order.Status.CANCELLED, Order.Status.RETURNED])
    agg = qs.aggregate(n=Count("id"), revenue=Sum("grand_total"), items=Sum("total_quantity"), aov=Avg("grand_total"))
    print(
        f"Last {days} days: {agg['n']} orders · {agg['items'] or 0} items · Rs {agg['revenue'] or 0:,.0f} · AOV Rs {agg['aov'] or 0:,.0f}"
    )
    for row in qs.values("payment_method").annotate(n=Count("id")).order_by("-n"):
        print(f"  {row['payment_method']:<14} {row['n']}")
    for row in qs.values("status").annotate(n=Count("id")).order_by("-n"):
        print(f"  {row['status']:<18} {row['n']}")
