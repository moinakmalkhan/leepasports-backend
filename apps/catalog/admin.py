from decimal import Decimal

from django.conf import settings
from django.contrib import admin, messages
from django.db import transaction
from django.db.models import Count, Sum
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import ChoicesDropdownFilter, RangeNumericFilter, RelatedDropdownFilter
from unfold.decorators import action, display
from unfold.enums import ActionVariant

from apps.core.admin_forms import PriceAdjustForm, StockAdjustForm
from apps.core.admin_utils import export_csv

from .models import Category, Collection, Color, Product, ProductImage, ProductVariant, Size, SizeGroup, StockAlert


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ("tree_name", "slug", "products_total", "show_in_menu", "sort_order", "active")
    list_filter = ("is_active", "show_in_menu", "depth", ("parent", RelatedDropdownFilter))
    search_fields = ("name", "slug")
    readonly_fields = ("slug", "path", "depth", "uid")
    autocomplete_fields = ("parent",)
    ordering = ("path",)
    list_editable = ("sort_order", "show_in_menu")
    fieldsets = (
        (None, {"fields": ("name", "parent", ("icon", "sort_order"), ("is_active", "show_in_menu"), "description", "image")}),
        ("Translations", {"classes": ("collapse",), "fields": ("translations",)}),
        ("SEO", {"classes": ("collapse",), "fields": ("meta_title", "meta_description")}),
        ("System", {"classes": ("collapse",), "fields": ("slug", "path", "depth", "uid")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_products=Count("products"))

    @display(description="Category", ordering="path")
    def tree_name(self, obj):
        return format_html('<span style="padding-left:{}px">{}{}</span>', obj.depth * 18, "└ " if obj.depth else "", obj.name)

    @display(description="Products", ordering="_products")
    def products_total(self, obj):
        return obj._products

    @display(description="Active", boolean=True)
    def active(self, obj):
        return obj.is_active


@admin.register(Collection)
class CollectionAdmin(ModelAdmin):
    list_display = ("name", "slug", "products_total", "is_featured", "is_active", "starts_at", "ends_at", "sort_order")
    list_filter = ("is_active", "is_featured")
    search_fields = ("name",)
    readonly_fields = ("slug", "uid")
    list_editable = ("is_featured", "sort_order")
    filter_horizontal = ()
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "tagline",
                    "description",
                    "image",
                    ("is_active", "is_featured", "sort_order"),
                    ("starts_at", "ends_at"),
                    "slug",
                )
            },
        ),
        ("Translations", {"classes": ("collapse",), "fields": ("translations",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_products=Count("products"))

    @display(description="Products", ordering="_products")
    def products_total(self, obj):
        return obj._products


@admin.register(Color)
class ColorAdmin(ModelAdmin):
    list_display = ("swatch", "name", "hex", "sort_order")
    list_display_links = ("name",)
    list_editable = ("sort_order",)
    search_fields = ("name",)

    @display(description="")
    def swatch(self, obj):
        return format_html(
            '<span class="inline-block h-6 w-6 rounded-full border border-base-300" style="background:{}"></span>', obj.hex
        )


class SizeInline(TabularInline):
    model = Size
    extra = 0


@admin.register(SizeGroup)
class SizeGroupAdmin(ModelAdmin):
    inlines = (SizeInline,)
    list_display = ("name", "sizes_list", "sort_order")
    search_fields = ("name",)
    readonly_fields = ("slug",)

    @display(description="Sizes")
    def sizes_list(self, obj):
        return " · ".join(obj.sizes.values_list("label", flat=True))


class ImageInline(TabularInline):
    model = ProductImage
    extra = 0
    fields = ("preview", "image", "color", "alt", "sort_order", "is_primary")
    readonly_fields = ("preview",)
    tab = True

    @display(description="")
    def preview(self, obj):
        return format_html('<img src="{}" class="h-12 w-12 rounded object-cover" />', obj.image.url) if obj.image else "—"


class VariantInline(TabularInline):
    model = ProductVariant
    extra = 0
    fields = ("sku", "color", "size", "price_override", "stock", "is_active")
    tab = True

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "size":
            kwargs["queryset"] = Size.objects.select_related("group").order_by("group__sort_order", "sort_order")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ("thumb", "name", "sku", "category", "gender", "price_display", "stock", "sold", "rating", "flags", "active")
    list_display_links = ("name",)
    list_filter = (
        ("category", RelatedDropdownFilter),
        ("gender", ChoicesDropdownFilter),
        ("collections", RelatedDropdownFilter),
        "is_active",
        "is_featured",
        "is_new",
        ("price", RangeNumericFilter),
        ("total_stock", RangeNumericFilter),
    )
    list_filter_submit = True
    search_fields = ("name", "sku", "tags", "variants__sku")
    readonly_fields = (
        "uid",
        "slug",
        "rating_avg",
        "rating_count",
        "view_count",
        "sales_count",
        "total_stock",
        "created_at",
        "updated_at",
        "storefront_link",
    )
    inlines = (ImageInline, VariantInline)
    list_select_related = ("category",)
    autocomplete_fields = ("category", "size_group", "collections")
    actions = ("feature", "unfeature", "activate", "deactivate", "put_on_sale", "export_products")
    actions_detail = ("duplicate", "view_orders")
    compressed_fields = True
    warn_unsaved_form = True
    fieldsets = (
        (
            "Product",
            {
                "fields": (
                    ("name", "sku"),
                    ("category", "gender", "brand"),
                    "collections",
                    "short_description",
                    "description",
                    ("material", "size_group"),
                    "care_instructions",
                    "specifications",
                    "tags",
                    "storefront_link",
                )
            },
        ),
        ("Pricing", {"fields": (("price", "compare_at_price", "cost_price"),)}),
        (
            "Translations (Urdu / Arabic)",
            {
                "classes": ("collapse",),
                "description": 'JSON per language, e.g. {"ur": {"name": "…", "short_description": "…"}, "ar": {…}}. Missing keys fall back to English.',
                "fields": ("translations",),
            },
        ),
        (
            "Visibility",
            {
                "fields": (
                    ("is_active", "is_featured", "is_new"),
                    "published_at",
                    ("rating_avg", "rating_count", "view_count", "sales_count", "total_stock"),
                )
            },
        ),
        ("SEO", {"classes": ("collapse",), "fields": ("meta_title", "meta_description")}),
        ("System", {"classes": ("collapse",), "fields": ("slug", "uid", "weight_grams", "created_at", "updated_at")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("images")

    @display(description="")
    def thumb(self, obj):
        image = obj.primary_image
        return (
            format_html('<img src="{}" class="h-10 w-10 rounded object-cover" />', image.image.url)
            if image
            else format_html(
                '<span class="inline-flex h-10 w-10 items-center justify-center rounded bg-base-100 text-base-400 dark:bg-base-800"><span class="material-symbols-outlined">apparel</span></span>'
            )
        )

    @display(description="Price", ordering="price")
    def price_display(self, obj):
        if obj.is_on_sale:
            return format_html(
                '<b>Rs {}</b> <s class="text-base-400">Rs {}</s> <span class="text-xs text-primary-600">−{}%</span>',
                f"{obj.price:,.0f}",
                f"{obj.compare_at_price:,.0f}",
                obj.discount_percent,
            )
        return f"Rs {obj.price:,.0f}"

    @display(description="Stock", ordering="total_stock")
    def stock(self, obj):
        low = settings.SHOP["LOW_STOCK_THRESHOLD"]
        cls = "text-red-600 font-semibold" if obj.total_stock <= 0 else "text-amber-600" if obj.total_stock <= low * 3 else ""
        return format_html('<span class="{}">{}</span>', cls, obj.total_stock)

    @display(description="Sold", ordering="sales_count")
    def sold(self, obj):
        return obj.sales_count

    @display(description="Rating", ordering="rating_avg")
    def rating(self, obj):
        return f"{obj.rating_avg}★ ({obj.rating_count})" if obj.rating_count else "—"

    @display(description="Flags")
    def flags(self, obj):
        parts = [p for p, on in (("★ Featured", obj.is_featured), ("New", obj.is_new), ("Sale", obj.is_on_sale)) if on]
        return " · ".join(parts) or "—"

    @display(description="Active", boolean=True)
    def active(self, obj):
        return obj.is_active

    @display(description="Storefront")
    def storefront_link(self, obj):
        return (
            format_html(
                '<a class="text-primary-600 underline" target="_blank" href="{}/products/{}">Open on chobbar.shop ↗</a>',
                settings.FRONTEND_URL,
                obj.slug,
            )
            if obj.pk
            else "—"
        )

    @action(description="Feature on home page", icon="star", variant=ActionVariant.PRIMARY)
    def feature(self, request, queryset):
        queryset.update(is_featured=True)
        self.message_user(request, "Products featured.", messages.SUCCESS)

    @action(description="Remove from featured", icon="star_outline")
    def unfeature(self, request, queryset):
        queryset.update(is_featured=False)
        self.message_user(request, "Removed from featured.", messages.SUCCESS)

    @action(description="Publish", icon="visibility", variant=ActionVariant.SUCCESS)
    def activate(self, request, queryset):
        queryset.update(is_active=True)
        self.message_user(request, "Products published.", messages.SUCCESS)

    @action(description="Unpublish", icon="visibility_off", variant=ActionVariant.WARNING)
    def deactivate(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, "Products unpublished.", messages.SUCCESS)

    @action(
        description="Put on sale by percentage",
        icon="sell",
        variant=ActionVariant.PRIMARY,
        dialog={
            "title": "Sale pricing",
            "description": "Keeps the current price as the crossed-out compare-at price (if none is set) and lowers the selling price.",
            "form_class": PriceAdjustForm,
            "form_submit_text": "Apply",
        },
    )
    def put_on_sale(self, request, form, queryset):
        pct = Decimal(form.cleaned_data["percent"])
        with transaction.atomic():
            for p in queryset.select_for_update():
                if pct < 0 and not p.compare_at_price:
                    p.compare_at_price = p.price
                p.price = (p.price * (1 + pct / 100)).quantize(Decimal("1"))
                if p.compare_at_price and p.compare_at_price <= p.price:
                    p.compare_at_price = None
                p.save()
        self.message_user(request, f"Prices adjusted by {pct}% for {queryset.count()} product(s).", messages.SUCCESS)

    @action(description="Export selected to CSV", icon="download")
    def export_products(self, request, queryset):
        return export_csv(
            "products",
            ["SKU", "Name", "Category", "Gender", "Price", "Compare at", "Stock", "Sold", "Rating", "Active"],
            (
                (
                    p.sku,
                    p.name,
                    p.category.name,
                    p.gender,
                    p.price,
                    p.compare_at_price,
                    p.total_stock,
                    p.sales_count,
                    p.rating_avg,
                    p.is_active,
                )
                for p in queryset.select_related("category")
            ),
        )

    @action(description="Duplicate", icon="content_copy", permissions=("change",))
    def duplicate(self, request, object_id):
        import uuid

        with transaction.atomic():
            source = Product.objects.prefetch_related("variants", "collections").get(pk=object_id)
            clone = Product.objects.get(pk=object_id)
            clone.pk = None
            clone.uid = uuid.uuid4()
            clone.name = f"{source.name} (copy)"
            clone.slug = None
            clone.sku = f"{source.sku}-COPY"[:40]
            clone.is_active = clone.is_featured = False
            clone.view_count = clone.sales_count = clone.rating_count = 0
            clone.rating_avg = 0
            clone.save()
            clone.collections.set(source.collections.all())
            ProductVariant.objects.bulk_create(
                [
                    ProductVariant(
                        product=clone,
                        color_id=v.color_id,
                        size_id=v.size_id,
                        sku=f"{v.sku}-COPY"[:60],
                        price_override=v.price_override,
                        stock=0,
                        is_active=v.is_active,
                    )
                    for v in source.variants.all()
                ]
            )
        self.message_user(request, f"Created draft copy {clone.sku}. Set SKUs, stock and images, then publish.", messages.SUCCESS)
        return redirect(reverse("admin:catalog_product_change", args=[clone.pk]))

    @action(description="Order history", icon="shopping_bag")
    def view_orders(self, request, object_id):
        return redirect(reverse("admin:orders_order_changelist") + f"?items__product__id__exact={object_id}")


@admin.register(ProductVariant)
class VariantAdmin(ModelAdmin):
    list_display = ("sku", "product", "color", "size", "price_display", "stock_display", "sold", "is_active")
    list_filter = (
        "is_active",
        ("color", RelatedDropdownFilter),
        ("stock", RangeNumericFilter),
        ("product__category", RelatedDropdownFilter),
    )
    list_filter_submit = True
    search_fields = ("sku", "product__name", "barcode")
    list_select_related = ("product", "color", "size")
    autocomplete_fields = ("product",)
    list_editable = ("stock",) if False else ()
    actions = ("export_inventory", "deactivate")
    actions_detail = ("adjust_stock",)
    actions_row = ("adjust_stock",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_sold=Sum("order_items__quantity"))

    @display(description="Price")
    def price_display(self, obj):
        return f"Rs {obj.price:,.0f}"

    @display(description="Stock", ordering="stock")
    def stock_display(self, obj):
        low = settings.SHOP["LOW_STOCK_THRESHOLD"]
        cls = "text-red-600 font-semibold" if obj.stock <= 0 else "text-amber-600 font-semibold" if obj.stock <= low else ""
        return format_html('<span class="{}">{}</span>', cls, obj.stock)

    @display(description="Sold", ordering="_sold")
    def sold(self, obj):
        return obj._sold or 0

    @action(
        description="Adjust stock",
        icon="inventory",
        variant=ActionVariant.PRIMARY,
        permissions=("change",),
        dialog={"title": "Adjust stock", "form_class": StockAdjustForm, "form_submit_text": "Apply"},
    )
    def adjust_stock(self, request, form, object_id):
        from apps.core.exceptions import BusinessError

        from .services import adjust_stock

        try:
            v = adjust_stock(int(object_id), int(form.cleaned_data["delta"]), reason=form.cleaned_data.get("reason", ""))
            self.message_user(request, f"{v.sku} stock is now {v.stock}.", messages.SUCCESS)
        except BusinessError as exc:
            self.message_user(request, str(exc.detail), messages.ERROR)
        return redirect(reverse("admin:catalog_productvariant_changelist"))

    @action(description="Deactivate selected", icon="block")
    def deactivate(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, "Variants deactivated.", messages.SUCCESS)

    @action(description="Export inventory CSV", icon="download")
    def export_inventory(self, request, queryset):
        return export_csv(
            "inventory",
            ["SKU", "Product", "Colour", "Size", "Price", "Stock", "Active"],
            (
                (
                    v.sku,
                    v.product.name,
                    v.color.name if v.color_id else "",
                    v.size.label if v.size_id else "",
                    v.price,
                    v.stock,
                    v.is_active,
                )
                for v in queryset
            ),
        )


@admin.register(StockAlert)
class StockAlertAdmin(ModelAdmin):
    list_display = ("email", "variant", "created_at", "notified_at")
    list_filter = (("notified_at", RangeNumericFilter) if False else "notified_at",)
    search_fields = ("email", "variant__sku", "variant__product__name")
    list_select_related = ("variant__product",)
