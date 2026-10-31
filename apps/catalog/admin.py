from decimal import Decimal

from django.contrib import admin, messages
from django.db import transaction
from django.db.models import Count
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import ChoicesDropdownFilter, RangeNumericFilter, RelatedDropdownFilter
from unfold.decorators import action, display
from unfold.enums import ActionVariant

from apps.core.admin_forms import FabricPriceAdjustForm
from apps.core.admin_utils import export_csv

from .models import Category, Fabric, Product, ProductFabricOption, ProductImage, ProductSizeOption, Size, SizeGroup


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ("tree_name", "slug", "products_total", "sort_order", "active")
    list_filter = ("is_active", "depth", ("parent", RelatedDropdownFilter))
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("path", "depth", "uid")
    list_select_related = ("parent",)
    autocomplete_fields = ("parent",)
    ordering = ("path",)
    actions = ("activate", "deactivate")
    fieldsets = (
        (None, {"fields": (("name", "slug"), "parent", ("icon", "sort_order", "is_active"), "description", "image")}),
        ("SEO", {"classes": ("collapse",), "fields": ("meta_title", "meta_description")}),
        ("System", {"classes": ("collapse",), "fields": ("path", "depth", "uid")}),
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

    @action(description="Activate", icon="visibility", variant=ActionVariant.SUCCESS)
    def activate(self, request, queryset):
        queryset.update(is_active=True)
        self.message_user(request, "Categories activated.", messages.SUCCESS)

    @action(description="Hide from storefront", icon="visibility_off", variant=ActionVariant.WARNING)
    def deactivate(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, "Categories hidden.", messages.SUCCESS)


@admin.register(Fabric)
class FabricAdmin(ModelAdmin):
    list_display = (
        "swatch",
        "name",
        "composition",
        "gsm",
        "quality_badge",
        "price_pkr",
        "price_unit",
        "usd_per_kg",
        "products_using",
        "price_updated_at",
        "active",
    )
    list_display_links = ("name",)
    list_filter = (("quality", ChoicesDropdownFilter), "is_active", "is_available_in_pakistan", ("price_pkr", RangeNumericFilter))
    list_filter_submit = True
    search_fields = ("name", "composition", "typical_mills")
    prepopulated_fields = {"slug": ("name",)}
    list_editable = ("price_pkr",)
    actions = ("adjust_prices", "mark_prices_current", "export_fabrics")
    actions_detail = ("reprice_now",)
    compressed_fields = True
    fieldsets = (
        (
            "Fabric",
            {"fields": (("name", "slug"), "composition", ("gsm", "width_inches"), ("quality", "quality_rank"), "description")},
        ),
        (
            "Mill pricing (PKR)",
            {
                "description": "Products using this fabric are re-priced automatically when you change the rate.",
                "fields": (("price_pkr", "price_unit", "price_updated_at"), "typical_mills", "is_available_in_pakistan"),
            },
        ),
        ("Storefront", {"fields": ("features", "best_for", ("image", "swatch_color"), "is_active")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_products=Count("product_options", distinct=True))

    @display(description="")
    def swatch(self, obj):
        return format_html(
            '<span class="inline-block h-6 w-6 rounded-full border border-base-300" style="background:{}"></span>',
            obj.swatch_color,
        )

    @display(description="Quality", label={"economy": "default", "standard": "info", "premium": "primary", "elite": "success"})
    def quality_badge(self, obj):
        return obj.quality

    @display(description="≈ USD/kg")
    def usd_per_kg(self, obj):
        from apps.pricing.services import pkr_per_unit

        return f"{obj.price_pkr / pkr_per_unit('USD'):.2f}"

    @display(description="Products", ordering="_products")
    def products_using(self, obj):
        return obj._products

    @display(description="Active", boolean=True)
    def active(self, obj):
        return obj.is_active

    @action(
        description="Adjust mill prices by percentage",
        icon="percent",
        variant=ActionVariant.PRIMARY,
        dialog={
            "title": "Adjust mill prices",
            "description": "Applies to every selected fabric and re-prices all affected products.",
            "form_class": FabricPriceAdjustForm,
            "form_submit_text": "Apply",
        },
    )
    def adjust_prices(self, request, form, queryset):
        factor = 1 + Decimal(form.cleaned_data["percent"]) / 100
        with transaction.atomic():
            for fabric in queryset.select_for_update():
                fabric.price_pkr = (fabric.price_pkr * factor).quantize(Decimal("0.01"))
                fabric.price_updated_at = timezone.localdate()
                fabric.save()
        self.message_user(
            request, f"Prices adjusted by {form.cleaned_data['percent']}% for {queryset.count()} fabric(s).", messages.SUCCESS
        )

    @action(description="Mark prices as checked today", icon="event_available")
    def mark_prices_current(self, request, queryset):
        queryset.update(price_updated_at=timezone.localdate())
        self.message_user(request, "Price check date updated.", messages.SUCCESS)

    @action(description="Export selected to CSV", icon="download")
    def export_fabrics(self, request, queryset):
        return export_csv(
            "fabrics",
            ["Name", "Composition", "GSM", "Quality", "PKR", "Unit", "Mills", "Updated"],
            (
                (f.name, f.composition, f.gsm, f.quality, f.price_pkr, f.price_unit, f.typical_mills, f.price_updated_at)
                for f in queryset
            ),
        )

    @action(description="Re-price products now", icon="sync", permissions=("change",))
    def reprice_now(self, request, object_id):
        from .tasks import reprice_products_for_fabric

        reprice_products_for_fabric.delay(int(object_id))
        self.message_user(request, "Re-pricing queued for all products using this fabric.", messages.SUCCESS)
        return redirect(reverse("admin:catalog_fabric_change", args=[object_id]))


class SizeInline(TabularInline):
    model = Size
    extra = 0
    fields = ("label", "sort_order", "surcharge_percent", "chest_cm", "length_cm")


@admin.register(SizeGroup)
class SizeGroupAdmin(ModelAdmin):
    inlines = (SizeInline,)
    list_display = ("name", "sizes_list", "sort_order")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)

    @display(description="Sizes")
    def sizes_list(self, obj):
        return " · ".join(obj.sizes.values_list("label", flat=True))


class ImageInline(TabularInline):
    model = ProductImage
    extra = 0
    fields = ("preview", "image", "alt", "sort_order", "is_primary")
    readonly_fields = ("preview",)
    tab = True

    @display(description="")
    def preview(self, obj):
        return format_html('<img src="{}" class="h-12 w-12 rounded object-cover" />', obj.image.url) if obj.image else "—"


class FabricOptionInline(TabularInline):
    model = ProductFabricOption
    extra = 0
    autocomplete_fields = ("fabric",)
    tab = True


class SizeOptionInline(TabularInline):
    model = ProductSizeOption
    extra = 0
    tab = True

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "size":
            kwargs["queryset"] = Size.objects.select_related("group").order_by("group__sort_order", "sort_order")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = (
        "thumb",
        "name",
        "sku",
        "category",
        "base_fabric",
        "from_price",
        "min_order_quantity",
        "lead_time_days",
        "sold",
        "flags",
        "active",
    )
    list_display_links = ("name",)
    list_filter = (
        ("category", RelatedDropdownFilter),
        ("base_fabric", RelatedDropdownFilter),
        "is_active",
        "is_featured",
        "is_new",
        "is_made_to_order",
        ("base_price", RangeNumericFilter),
    )
    list_filter_submit = True
    search_fields = ("name", "sku", "short_description", "tags")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("uid", "base_price", "view_count", "order_count", "created_at", "updated_at", "storefront_link")
    inlines = (ImageInline, FabricOptionInline, SizeOptionInline)
    list_select_related = ("category", "base_fabric")
    autocomplete_fields = ("category", "base_fabric", "size_group")
    actions = ("feature", "unfeature", "activate", "deactivate", "export_products")
    actions_detail = ("duplicate", "view_orders")
    compressed_fields = True
    warn_unsaved_form = True
    fieldsets = (
        (
            "Product",
            {"fields": (("name", "slug", "sku"), "category", "short_description", "description", "tags", "storefront_link")},
        ),
        (
            "Pricing",
            {
                "description": "Unit price = labour + fabric (mill PKR/kg × consumption ÷ FX) with group & volume discounts applied at checkout.",
                "fields": (("base_fabric", "fabric_consumption_kg"), ("labor_price", "base_price", "compare_at_price")),
            },
        ),
        (
            "Sizes & options",
            {"fields": ("size_group", "genders", "colors", "is_customizable", "customization_options", "specifications")},
        ),
        (
            "Ordering",
            {
                "fields": (
                    ("min_order_quantity", "order_increment", "lead_time_days"),
                    ("is_made_to_order", "stock_quantity", "weight_grams"),
                )
            },
        ),
        ("Visibility", {"fields": (("is_active", "is_featured", "is_new"), ("view_count", "order_count"))}),
        ("SEO", {"classes": ("collapse",), "fields": ("meta_title", "meta_description")}),
        ("System", {"classes": ("collapse",), "fields": ("uid", "created_at", "updated_at")}),
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

    @display(description="From", ordering="base_price")
    def from_price(self, obj):
        return f"USD {obj.base_price:,.2f}"

    @display(description="Sold", ordering="order_count")
    def sold(self, obj):
        return f"{obj.order_count:,}"

    @display(description="Flags")
    def flags(self, obj):
        parts = []
        if obj.is_featured:
            parts.append("★ Featured")
        if obj.is_new:
            parts.append("New")
        if not obj.is_made_to_order and obj.stock_quantity <= 20:
            parts.append(f"Low stock ({obj.stock_quantity})")
        return " · ".join(parts) or "—"

    @display(description="Active", boolean=True)
    def active(self, obj):
        return obj.is_active

    @display(description="Storefront")
    def storefront_link(self, obj):
        from django.conf import settings

        return (
            format_html(
                '<a class="text-primary-600 underline" target="_blank" href="{}/products/{}">Open on storefront ↗</a>',
                settings.FRONTEND_URL,
                obj.slug,
            )
            if obj.pk
            else "—"
        )

    @action(description="Feature on homepage", icon="star", variant=ActionVariant.PRIMARY)
    def feature(self, request, queryset):
        queryset.update(is_featured=True)
        self.message_user(request, "Products featured.", messages.SUCCESS)

    @action(description="Remove from featured", icon="star_outline")
    def unfeature(self, request, queryset):
        queryset.update(is_featured=False)
        self.message_user(request, "Products removed from featured.", messages.SUCCESS)

    @action(description="Publish", icon="visibility", variant=ActionVariant.SUCCESS)
    def activate(self, request, queryset):
        queryset.update(is_active=True)
        self.message_user(request, "Products published.", messages.SUCCESS)

    @action(description="Unpublish", icon="visibility_off", variant=ActionVariant.WARNING)
    def deactivate(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, "Products unpublished.", messages.SUCCESS)

    @action(description="Export selected to CSV", icon="download")
    def export_products(self, request, queryset):
        return export_csv(
            "products",
            ["SKU", "Name", "Category", "Base fabric", "Labour", "From price", "MOQ", "Lead days", "Sold", "Active"],
            (
                (
                    p.sku,
                    p.name,
                    p.category.name,
                    p.base_fabric.name,
                    p.labor_price,
                    p.base_price,
                    p.min_order_quantity,
                    p.lead_time_days,
                    p.order_count,
                    p.is_active,
                )
                for p in queryset.select_related("category", "base_fabric")
            ),
        )

    @action(description="Duplicate product", icon="content_copy", permissions=("change",))
    def duplicate(self, request, object_id):
        from apps.core.utils import unique_slug

        with transaction.atomic():
            source = Product.objects.prefetch_related("fabric_options", "size_options").get(pk=object_id)
            clone = Product.objects.get(pk=object_id)
            clone.pk = None
            clone.uid = None
            import uuid

            clone.uid = uuid.uuid4()
            clone.name = f"{source.name} (copy)"
            clone.slug = unique_slug(Product, clone.name)
            clone.sku = f"{source.sku}-COPY"[:40]
            clone.is_active = False
            clone.is_featured = False
            clone.view_count = clone.order_count = 0
            clone.save()
            ProductFabricOption.objects.bulk_create(
                [
                    ProductFabricOption(
                        product=clone, fabric_id=o.fabric_id, price_adjustment=o.price_adjustment, is_default=o.is_default
                    )
                    for o in source.fabric_options.all()
                ]
            )
            ProductSizeOption.objects.bulk_create(
                [
                    ProductSizeOption(product=clone, gender=o.gender, size_id=o.size_id, is_active=o.is_active)
                    for o in source.size_options.all()
                ]
            )
        self.message_user(
            request, f"Created draft copy {clone.sku}. Update SKU, images and publish when ready.", messages.SUCCESS
        )
        return redirect(reverse("admin:catalog_product_change", args=[clone.pk]))

    @action(description="Order history", icon="shopping_bag")
    def view_orders(self, request, object_id):
        return redirect(reverse("admin:orders_order_changelist") + f"?items__product__id__exact={object_id}")
