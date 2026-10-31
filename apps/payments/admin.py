from django.contrib import admin, messages
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.contrib.filters.admin import ChoicesDropdownFilter, RangeDateFilter
from unfold.decorators import action, display
from unfold.enums import ActionVariant

from apps.core.admin_forms import ConfirmPaymentForm
from apps.core.admin_utils import STATUS_COLORS, export_csv
from apps.core.exceptions import BusinessError

from . import services
from .models import BankAccount, Payment


@admin.register(BankAccount)
class BankAccountAdmin(ModelAdmin):
    list_display = ("label", "bank_name", "account_name", "account_number", "is_active", "sort_order")
    list_editable = ("is_active", "sort_order")


@admin.register(Payment)
class PaymentAdmin(ModelAdmin):
    list_display = (
        "order_link",
        "customer",
        "method",
        "status_badge",
        "amount_display",
        "reference",
        "proof_link",
        "submitted_at",
        "confirmed_at",
    )
    list_filter = (("status", ChoicesDropdownFilter), "method", ("created_at", RangeDateFilter))
    list_filter_submit = True
    search_fields = ("order__number", "order__email", "order__phone", "reference")
    list_select_related = ("order", "confirmed_by")
    readonly_fields = (
        "uid",
        "order",
        "method",
        "currency",
        "status",
        "submitted_at",
        "confirmed_at",
        "confirmed_by",
        "created_at",
    )
    actions = ("bulk_confirm", "export_payments")
    actions_detail = ("confirm_payment", "mark_failed")
    actions_row = ("confirm_payment",)

    def has_add_permission(self, request):
        return False

    @display(description="Order")
    def order_link(self, obj):
        return format_html(
            '<a class="underline" href="{}">{}</a>', reverse("admin:orders_order_change", args=[obj.order_id]), obj.order.number
        )

    @display(description="Customer")
    def customer(self, obj):
        return obj.order.shipping_address.get("full_name") or obj.order.email

    @display(description="Status", label=STATUS_COLORS)
    def status_badge(self, obj):
        return obj.status, obj.get_status_display()

    @display(description="Amount", ordering="amount")
    def amount_display(self, obj):
        return f"Rs {obj.amount:,.0f}"

    @display(description="Proof")
    def proof_link(self, obj):
        return format_html('<a class="underline" target="_blank" href="{}">View</a>', obj.proof.url) if obj.proof else "—"

    @action(
        description="Confirm payment",
        icon="verified",
        variant=ActionVariant.SUCCESS,
        permissions=("change",),
        dialog={
            "title": "Confirm payment received",
            "description": "Marks the order paid, confirms it and notifies the customer.",
            "form_class": ConfirmPaymentForm,
            "form_submit_text": "Confirm",
        },
    )
    def confirm_payment(self, request, form, object_id):
        payment = Payment.objects.get(pk=object_id)
        try:
            if form.cleaned_data.get("reference"):
                payment.reference = form.cleaned_data["reference"]
                payment.save(update_fields=["reference"])
            services.confirm(payment, by=request.user, amount=form.cleaned_data.get("amount"))
            self.message_user(request, f"Payment for {payment.order.number} confirmed.", messages.SUCCESS)
        except BusinessError as exc:
            self.message_user(request, str(exc.detail), messages.ERROR)
        return redirect(reverse("admin:payments_payment_change", args=[object_id]))

    @action(description="Mark as failed", icon="error", variant=ActionVariant.DANGER, permissions=("change",))
    def mark_failed(self, request, object_id):
        Payment.objects.filter(pk=object_id).exclude(status=Payment.Status.CONFIRMED).update(status=Payment.Status.FAILED)
        self.message_user(request, "Marked as failed. The customer can resubmit.", messages.WARNING)
        return redirect(reverse("admin:payments_payment_change", args=[object_id]))

    @action(description="Confirm selected", icon="verified")
    def bulk_confirm(self, request, queryset):
        done = skipped = 0
        with transaction.atomic():
            for payment in queryset.exclude(status=Payment.Status.CONFIRMED):
                try:
                    services.confirm(payment, by=request.user)
                    done += 1
                except BusinessError:
                    skipped += 1
        self.message_user(request, f"{done} confirmed, {skipped} skipped.", messages.SUCCESS if done else messages.WARNING)

    @action(description="Export selected to CSV", icon="download")
    def export_payments(self, request, queryset):
        return export_csv(
            "payments",
            ["Order", "Method", "Status", "Amount", "Reference", "Submitted", "Confirmed"],
            ((p.order.number, p.method, p.status, p.amount, p.reference, p.submitted_at, p.confirmed_at) for p in queryset),
        )
