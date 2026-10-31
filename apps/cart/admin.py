from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display

from .models import Cart, CartItem, SavedList, SavedListItem


class CartItemInline(TabularInline):
    model = CartItem
    extra = 0
    fields = ("product", "fabric", "quantity", "unit_price", "line_total", "updated_at")
    readonly_fields = fields
    can_delete = False
    show_change_link = False


@admin.register(Cart)
class CartAdmin(ModelAdmin):
    list_display = ("owner", "items_count", "value", "updated_at")
    list_filter = ("currency",)
    search_fields = ("company__name", "user__email", "guest_token")
    inlines = (CartItemInline,)
    list_select_related = ("company", "user")
    readonly_fields = ("uid", "guest_token", "created_at", "updated_at")

    @display(description="Owner")
    def owner(self, obj):
        return (
            f"{obj.company.name} · {obj.user.email}"
            if obj.company_id
            else (obj.user.email if obj.user_id else f"Guest {obj.guest_token[:8]}…")
        )

    @display(description="Items")
    def items_count(self, obj):
        return obj.items.count()

    @display(description="Value")
    def value(self, obj):
        return f"{obj.currency} {sum(i.line_total for i in obj.items.all()):,.2f}"


class SavedListItemInline(TabularInline):
    model = SavedListItem
    extra = 0
    fields = ("product", "fabric", "color", "notes")
    readonly_fields = fields


@admin.register(SavedList)
class SavedListAdmin(ModelAdmin):
    list_display = ("name", "company", "created_by", "is_shared", "updated_at")
    search_fields = ("name", "company__name")
    list_select_related = ("company", "created_by")
    inlines = (SavedListItemInline,)
