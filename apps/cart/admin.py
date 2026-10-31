from django.contrib import admin

from .models import Cart, CartItem, SavedList


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ("product", "fabric", "quantity", "unit_price", "line_total")


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("uid", "company", "user", "updated_at")
    inlines = (CartItemInline,)
    list_select_related = ("company", "user")


@admin.register(SavedList)
class SavedListAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "created_by", "updated_at")
    list_select_related = ("company", "created_by")
