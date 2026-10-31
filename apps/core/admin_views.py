"""Reports: date-range sales analytics with CSV export, as an Unfold site view."""

from datetime import timedelta

from django import forms
from django.db.models import Count, F, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone
from django.views.generic import TemplateView
from unfold.views import UnfoldSiteViewMixin
from unfold.widgets import UnfoldAdminDateWidget, UnfoldAdminSelectWidget

from apps.orders.models import Order, OrderItem

from .admin_utils import export_csv

REVENUE_STATUSES = [s for s in Order.Status if s not in (Order.Status.CANCELLED, Order.Status.RETURNED)]


class ReportForm(forms.Form):
    start = forms.DateField(widget=UnfoldAdminDateWidget)
    end = forms.DateField(widget=UnfoldAdminDateWidget)
    group_by = forms.ChoiceField(
        choices=[
            ("product", "Product"),
            ("category", "Category"),
            ("company", "Company"),
            ("fabric", "Fabric"),
            ("month", "Month"),
        ],
        widget=UnfoldAdminSelectWidget,
    )


class ReportsView(UnfoldSiteViewMixin, TemplateView):
    title = "Reports"
    template_name = "admin/reports.html"
    permission_required = ("orders.view_order",)

    def get_form(self):
        today = timezone.localdate()
        data = self.request.GET if self.request.GET else None
        return ReportForm(data=data, initial={"start": today - timedelta(days=90), "end": today, "group_by": "product"})

    def get_rows(self, start, end, group_by):
        items = OrderItem.objects.filter(
            order__status__in=REVENUE_STATUSES, order__created_at__date__gte=start, order__created_at__date__lte=end
        )
        if group_by == "product":
            qs = items.values(label=F("product_name"), code=F("sku")).annotate(
                pcs=Sum("quantity"), rev=Sum("line_total"), orders=Count("order", distinct=True)
            )
        elif group_by == "category":
            qs = items.values(label=F("product__category__name")).annotate(
                pcs=Sum("quantity"), rev=Sum("line_total"), orders=Count("order", distinct=True)
            )
        elif group_by == "company":
            qs = items.values(label=F("order__company__name"), code=F("order__company__country")).annotate(
                pcs=Sum("quantity"), rev=Sum("line_total"), orders=Count("order", distinct=True)
            )
        elif group_by == "fabric":
            qs = items.values(label=F("fabric_name")).annotate(
                pcs=Sum("quantity"), rev=Sum("line_total"), orders=Count("order", distinct=True)
            )
        else:
            qs = (
                items.annotate(month=TruncMonth("order__created_at"))
                .values("month")
                .annotate(pcs=Sum("quantity"), rev=Sum("line_total"), orders=Count("order", distinct=True))
                .order_by("month")
            )
            return [{"label": r["month"].strftime("%B %Y"), "code": "", **r} for r in qs]
        return [{"code": "", **r} for r in qs.order_by("-rev")]

    def get(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_bound and form.is_valid():
            params = form.cleaned_data
        else:
            params = {k: form.initial[k] for k in ("start", "end", "group_by")}
        rows = self.get_rows(params["start"], params["end"], params["group_by"])
        if request.GET.get("export") == "csv":
            return export_csv(
                f"sales-by-{params['group_by']}",
                ["Label", "Code", "Items", "Orders", "Revenue"],
                ([r["label"], r.get("code", ""), r["pcs"], r["orders"], r["rev"]] for r in rows),
            )
        totals = {
            "pcs": sum(r["pcs"] or 0 for r in rows),
            "rev": sum(r["rev"] or 0 for r in rows),
            "orders": Order.objects.filter(
                status__in=REVENUE_STATUSES, created_at__date__gte=params["start"], created_at__date__lte=params["end"]
            ).count(),
        }
        table = {
            "headers": ["Label", "Code", "Items", "Orders", "Revenue"],
            "rows": [
                [r["label"], r.get("code") or "—", f"{r['pcs'] or 0:,}", r["orders"], f"{r['rev'] or 0:,.2f}"] for r in rows
            ],
        }
        return self.render_to_response(self.get_context_data(form=form, table=table, totals=totals, params=params))
