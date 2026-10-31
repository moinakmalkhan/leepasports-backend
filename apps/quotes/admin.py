from django.contrib import admin

from .models import Quote, QuoteItem


class QuoteItemInline(admin.TabularInline):
    model = QuoteItem
    extra = 0
    fields = ("product_name", "fabric_name", "quantity", "requested_unit_price", "quoted_unit_price", "line_total")
    readonly_fields = ("product_name", "fabric_name", "quantity", "requested_unit_price", "line_total")


@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    list_display = ("number", "company", "status", "requested_total", "quoted_total", "valid_until", "created_at")
    list_filter = ("status",)
    search_fields = ("number", "company__name")
    inlines = (QuoteItemInline,)
    list_select_related = ("company",)
