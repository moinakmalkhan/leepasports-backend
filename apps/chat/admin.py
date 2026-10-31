from django.contrib import admin

from .models import Conversation, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ("sender", "kind", "body", "created_at")
    can_delete = False


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("subject", "company", "status", "assigned_to", "message_count", "last_message_at")
    list_filter = ("status",)
    search_fields = ("subject", "company__name")
    inlines = (MessageInline,)
    list_select_related = ("company", "assigned_to")
