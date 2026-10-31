from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import ChoicesDropdownFilter, RelatedDropdownFilter
from unfold.decorators import action, display
from unfold.enums import ActionVariant

from apps.core.admin_forms import NoteForm
from apps.core.admin_utils import STATUS_COLORS

from . import services
from .models import Conversation, Message


class MessageInline(TabularInline):
    model = Message
    extra = 0
    fields = ("created_at", "sender", "kind", "body", "attachment")
    readonly_fields = fields
    can_delete = False
    max_num = 0
    ordering = ("created_at",)


@admin.register(Conversation)
class ConversationAdmin(ModelAdmin):
    list_display = (
        "subject",
        "created_by",
        "topic",
        "status_badge",
        "linked",
        "assigned_to",
        "message_count",
        "last_message_at",
        "preview",
    )
    list_filter = (("status", ChoicesDropdownFilter), "topic", ("assigned_to", RelatedDropdownFilter))
    list_filter_submit = True
    search_fields = ("subject", "created_by__email", "messages__body")
    inlines = (MessageInline,)
    list_select_related = ("created_by", "assigned_to", "order")
    readonly_fields = ("uid", "created_by", "order", "last_message_at", "last_message_preview", "message_count", "created_at")
    actions = ("assign_to_me", "close_selected")
    actions_detail = ("reply", "assign_me", "close_conversation")

    def has_add_permission(self, request):
        return False

    @display(description="Status", label=STATUS_COLORS)
    def status_badge(self, obj):
        return obj.status, obj.get_status_display()

    @display(description="About")
    def linked(self, obj):
        if obj.order_id:
            return format_html(
                '<a class="underline" href="{}">Order {}</a>',
                reverse("admin:orders_order_change", args=[obj.order_id]),
                obj.order.number,
            )
        return "General"

    @display(description="Last message")
    def preview(self, obj):
        return obj.last_message_preview[:60]

    @action(
        description="Reply",
        icon="reply",
        variant=ActionVariant.PRIMARY,
        permissions=("change",),
        dialog={
            "title": "Reply to customer",
            "description": "Delivered instantly in chat and as a notification.",
            "form_class": NoteForm,
            "form_submit_text": "Send",
        },
    )
    def reply(self, request, form, object_id):
        conversation = Conversation.objects.get(pk=object_id)
        body = form.cleaned_data.get("note", "").strip()
        if body:
            services.post_message(conversation, sender=request.user, body=body)
            if not conversation.assigned_to_id:
                Conversation.objects.filter(pk=conversation.pk).update(assigned_to=request.user)
            self.message_user(request, "Reply sent.", messages.SUCCESS)
        return redirect(reverse("admin:chat_conversation_change", args=[object_id]))

    @action(description="Assign to me", icon="person_check", permissions=("change",))
    def assign_me(self, request, object_id):
        Conversation.objects.filter(pk=object_id).update(assigned_to=request.user)
        self.message_user(request, "Assigned to you.", messages.SUCCESS)
        return redirect(reverse("admin:chat_conversation_change", args=[object_id]))

    @action(description="Close", icon="done_all", permissions=("change",))
    def close_conversation(self, request, object_id):
        conversation = Conversation.objects.get(pk=object_id)
        services.post_message(
            conversation, sender=request.user, body="Conversation closed by Chobbar support.", kind=Message.Kind.SYSTEM
        )
        Conversation.objects.filter(pk=object_id).update(status=Conversation.Status.CLOSED)
        self.message_user(request, "Closed.", messages.SUCCESS)
        return redirect(reverse("admin:chat_conversation_change", args=[object_id]))

    @action(description="Assign selected to me", icon="person_check")
    def assign_to_me(self, request, queryset):
        n = queryset.update(assigned_to=request.user)
        self.message_user(request, f"{n} assigned to you.", messages.SUCCESS)

    @action(description="Close selected", icon="done_all")
    def close_selected(self, request, queryset):
        n = queryset.update(status=Conversation.Status.CLOSED)
        self.message_user(request, f"{n} closed.", messages.SUCCESS)
