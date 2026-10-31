from django.contrib import admin

from .models import CustomerGroup, ExchangeRate, PriceListItem, VolumeTier


@admin.register(CustomerGroup)
class CustomerGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "discount_percent", "is_default")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ("currency", "pkr_per_unit", "source", "updated_at")


@admin.register(VolumeTier)
class VolumeTierAdmin(admin.ModelAdmin):
    list_display = ("product", "min_quantity", "discount_percent")
    autocomplete_fields = ("product",)


@admin.register(PriceListItem)
class PriceListItemAdmin(admin.ModelAdmin):
    list_display = ("product", "company", "customer_group", "unit_price", "min_quantity", "valid_from", "valid_to", "is_active")
    list_filter = ("is_active", "customer_group")
    autocomplete_fields = ("product", "company")
    search_fields = ("product__name", "product__sku", "company__name")
