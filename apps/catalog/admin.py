from django.contrib import admin

from .models import Category, Fabric, Product, ProductFabricOption, ProductImage, ProductSizeOption, Size, SizeGroup


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "depth", "sort_order", "is_active")
    list_filter = ("is_active", "depth")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("path", "depth", "uid")
    list_select_related = ("parent",)


@admin.register(Fabric)
class FabricAdmin(admin.ModelAdmin):
    list_display = ("name", "composition", "gsm", "quality", "price_pkr", "price_unit", "is_available_in_pakistan", "is_active")
    list_filter = ("quality", "is_active", "is_available_in_pakistan")
    search_fields = ("name", "composition")
    prepopulated_fields = {"slug": ("name",)}
    list_editable = ("price_pkr",)


class SizeInline(admin.TabularInline):
    model = Size
    extra = 0


@admin.register(SizeGroup)
class SizeGroupAdmin(admin.ModelAdmin):
    inlines = (SizeInline,)
    list_display = ("name", "sort_order")


class ImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


class FabricOptionInline(admin.TabularInline):
    model = ProductFabricOption
    extra = 0
    autocomplete_fields = ("fabric",)


class SizeOptionInline(admin.TabularInline):
    model = ProductSizeOption
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "category", "base_fabric", "base_price", "min_order_quantity", "is_featured", "is_active")
    list_filter = ("is_active", "is_featured", "is_new", "category", "is_made_to_order")
    search_fields = ("name", "sku", "short_description")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("uid", "base_price", "view_count", "order_count", "created_at", "updated_at")
    inlines = (ImageInline, FabricOptionInline, SizeOptionInline)
    list_select_related = ("category", "base_fabric")
    autocomplete_fields = ("category", "base_fabric")
