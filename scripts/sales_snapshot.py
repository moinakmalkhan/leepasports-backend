"""Quick sales snapshot for the last N days (default 30).

python manage.py runscript sales_snapshot --script-args 7
"""

from datetime import timedelta

from django.db.models import Count, Sum
from django.utils import timezone

from apps.orders.models import Order


def run(*args):
    days = int(args[0]) if args else 30
    since = timezone.now() - timedelta(days=days)
    qs = Order.objects.filter(created_at__gte=since).exclude(status=Order.Status.CANCELLED)
    agg = qs.aggregate(n=Count("id"), revenue=Sum("grand_total"), pieces=Sum("total_quantity"))
    print(f"Last {days} days: {agg['n']} orders · {agg['pieces'] or 0} pieces · USD {agg['revenue'] or 0:,.2f}")
    for row in qs.values("status").annotate(n=Count("id")).order_by("-n"):
        print(f"  {row['status']:<18} {row['n']}")
