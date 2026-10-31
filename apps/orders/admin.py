from django.contrib import admin, messages
from django.db import transaction
from django.db.models import Count
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import ChoicesDropdownFilter, RangeDateFilter, RangeNumericFilter, RelatedDropdownFilter
from unfold.decorators import action, display
from unfold.enums import ActionVariant

from apps.core.admin_forms import CancelOrderForm, NoteForm, ShipOrderForm
from apps.core.admin_utils import STATUS_COLORS, export_csv
from apps.core.exceptions import BusinessError

from . import services
from .models import Order, OrderItem, OrderStatusHistory, ShippingMethod


class LateFilter(admin.SimpleListFilter):
    title = "schedule"
    parameter_name = "late"

    def lookups(self, request, model_admin):
        return (("1", "Behind estimated ship date"),)

    def queryset(self, request, queryset):
        if self.value() == "1":
            return queryset.filter(
                status__in=[Order.Status.CONFIRMED, Order.Status.IN_PRODUCTION, Order.Status.QUALITY_CHECK],
                estimated_ship_date__lt=timezone.localdate(),
            )
        return queryset


class ItemInline(TabularInline):
    model = OrderItem
    extra = 0
    fields = ("image", "product_name", "sku", "fabric_name", "color", "sizes", "quantity", "unit_price", "line_total", "artwork")
    readonly_fields = (
        "image",
        "product_name",
        "sku",
        "fabric_name",
        "color",
        "sizes",
        "quantity",
        "unit_price",
        "line_total",
        "artwork",
    )
    can_delete = False
    max_num = 0
    tab = True

    @display(description="")
    def image(self, obj):
        return format_html('<img src="{}" class="h-10 w-10 rounded object-cover"/>', obj.image_url) if obj.image_url else "—"

    @display(description="Size breakdown")
    def sizes(self, obj):
        return format_html(
            "<br>".join(
                f"{line.get('gender', '').title()} {line.get('size')}: <b>{line.get('quantity')}</b>" for line in obj.breakdown
            )
        )


class HistoryInline(TabularInline):
    model = OrderStatusHistory
    extra = 0
    fields = ("created_at", "from_status", "to_status", "note", "changed_by", "is_customer_visible")
    readonly_fields = ("created_at", "from_status", "to_status", "changed_by")
    can_delete = False
    max_num = 0
    tab = True
    ordering = ("-created_at",)


@admin.register(Order)
class OrderAdmin(ModelAdmin):
    list_display = (
        "number",
        "company",
        "status_badge",
        "payment_badge",
        "method",
        "total",
        "total_quantity",
        "po_number",
        "ship_by",
        "created_at",
    )
    list_filter = (
        ("status", ChoicesDropdownFilter),
        ("payment_status", ChoicesDropdownFilter),
        ("payment_method", ChoicesDropdownFilter),
        LateFilter,
        ("company", RelatedDropdownFilter),
        ("created_at", RangeDateFilter),
        ("grand_total", RangeNumericFilter),
    )
    list_filter_submit = True
    list_filter_sheet = False
    search_fields = (
        "number",
        "po_number",
        "company__name",
        "placed_by__email",
        "items__product_name",
        "items__sku",
        "tracking_number",
    )
    readonly_fields = (
        "uid",
        "number",
        "company",
        "placed_by",
        "quote",
        "status",
        "payment_status",
        "payment_method",
        "payment_terms",
        "currency",
        "subtotal",
        "discount_total",
        "shipping_total",
        "tax_total",
        "grand_total",
        "amount_paid",
        "total_quantity",
        "shipping_address_pretty",
        "billing_address_pretty",
        "approved_by",
        "approved_at",
        "confirmed_at",
        "shipped_at",
        "delivered_at",
        "cancelled_at",
        "created_at",
        "updated_at",
        "payments_summary",
    )
    inlines = (ItemInline, HistoryInline)
    list_select_related = ("company", "placed_by")
    date_hierarchy = "created_at"
    actions = ("bulk_start_production", "export_orders", "export_picking_list")
    actions_detail = (
        "confirm_order",
        "start_production",
        "quality_check",
        "ship_order",
        "mark_delivered",
        "complete_order",
        "cancel_order",
        "open_invoice",
        "message_customer",
    )
    actions_row = ("ship_order",)
    compressed_fields = True
    fieldsets = (
        (
            "Order",
            {
                "fields": (
                    ("number", "status", "payment_status"),
                    ("company", "placed_by", "quote"),
                    ("payment_method", "payment_terms", "po_number"),
                    ("requested_delivery_date", "estimated_ship_date", "due_date"),
                )
            },
        ),
        (
            "Totals",
            {
                "fields": (
                    ("subtotal", "discount_total", "shipping_total"),
                    ("tax_total", "grand_total", "amount_paid"),
                    ("total_quantity", "currency"),
                    "payments_summary",
                )
            },
        ),
        (
            "Shipping",
            {
                "fields": (
                    "shipping_method",
                    ("carrier", "tracking_number"),
                    "tracking_url",
                    "shipping_address_pretty",
                    "billing_address_pretty",
                )
            },
        ),
        ("Notes", {"fields": ("customer_notes", "internal_notes", "cancel_reason")}),
        (
            "Timeline",
            {
                "classes": ("collapse",),
                "fields": (
                    ("approved_by", "approved_at"),
                    ("confirmed_at", "shipped_at"),
                    ("delivered_at", "cancelled_at"),
                    ("created_at", "updated_at"),
                    "uid",
                ),
            },
        ),
    )

    def has_add_permission(self, request):
        return False  # Orders are created through the storefront / quotes.

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_items=Count("items"))

    # --- columns -----------------------------------------------------------
    @display(description="Status", label=STATUS_COLORS)
    def status_badge(self, obj):
        return obj.status, obj.get_status_display()

    @display(description="Payment", label=STATUS_COLORS)
    def payment_badge(self, obj):
        return obj.payment_status, obj.get_payment_status_display()

    @display(description="Method")
    def method(self, obj):
        return obj.get_payment_method_display()

    @display(description="Total", ordering="grand_total")
    def total(self, obj):
        return f"{obj.currency} {obj.grand_total:,.2f}"

    @display(description="Ship by", ordering="estimated_ship_date")
    def ship_by(self, obj):
        if not obj.estimated_ship_date or not obj.is_open or obj.status == Order.Status.SHIPPED:
            return obj.estimated_ship_date or "—"
        late = obj.estimated_ship_date < timezone.localdate()
        return format_html('<span class="{}">{}</span>', "text-red-600 font-semibold" if late else "", obj.estimated_ship_date)

    def _address(self, data):
        if not data:
            return "—"
        lines = [
            data.get("contact_name"),
            data.get("line1"),
            data.get("line2"),
            f"{data.get('city', '')} {data.get('state', '')} {data.get('postal_code', '')}".strip(),
            data.get("country"),
            data.get("contact_phone"),
        ]
        return format_html("<br>".join(line for line in lines if line))

    @display(description="Ship to")
    def shipping_address_pretty(self, obj):
        return self._address(obj.shipping_address)

    @display(description="Bill to")
    def billing_address_pretty(self, obj):
        return self._address(obj.billing_address)

    @display(description="Payments")
    def payments_summary(self, obj):
        rows = [
            f'<a class="underline" href="{reverse("admin:payments_payment_change", args=[p.pk])}">{p.get_kind_display()} · {p.currency} {p.amount:,.2f} · {p.get_status_display()}</a>'
            for p in obj.payments.all()
        ]
        return format_html("<br>".join(rows)) if rows else "—"

    # --- workflow actions ---------------------------------------------------
    def _transition(self, request, object_id, status, note="", **fields):
        order = Order.objects.get(pk=object_id)
        try:
            services.transition(order, status, by=request.user, note=note, **fields)
            self.message_user(
                request, f"{order.number} → {Order.Status(status).label}. The customer has been notified.", messages.SUCCESS
            )
        except BusinessError as exc:
            self.message_user(request, str(exc.detail), messages.ERROR)
        return redirect(reverse("admin:orders_order_change", args=[object_id]))

    @action(
        description="Confirm order",
        icon="check_circle",
        variant=ActionVariant.SUCCESS,
        permissions=("change",),
        dialog={
            "title": "Confirm order",
            "description": "Marks payment arrangements as accepted and schedules production.",
            "form_class": NoteForm,
            "form_submit_text": "Confirm",
        },
    )
    def confirm_order(self, request, form, object_id):
        return self._transition(request, object_id, Order.Status.CONFIRMED, form.cleaned_data.get("note", ""))

    @action(
        description="Start production", icon="precision_manufacturing", variant=ActionVariant.PRIMARY, permissions=("change",)
    )
    def start_production(self, request, object_id):
        return self._transition(request, object_id, Order.Status.IN_PRODUCTION, "Cutting and stitching started")

    @action(description="Move to QC", icon="fact_check", permissions=("change",))
    def quality_check(self, request, object_id):
        return self._transition(request, object_id, Order.Status.QUALITY_CHECK, "Final inspection and packing")

    @action(
        description="Ship",
        icon="local_shipping",
        variant=ActionVariant.PRIMARY,
        permissions=("change",),
        dialog={
            "title": "Ship order",
            "description": "Tracking details are emailed to the customer immediately.",
            "form_class": ShipOrderForm,
            "form_submit_text": "Mark as shipped",
        },
    )
    def ship_order(self, request, form, object_id):
        d = form.cleaned_data
        return self._transition(
            request,
            object_id,
            Order.Status.SHIPPED,
            d.get("note") or f"Shipped via {d['carrier']}",
            carrier=d["carrier"],
            tracking_number=d["tracking_number"],
            tracking_url=d.get("tracking_url", ""),
        )

    @action(description="Mark delivered", icon="inventory", permissions=("change",))
    def mark_delivered(self, request, object_id):
        return self._transition(request, object_id, Order.Status.DELIVERED, "Delivered")

    @action(description="Complete", icon="task_alt", variant=ActionVariant.SUCCESS, permissions=("change",))
    def complete_order(self, request, object_id):
        return self._transition(request, object_id, Order.Status.COMPLETED, "Order completed")

    @action(
        description="Cancel order",
        icon="cancel",
        variant=ActionVariant.DANGER,
        permissions=("change",),
        dialog={
            "title": "Cancel order",
            "description": "Releases credit and restores sales counters. The customer is notified.",
            "form_class": CancelOrderForm,
            "form_submit_text": "Cancel order",
        },
    )
    def cancel_order(self, request, form, object_id):
        order = Order.objects.get(pk=object_id)
        try:
            services.cancel(order, by=request.user, reason=form.cleaned_data["reason"])
            self.message_user(request, f"{order.number} cancelled.", messages.SUCCESS)
        except BusinessError as exc:
            self.message_user(request, str(exc.detail), messages.ERROR)
        return redirect(reverse("admin:orders_order_change", args=[object_id]))

    @action(description="Invoice (API)", icon="receipt_long")
    def open_invoice(self, request, object_id):
        order = Order.objects.get(pk=object_id)
        return redirect(f"/api/v1/orders/{order.uid}/invoice/")

    @action(description="Message customer", icon="forum")
    def message_customer(self, request, object_id):
        return redirect(reverse("admin:chat_conversation_changelist") + f"?order__id__exact={object_id}")

    # --- bulk actions ---------------------------------------------------------
    @action(description="Start production for selected", icon="precision_manufacturing")
    def bulk_start_production(self, request, queryset):
        done = skipped = 0
        with transaction.atomic():
            for order in queryset:
                try:
                    services.transition(order, Order.Status.IN_PRODUCTION, by=request.user, note="Cutting and stitching started")
                    done += 1
                except BusinessError:
                    skipped += 1
        self.message_user(
            request,
            f"{done} order(s) moved to production, {skipped} skipped (wrong status).",
            messages.SUCCESS if done else messages.WARNING,
        )

    @action(description="Export selected to CSV", icon="download")
    def export_orders(self, request, queryset):
        return export_csv(
            "orders",
            [
                "Number",
                "Company",
                "Status",
                "Payment status",
                "Method",
                "PO",
                "Currency",
                "Subtotal",
                "Shipping",
                "Total",
                "Paid",
                "Pieces",
                "Placed",
                "Est. ship",
                "Tracking",
            ],
            (
                (
                    o.number,
                    o.company.name,
                    o.status,
                    o.payment_status,
                    o.payment_method,
                    o.po_number,
                    o.currency,
                    o.subtotal,
                    o.shipping_total,
                    o.grand_total,
                    o.amount_paid,
                    o.total_quantity,
                    o.created_at.date(),
                    o.estimated_ship_date,
                    o.tracking_number,
                )
                for o in queryset.select_related("company")
            ),
        )

    @action(description="Export picking list (sizes)", icon="list_alt")
    def export_picking_list(self, request, queryset):
        rows = []
        for item in OrderItem.objects.filter(order__in=queryset).select_related("order").order_by("order__number", "id"):
            for line in item.breakdown:
                rows.append(
                    (
                        item.order.number,
                        item.sku,
                        item.product_name,
                        item.fabric_name,
                        item.color,
                        line.get("gender"),
                        line.get("size"),
                        line.get("quantity"),
                    )
                )
        return export_csv("picking-list", ["Order", "SKU", "Product", "Fabric", "Color", "Gender", "Size", "Qty"], rows)


@admin.register(ShippingMethod)
class ShippingMethodAdmin(ModelAdmin):
    list_display = ("name", "code", "base_price", "price_per_kg", "transit", "is_active", "sort_order")
    list_editable = ("base_price", "price_per_kg", "is_active", "sort_order")

    @display(description="Transit")
    def transit(self, obj):
        return f"{obj.min_days}–{obj.max_days} days"
