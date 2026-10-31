from django.contrib import admin

from .models import Order, OrderItem, OrderStatusHistory, ShippingMethod


class ItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product_name", "sku", "fabric_name", "quantity", "unit_price", "line_total", "breakdown")
    can_delete = False


class HistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ("from_status", "to_status", "note", "changed_by", "created_at")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "company",
        "status",
        "payment_status",
        "payment_method",
        "grand_total",
        "total_quantity",
        "created_at",
    )
    list_filter = ("status", "payment_status", "payment_method")
    search_fields = ("number", "po_number", "company__name", "placed_by__email")
    readonly_fields = ("uid", "number", "subtotal", "discount_total", "grand_total", "amount_paid", "created_at", "updated_at")
    inlines = (ItemInline, HistoryInline)
    list_select_related = ("company",)
    date_hierarchy = "created_at"


@admin.register(ShippingMethod)
class ShippingMethodAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "base_price", "price_per_kg", "min_days", "max_days", "is_active")
