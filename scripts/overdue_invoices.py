"""Flag net-terms orders past their due date as overdue and list them.

python manage.py runscript overdue_invoices
"""

from django.utils import timezone

from apps.orders.models import Order


def run(*args):
    today = timezone.localdate()
    qs = Order.objects.filter(
        due_date__lt=today, payment_status__in=[Order.PaymentStatus.UNPAID, Order.PaymentStatus.DEPOSIT_PAID]
    ).exclude(status=Order.Status.CANCELLED)
    updated = qs.update(payment_status=Order.PaymentStatus.OVERDUE)
    for order in Order.objects.filter(payment_status=Order.PaymentStatus.OVERDUE).select_related("company").order_by("due_date"):
        print(f"{order.number:<22} {order.company.name:<30} due {order.due_date}  {order.currency} {order.balance_due:,.2f}")
    print(f"\n{updated} order(s) newly marked overdue.")
