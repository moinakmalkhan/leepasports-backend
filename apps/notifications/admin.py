from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "kind", "level", "is_read", "created_at")
    list_filter = ("kind", "level", "is_read")
    search_fields = ("title", "user__email")
    list_select_related = ("user",)
