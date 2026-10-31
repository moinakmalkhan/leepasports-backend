from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.contrib.filters.admin import ChoicesDropdownFilter, RangeDateFilter, RelatedDropdownFilter
from unfold.decorators import action, display
from unfold.enums import ActionVariant

from apps.core.admin_forms import ReviewReplyForm

from . import services
from .models import Review


@admin.register(Review)
class ReviewAdmin(ModelAdmin):
    list_display = ("product", "stars", "title", "user", "verified", "status_badge", "helpful_count", "created_at")
    list_filter = (
        ("status", ChoicesDropdownFilter),
        "rating",
        "is_verified_purchase",
        ("product", RelatedDropdownFilter),
        ("created_at", RangeDateFilter),
    )
    list_filter_submit = True
    search_fields = ("title", "body", "product__name", "user__email")
    list_select_related = ("product", "user")
    readonly_fields = ("uid", "product", "user", "order_item", "is_verified_purchase", "helpful_count", "created_at")
    actions = ("approve", "reject")
    actions_detail = ("approve_one", "reject_one", "reply")
    actions_row = ("approve_one",)

    def has_add_permission(self, request):
        return False

    @display(description="Rating", ordering="rating")
    def stars(self, obj):
        return format_html(
            '<span class="text-amber-500">{}</span><span class="text-base-300">{}</span>',
            "★" * obj.rating,
            "★" * (5 - obj.rating),
        )

    @display(description="Verified", boolean=True)
    def verified(self, obj):
        return obj.is_verified_purchase

    @display(description="Status", label={"pending": "warning", "approved": "success", "rejected": "danger"})
    def status_badge(self, obj):
        return obj.status

    @action(description="Approve selected", icon="check", variant=ActionVariant.SUCCESS)
    def approve(self, request, queryset):
        for r in queryset:
            services.moderate(r, Review.Status.APPROVED)
        self.message_user(request, f"{queryset.count()} review(s) approved.", messages.SUCCESS)

    @action(description="Reject selected", icon="block", variant=ActionVariant.DANGER)
    def reject(self, request, queryset):
        for r in queryset:
            services.moderate(r, Review.Status.REJECTED)
        self.message_user(request, f"{queryset.count()} review(s) rejected.", messages.WARNING)

    @action(description="Approve", icon="check", variant=ActionVariant.SUCCESS, permissions=("change",))
    def approve_one(self, request, object_id):
        services.moderate(Review.objects.get(pk=object_id), Review.Status.APPROVED)
        self.message_user(request, "Review approved and live.", messages.SUCCESS)
        return redirect(reverse("admin:reviews_review_changelist"))

    @action(description="Reject", icon="block", variant=ActionVariant.DANGER, permissions=("change",))
    def reject_one(self, request, object_id):
        services.moderate(Review.objects.get(pk=object_id), Review.Status.REJECTED)
        self.message_user(request, "Review rejected.", messages.WARNING)
        return redirect(reverse("admin:reviews_review_change", args=[object_id]))

    @action(
        description="Reply publicly",
        icon="reply",
        variant=ActionVariant.PRIMARY,
        permissions=("change",),
        dialog={"title": "Reply from Chobbar", "form_class": ReviewReplyForm, "form_submit_text": "Post reply"},
    )
    def reply(self, request, form, object_id):
        review = Review.objects.get(pk=object_id)
        services.moderate(review, Review.Status.APPROVED, reply=form.cleaned_data["reply"])
        self.message_user(request, "Reply posted.", messages.SUCCESS)
        return redirect(reverse("admin:reviews_review_change", args=[object_id]))
