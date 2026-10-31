from django.contrib import admin, messages
from unfold.admin import ModelAdmin
from unfold.contrib.filters.admin import RelatedDropdownFilter
from unfold.decorators import action, display

from .models import CustomerGroup, ExchangeRate, PriceListItem, VolumeTier


@admin.register(CustomerGroup)
class CustomerGroupAdmin(ModelAdmin):
    list_display = ("name", "discount_percent", "companies_count", "is_default")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)

    @display(description="Companies")
    def companies_count(self, obj):
        return obj.companies.count()


@admin.register(ExchangeRate)
class ExchangeRateAdmin(ModelAdmin):
    list_display = ("currency", "pkr_per_unit", "source", "updated_at")
    list_editable = ("pkr_per_unit",)
    actions_list = ("reprice_catalog",)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from django.core.cache import cache

        cache.delete(f"fx:{obj.currency}")

    @action(description="Re-price whole catalog", icon="sync")
    def reprice_catalog(self, request):
        from django.shortcuts import redirect
        from django.urls import reverse

        from apps.catalog.tasks import reprice_all_products

        reprice_all_products.delay()
        self.message_user(request, "Catalog re-pricing queued.", messages.SUCCESS)
        return redirect(reverse("admin:pricing_exchangerate_changelist"))


@admin.register(VolumeTier)
class VolumeTierAdmin(ModelAdmin):
    list_display = ("scope", "min_quantity", "discount_percent")
    list_filter = (("product", RelatedDropdownFilter),)
    autocomplete_fields = ("product",)
    list_editable = ("discount_percent",)

    @display(description="Scope")
    def scope(self, obj):
        return obj.product.name if obj.product_id else "Global ladder"


@admin.register(PriceListItem)
class PriceListItemAdmin(ModelAdmin):
    list_display = ("product", "target", "unit_price", "currency", "min_quantity", "valid_from", "valid_to", "active")
    list_filter = ("is_active", ("customer_group", RelatedDropdownFilter), ("company", RelatedDropdownFilter))
    autocomplete_fields = ("product", "company", "customer_group")
    search_fields = ("product__name", "product__sku", "company__name")
    list_select_related = ("product", "company", "customer_group")
    actions = ("deactivate",)

    @display(description="Applies to")
    def target(self, obj):
        return obj.company.name if obj.company_id else f"Group: {obj.customer_group.name}"

    @display(description="Active", boolean=True)
    def active(self, obj):
        return obj.is_active

    @action(description="Deactivate selected", icon="block")
    def deactivate(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, "Contract prices deactivated.", messages.SUCCESS)
