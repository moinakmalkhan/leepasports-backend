from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.contrib.filters.admin import ChoicesDropdownFilter
from unfold.decorators import display

from .models import FAQ, Announcement, Banner, Page


@admin.register(Banner)
class BannerAdmin(ModelAdmin):
    list_display = ("preview", "title", "placement", "cta_url", "live", "sort_order", "starts_at", "ends_at", "is_active")
    list_display_links = ("title",)
    list_filter = (("placement", ChoicesDropdownFilter), "is_active")
    list_editable = ("sort_order", "is_active")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    ("placement", "theme", "sort_order"),
                    "eyebrow",
                    "title",
                    "subtitle",
                    ("image", "mobile_image"),
                    ("cta_label", "cta_url"),
                    ("is_active", "starts_at", "ends_at"),
                )
            },
        ),
        ("Translations", {"classes": ("collapse",), "fields": ("translations",)}),
    )

    @display(description="")
    def preview(self, obj):
        return format_html('<img src="{}" class="h-10 w-20 rounded object-cover" />', obj.image.url) if obj.image else "—"

    @display(description="Live", boolean=True)
    def live(self, obj):
        return obj.is_live


@admin.register(Announcement)
class AnnouncementAdmin(ModelAdmin):
    list_display = ("text", "url", "is_active", "sort_order")
    list_editable = ("is_active", "sort_order")


@admin.register(Page)
class PageAdmin(ModelAdmin):
    list_display = ("title", "slug", "is_published", "show_in_footer", "updated_at")
    list_editable = ("is_published", "show_in_footer")
    search_fields = ("title", "body")
    readonly_fields = ("slug",)


@admin.register(FAQ)
class FAQAdmin(ModelAdmin):
    list_display = ("question", "category", "sort_order", "is_active")
    list_filter = ("category", "is_active")
    list_editable = ("sort_order", "is_active")
    search_fields = ("question", "answer")
