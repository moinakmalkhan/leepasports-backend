import csv
from decimal import Decimal

from django.http import HttpResponse
from django.utils import timezone


def export_csv(filename: str, headers: list[str], rows) -> HttpResponse:
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}-{timezone.now():%Y%m%d-%H%M}.csv"'
    writer = csv.writer(response)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(["" if v is None else (f"{v:.2f}" if isinstance(v, Decimal) else v) for v in row])
    return response


STATUS_COLORS = {
    # orders
    "pending_approval": "warning",
    "pending_payment": "warning",
    "confirmed": "info",
    "in_production": "info",
    "quality_check": "info",
    "shipped": "primary",
    "delivered": "success",
    "completed": "success",
    "cancelled": "danger",
    # payment / quotes / chat
    "unpaid": "warning",
    "deposit_paid": "info",
    "paid": "success",
    "overdue": "danger",
    "refunded": "default",
    "pending": "warning",
    "submitted": "warning",
    "under_review": "info",
    "quoted": "primary",
    "accepted": "success",
    "declined": "danger",
    "expired": "default",
    "converted": "success",
    "failed": "danger",
    "open": "warning",
    "closed": "default",
}
