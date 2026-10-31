from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.contrib.filters.admin import ChoicesDropdownFilter, RangeDateFilter
from unfold.decorators import display

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(ModelAdmin):
    list_display = ("title", "user", "kind_badge", "level_badge", "is_read", "created_at")
    list_filter = (("kind", ChoicesDropdownFilter), ("level", ChoicesDropdownFilter), "is_read", ("created_at", RangeDateFilter))
    search_fields = ("title", "user__email")
    list_select_related = ("user",)
    readonly_fields = ("uid", "created_at")

    @display(description="Kind", label=True)
    def kind_badge(self, obj):
        return obj.kind

    @display(description="Level", label={"info": "info", "success": "success", "warning": "warning", "error": "danger"})
    def level_badge(self, obj):
        return obj.level
