from django.contrib import admin
from django.db.models import Count
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display

from .models import Cart, CartItem, Wishlist, WishlistItem


class CartItemInline(TabularInline):
    model = CartItem
    extra = 0
    fields = ("variant", "quantity", "updated_at")
    readonly_fields = fields
    can_delete = False
    max_num = 0


@admin.register(Cart)
class CartAdmin(ModelAdmin):
    """Abandoned-bag view: who left what behind."""

    list_display = ("owner", "lines", "coupon_code", "updated_at")
    search_fields = ("user__email", "guest_token")
    inlines = (CartItemInline,)
    list_select_related = ("user",)
    readonly_fields = ("uid", "guest_token", "created_at", "updated_at")
    ordering = ("-updated_at",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_lines=Count("items")).filter(_lines__gt=0)

    def has_add_permission(self, request):
        return False

    @display(description="Shopper")
    def owner(self, obj):
        return obj.user.email if obj.user_id else f"Guest {obj.guest_token[:8]}…"

    @display(description="Lines", ordering="_lines")
    def lines(self, obj):
        return obj._lines


class WishlistItemInline(TabularInline):
    model = WishlistItem
    extra = 0
    fields = ("product", "variant", "added_at")
    readonly_fields = fields
    can_delete = False
    max_num = 0


@admin.register(Wishlist)
class WishlistAdmin(ModelAdmin):
    list_display = ("user", "count", "updated_at")
    search_fields = ("user__email",)
    inlines = (WishlistItemInline,)
    list_select_related = ("user",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_n=Count("items"))

    def has_add_permission(self, request):
        return False

    @display(description="Items", ordering="_n")
    def count(self, obj):
        return obj._n
