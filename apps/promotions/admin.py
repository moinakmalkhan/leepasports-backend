from django.contrib import admin
from django.db.models import Count, Sum
from unfold.admin import ModelAdmin
from unfold.contrib.filters.admin import ChoicesDropdownFilter, RangeDateFilter
from unfold.decorators import display

from .models import Coupon, CouponRedemption


@admin.register(Coupon)
class CouponAdmin(ModelAdmin):
    list_display = (
        "code",
        "kind",
        "value_display",
        "min_subtotal",
        "uses",
        "revenue",
        "live",
        "starts_at",
        "ends_at",
        "is_active",
    )
    list_filter = (("kind", ChoicesDropdownFilter), "is_active", "first_order_only", ("created_at", RangeDateFilter))
    search_fields = ("code", "description")
    autocomplete_fields = ("categories", "products")
    readonly_fields = ("uses_count",)
    list_editable = ("is_active",)
    fieldsets = (
        ("Code", {"fields": (("code", "is_active"), "description", ("kind", "value", "max_discount"))}),
        (
            "Rules",
            {
                "fields": (
                    ("min_subtotal", "max_uses", "max_uses_per_user"),
                    "first_order_only",
                    ("starts_at", "ends_at"),
                    "categories",
                    "products",
                    "uses_count",
                )
            },
        ),
    )

    def get_queryset(self, request):
        return (
            super().get_queryset(request).annotate(_orders=Count("redemptions"), _revenue=Sum("redemptions__order__grand_total"))
        )

    @display(description="Value")
    def value_display(self, obj):
        return {"percent": f"{obj.value:g}%", "fixed": f"Rs {obj.value:,.0f}", "free_shipping": "Free shipping"}[obj.kind]

    @display(description="Used", ordering="_orders")
    def uses(self, obj):
        return f"{obj.uses_count}{f' / {obj.max_uses}' if obj.max_uses else ''}"

    @display(description="Order revenue", ordering="_revenue")
    def revenue(self, obj):
        return f"Rs {obj._revenue or 0:,.0f}"

    @display(description="Live", boolean=True)
    def live(self, obj):
        return obj.is_live


@admin.register(CouponRedemption)
class CouponRedemptionAdmin(ModelAdmin):
    list_display = ("coupon", "order", "email", "discount", "created_at")
    list_select_related = ("coupon", "order")
    search_fields = ("coupon__code", "order__number", "email")

    def has_add_permission(self, request):
        return False
