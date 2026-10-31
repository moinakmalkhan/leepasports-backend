from django.contrib import admin, messages
from django.db import transaction
from django.db.models import Count
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import ChoicesDropdownFilter, RangeDateFilter, RangeNumericFilter
from unfold.decorators import action, display
from unfold.enums import ActionVariant

from apps.core.admin_forms import CancelOrderForm, ResolveReturnForm, ShipOrderForm
from apps.core.admin_utils import STATUS_COLORS, export_csv
from apps.core.exceptions import BusinessError

from . import services
from .models import Order, OrderItem, OrderStatusHistory, ReturnItem, ReturnRequest, ShippingZone

STATUS_COLORS.update(
    {
        "pending": "warning",
        "processing": "info",
        "out_for_delivery": "primary",
        "returned": "default",
        "cod_pending": "warning",
        "partially_refunded": "info",
        "requested": "warning",
        "approved": "info",
        "received": "info",
    }
)


class ItemInline(TabularInline):
    model = OrderItem
    extra = 0
    fields = ("image", "product_name", "variant_label", "sku", "quantity", "unit_price", "line_total", "returned_quantity")
    readonly_fields = fields
    can_delete = False
    max_num = 0
    tab = True

    @display(description="")
    def image(self, obj):
        return format_html('<img src="{}" class="h-10 w-10 rounded object-cover"/>', obj.image_url) if obj.image_url else "—"


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
        "customer",
        "city",
        "status_badge",
        "payment_badge",
        "method",
        "total",
        "total_quantity",
        "created_at",
    )
    list_filter = (
        ("status", ChoicesDropdownFilter),
        ("payment_status", ChoicesDropdownFilter),
        ("payment_method", ChoicesDropdownFilter),
        ("created_at", RangeDateFilter),
        ("grand_total", RangeNumericFilter),
    )
    list_filter_submit = True
    list_filter_sheet = False
    search_fields = (
        "number",
        "email",
        "phone",
        "shipping_address__full_name",
        "shipping_address__city",
        "items__product_name",
        "items__sku",
        "tracking_number",
    )
    readonly_fields = (
        "uid",
        "number",
        "user",
        "email",
        "phone",
        "status",
        "payment_status",
        "payment_method",
        "currency",
        "subtotal",
        "discount_total",
        "shipping_total",
        "cod_fee",
        "grand_total",
        "refunded_total",
        "total_quantity",
        "coupon_code",
        "shipping_zone",
        "address_pretty",
        "confirmed_at",
        "shipped_at",
        "delivered_at",
        "cancelled_at",
        "paid_at",
        "created_at",
        "updated_at",
        "payments_summary",
    )
    inlines = (ItemInline, HistoryInline)
    list_select_related = ("user",)
    date_hierarchy = "created_at"
    actions = ("bulk_confirm", "bulk_processing", "export_orders", "export_packing_list")
    actions_detail = (
        "confirm_order",
        "start_packing",
        "ship_order",
        "out_for_delivery",
        "mark_delivered",
        "cancel_order",
        "message_customer",
    )
    actions_row = ("confirm_order", "ship_order")
    compressed_fields = True
    fieldsets = (
        (
            "Order",
            {
                "fields": (
                    ("number", "status", "payment_status"),
                    ("user", "email", "phone"),
                    ("payment_method", "coupon_code", "source"),
                    ("estimated_delivery", "is_gift"),
                )
            },
        ),
        (
            "Totals",
            {
                "fields": (
                    ("subtotal", "discount_total", "shipping_total"),
                    ("cod_fee", "grand_total", "refunded_total"),
                    ("total_quantity", "currency"),
                    "payments_summary",
                )
            },
        ),
        ("Delivery", {"fields": ("shipping_zone", ("carrier", "tracking_number"), "tracking_url", "address_pretty")}),
        ("Notes", {"fields": ("customer_notes", "internal_notes", "cancel_reason")}),
        (
            "Timeline",
            {
                "classes": ("collapse",),
                "fields": (
                    ("confirmed_at", "paid_at"),
                    ("shipped_at", "delivered_at"),
                    ("cancelled_at", "created_at", "updated_at"),
                    "uid",
                ),
            },
        ),
    )

    def has_add_permission(self, request):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_items=Count("items"))

    @display(description="Customer")
    def customer(self, obj):
        name = obj.shipping_address.get("full_name") or obj.email
        return format_html("<b>{}</b><br><span class='text-xs text-base-500'>{} · {}</span>", name, obj.phone, obj.email)

    @display(description="City")
    def city(self, obj):
        return obj.shipping_address.get("city", "—")

    @display(description="Status", label=STATUS_COLORS)
    def status_badge(self, obj):
        return obj.status, obj.get_status_display()

    @display(description="Payment", label=STATUS_COLORS)
    def payment_badge(self, obj):
        return obj.payment_status, obj.get_payment_status_display()

    @display(description="Method")
    def method(self, obj):
        return {"cod": "COD", "bank_transfer": "Bank", "card": "Card"}.get(obj.payment_method, obj.payment_method)

    @display(description="Total", ordering="grand_total")
    def total(self, obj):
        return f"Rs {obj.grand_total:,.0f}"

    @display(description="Deliver to")
    def address_pretty(self, obj):
        a = obj.shipping_address or {}
        lines = [
            a.get("full_name"),
            a.get("line1"),
            a.get("line2"),
            f"{a.get('city', '')} {a.get('province', '')} {a.get('postal_code', '')}".strip(),
            a.get("phone"),
        ]
        return format_html("<br>".join(line for line in lines if line)) if a else "—"

    @display(description="Payments")
    def payments_summary(self, obj):
        rows = [
            f'<a class="underline" href="{reverse("admin:payments_payment_change", args=[p.pk])}">{p.method} · Rs {p.amount:,.0f} · {p.get_status_display()}</a>'
            for p in obj.payments.all()
        ]
        return format_html("<br>".join(rows)) if rows else ("Cash on delivery" if obj.payment_method == "cod" else "—")

    def _transition(self, request, object_id, status, note="", **fields):
        order = Order.objects.get(pk=object_id)
        try:
            services.transition(order, status, by=request.user, note=note, **fields)
            self.message_user(request, f"{order.number} → {Order.Status(status).label}. Customer notified.", messages.SUCCESS)
        except BusinessError as exc:
            self.message_user(request, str(exc.detail), messages.ERROR)
        return redirect(reverse("admin:orders_order_change", args=[object_id]))

    @action(description="Confirm", icon="check_circle", variant=ActionVariant.SUCCESS, permissions=("change",))
    def confirm_order(self, request, object_id):
        return self._transition(request, object_id, Order.Status.CONFIRMED, "Order confirmed")

    @action(description="Start packing", icon="inventory_2", permissions=("change",))
    def start_packing(self, request, object_id):
        return self._transition(request, object_id, Order.Status.PROCESSING, "Being packed")

    @action(
        description="Ship",
        icon="local_shipping",
        variant=ActionVariant.PRIMARY,
        permissions=("change",),
        dialog={
            "title": "Ship order",
            "description": "Tracking details are sent to the customer immediately.",
            "form_class": ShipOrderForm,
            "form_submit_text": "Mark as shipped",
        },
    )
    def ship_order(self, request, form, object_id):
        d = form.cleaned_data
        extra = {"carrier": d["carrier"], "tracking_number": d["tracking_number"], "tracking_url": d.get("tracking_url", "")}
        if d.get("estimated_delivery"):
            extra["estimated_delivery"] = d["estimated_delivery"]
        return self._transition(request, object_id, Order.Status.SHIPPED, d.get("note") or f"Shipped via {d['carrier']}", **extra)

    @action(description="Out for delivery", icon="two_wheeler", permissions=("change",))
    def out_for_delivery(self, request, object_id):
        return self._transition(request, object_id, Order.Status.OUT_FOR_DELIVERY, "Out for delivery")

    @action(description="Delivered", icon="task_alt", variant=ActionVariant.SUCCESS, permissions=("change",))
    def mark_delivered(self, request, object_id):
        return self._transition(request, object_id, Order.Status.DELIVERED, "Delivered")

    @action(
        description="Cancel",
        icon="cancel",
        variant=ActionVariant.DANGER,
        permissions=("change",),
        dialog={
            "title": "Cancel order",
            "description": "Restocks items and notifies the customer.",
            "form_class": CancelOrderForm,
            "form_submit_text": "Cancel order",
        },
    )
    def cancel_order(self, request, form, object_id):
        order = Order.objects.get(pk=object_id)
        try:
            services.cancel(order, by=request.user, reason=form.cleaned_data["reason"], by_customer=False)
            self.message_user(request, f"{order.number} cancelled and restocked.", messages.SUCCESS)
        except BusinessError as exc:
            self.message_user(request, str(exc.detail), messages.ERROR)
        return redirect(reverse("admin:orders_order_change", args=[object_id]))

    @action(description="Message customer", icon="forum")
    def message_customer(self, request, object_id):
        return redirect(reverse("admin:chat_conversation_changelist") + f"?order__id__exact={object_id}")

    @action(description="Confirm selected", icon="check_circle")
    def bulk_confirm(self, request, queryset):
        done = skipped = 0
        with transaction.atomic():
            for order in queryset:
                try:
                    services.transition(order, Order.Status.CONFIRMED, by=request.user, note="Order confirmed")
                    done += 1
                except BusinessError:
                    skipped += 1
        self.message_user(request, f"{done} confirmed, {skipped} skipped.", messages.SUCCESS if done else messages.WARNING)

    @action(description="Start packing selected", icon="inventory_2")
    def bulk_processing(self, request, queryset):
        done = skipped = 0
        with transaction.atomic():
            for order in queryset:
                try:
                    services.transition(order, Order.Status.PROCESSING, by=request.user, note="Being packed")
                    done += 1
                except BusinessError:
                    skipped += 1
        self.message_user(request, f"{done} moved to packing, {skipped} skipped.", messages.SUCCESS if done else messages.WARNING)

    @action(description="Export selected to CSV", icon="download")
    def export_orders(self, request, queryset):
        return export_csv(
            "orders",
            [
                "Number",
                "Customer",
                "Phone",
                "Email",
                "City",
                "Status",
                "Payment status",
                "Method",
                "Subtotal",
                "Discount",
                "Delivery",
                "COD fee",
                "Total",
                "Items",
                "Placed",
                "Tracking",
            ],
            (
                (
                    o.number,
                    o.shipping_address.get("full_name"),
                    o.phone,
                    o.email,
                    o.shipping_address.get("city"),
                    o.status,
                    o.payment_status,
                    o.payment_method,
                    o.subtotal,
                    o.discount_total,
                    o.shipping_total,
                    o.cod_fee,
                    o.grand_total,
                    o.total_quantity,
                    o.created_at.date(),
                    o.tracking_number,
                )
                for o in queryset
            ),
        )

    @action(description="Export packing list", icon="list_alt")
    def export_packing_list(self, request, queryset):
        rows = [
            (
                i.order.number,
                i.order.shipping_address.get("full_name"),
                i.order.shipping_address.get("city"),
                i.sku,
                i.product_name,
                i.variant_label,
                i.quantity,
            )
            for i in OrderItem.objects.filter(order__in=queryset).select_related("order").order_by("order__number", "id")
        ]
        return export_csv("packing-list", ["Order", "Customer", "City", "SKU", "Product", "Variant", "Qty"], rows)


class ReturnItemInline(TabularInline):
    model = ReturnItem
    extra = 0
    fields = ("order_item", "quantity", "exchange_variant")
    readonly_fields = ("order_item", "quantity", "exchange_variant")
    can_delete = False
    max_num = 0


@admin.register(ReturnRequest)
class ReturnRequestAdmin(ModelAdmin):
    list_display = ("number", "order_link", "kind", "reason", "status_badge", "refund", "created_at", "resolved_at")
    list_filter = (
        ("status", ChoicesDropdownFilter),
        ("kind", ChoicesDropdownFilter),
        ("reason", ChoicesDropdownFilter),
        ("created_at", RangeDateFilter),
    )
    list_filter_submit = True
    search_fields = ("number", "order__number", "order__email", "order__phone")
    readonly_fields = ("uid", "number", "order", "user", "kind", "reason", "details", "image", "created_at", "resolved_at")
    inlines = (ReturnItemInline,)
    list_select_related = ("order",)
    actions_detail = ("resolve",)
    actions_row = ("resolve",)

    def has_add_permission(self, request):
        return False

    @display(description="Order")
    def order_link(self, obj):
        return format_html(
            '<a class="underline" href="{}">{}</a>', reverse("admin:orders_order_change", args=[obj.order_id]), obj.order.number
        )

    @display(description="Status", label=STATUS_COLORS)
    def status_badge(self, obj):
        return obj.status, obj.get_status_display()

    @display(description="Refund")
    def refund(self, obj):
        return f"Rs {obj.refund_amount:,.0f}" if obj.refund_amount else "—"

    @action(
        description="Resolve",
        icon="rule",
        variant=ActionVariant.PRIMARY,
        permissions=("change",),
        dialog={
            "title": "Update return request",
            "description": "Completing a refund restocks the items and records the refund on the order.",
            "form_class": ResolveReturnForm,
            "form_submit_text": "Update",
        },
    )
    def resolve(self, request, form, object_id):
        req = ReturnRequest.objects.get(pk=object_id)
        d = form.cleaned_data
        try:
            services.resolve_return(
                req,
                status=d["status"],
                by=request.user,
                staff_notes=d.get("staff_notes", ""),
                refund_amount=d.get("refund_amount"),
                refund_method=d.get("refund_method", ""),
            )
            self.message_user(
                request, f"{req.number} → {ReturnRequest.Status(d['status']).label}. Customer notified.", messages.SUCCESS
            )
        except BusinessError as exc:
            self.message_user(request, str(exc.detail), messages.ERROR)
        return redirect(reverse("admin:orders_returnrequest_change", args=[object_id]))


@admin.register(ShippingZone)
class ShippingZoneAdmin(ModelAdmin):
    list_display = ("name", "rate", "free_over", "cod_fee", "transit", "is_default", "is_active", "sort_order")
    list_editable = ("rate", "free_over", "cod_fee", "is_active", "sort_order")

    @display(description="Transit")
    def transit(self, obj):
        return f"{obj.min_days}–{obj.max_days} days"
