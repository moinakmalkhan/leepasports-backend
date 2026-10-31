from decimal import Decimal

from django.contrib import admin, messages
from django.db.models import Count
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import ChoicesDropdownFilter, RangeDateFilter, RelatedDropdownFilter
from unfold.decorators import action, display
from unfold.enums import ActionVariant

from apps.core.admin_forms import QuoteRespondForm
from apps.core.admin_utils import STATUS_COLORS, export_csv
from apps.core.exceptions import BusinessError

from . import services
from .models import Quote, QuoteItem


class QuoteItemInline(TabularInline):
    model = QuoteItem
    extra = 0
    fields = (
        "product_name",
        "fabric_name",
        "color",
        "sizes",
        "quantity",
        "requested_unit_price",
        "quoted_unit_price",
        "line_total",
    )
    readonly_fields = ("product_name", "fabric_name", "color", "sizes", "quantity", "requested_unit_price", "line_total")
    can_delete = False
    max_num = 0

    @display(description="Sizes")
    def sizes(self, obj):
        return format_html(
            "<br>".join(
                f"{line.get('gender', '').title()} {line.get('size')}: <b>{line.get('quantity')}</b>" for line in obj.breakdown
            )
        )


@admin.register(Quote)
class QuoteAdmin(ModelAdmin):
    list_display = (
        "number",
        "company",
        "status_badge",
        "total_quantity",
        "requested",
        "quoted",
        "waiting",
        "valid_until",
        "handled_by",
    )
    list_filter = (("status", ChoicesDropdownFilter), ("company", RelatedDropdownFilter), ("created_at", RangeDateFilter))
    list_filter_submit = True
    search_fields = ("number", "company__name", "requested_by__email", "items__product_name")
    inlines = (QuoteItemInline,)
    list_select_related = ("company", "handled_by")
    readonly_fields = (
        "uid",
        "number",
        "company",
        "requested_by",
        "status",
        "currency",
        "requested_total",
        "quoted_total",
        "total_quantity",
        "quoted_at",
        "responded_at",
        "created_at",
        "shipping_address",
        "orders_links",
    )
    actions = ("export_quotes",)
    actions_detail = ("start_review", "publish_quote", "decline_quote", "message_customer")
    compressed_fields = True
    fieldsets = (
        (
            "Request",
            {
                "fields": (
                    ("number", "status"),
                    ("company", "requested_by", "handled_by"),
                    ("total_quantity", "requested_total", "quoted_total", "currency"),
                    ("target_budget", "delivery_deadline", "valid_until"),
                    "customer_notes",
                    "shipping_address",
                )
            },
        ),
        (
            "Your reply",
            {
                "description": "Edit quoted unit prices in the items table below, save, then use “Publish quote”.",
                "fields": ("response_message", "internal_notes"),
            },
        ),
        ("System", {"classes": ("collapse",), "fields": ("quoted_at", "responded_at", "created_at", "orders_links", "uid")}),
    )

    def has_add_permission(self, request):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_items=Count("items"))

    @display(description="Status", label=STATUS_COLORS)
    def status_badge(self, obj):
        return obj.status, obj.get_status_display()

    @display(description="List total")
    def requested(self, obj):
        return f"{obj.currency} {obj.requested_total:,.2f}"

    @display(description="Quoted")
    def quoted(self, obj):
        return f"{obj.currency} {obj.quoted_total:,.2f}" if obj.quoted_total is not None else "—"

    @display(description="Waiting")
    def waiting(self, obj):
        if obj.status not in (Quote.Status.SUBMITTED, Quote.Status.UNDER_REVIEW):
            return "—"
        from django.utils import timezone

        hours = int((timezone.now() - obj.created_at).total_seconds() // 3600)
        return format_html('<span class="{}">{}h</span>', "text-red-600 font-semibold" if hours > 24 else "", hours)

    @display(description="Orders")
    def orders_links(self, obj):
        return (
            format_html(
                "<br>".join(
                    f'<a class="underline" href="{reverse("admin:orders_order_change", args=[o.pk])}">{o.number}</a>'
                    for o in obj.orders.all()
                )
            )
            or "—"
        )

    @action(description="Start review", icon="rate_review", permissions=("change",))
    def start_review(self, request, object_id):
        quote = Quote.objects.get(pk=object_id)
        if quote.status == Quote.Status.SUBMITTED:
            quote.status = Quote.Status.UNDER_REVIEW
            quote.handled_by = request.user
            quote.save(update_fields=["status", "handled_by", "updated_at"])
            self.message_user(request, "Quote is now under review by you.", messages.SUCCESS)
        return redirect(reverse("admin:quotes_quote_change", args=[object_id]))

    @action(
        description="Publish quote to customer",
        icon="send",
        variant=ActionVariant.PRIMARY,
        permissions=("change",),
        dialog={
            "title": "Publish quote",
            "description": "Uses the quoted unit prices saved on each line (falls back to list price or the discount below).",
            "form_class": QuoteRespondForm,
            "form_submit_text": "Send quote",
        },
    )
    def publish_quote(self, request, form, object_id):
        quote = Quote.objects.prefetch_related("items").get(pk=object_id)
        d = form.cleaned_data
        prices = {}
        discount = d.get("discount_percent")
        for item in quote.items.all():
            if item.quoted_unit_price is not None:
                prices[str(item.uid)] = item.quoted_unit_price
            elif discount:
                prices[str(item.uid)] = (item.requested_unit_price * (1 - Decimal(discount) / 100)).quantize(Decimal("0.01"))
        try:
            services.respond(
                quote,
                by=request.user,
                item_prices=prices,
                message=d.get("message") or quote.response_message,
                valid_days=d.get("valid_days"),
            )
            self.message_user(request, f"Quote {quote.number} sent to {quote.company.name}.", messages.SUCCESS)
        except BusinessError as exc:
            self.message_user(request, str(exc.detail), messages.ERROR)
        return redirect(reverse("admin:quotes_quote_change", args=[object_id]))

    @action(description="Decline", icon="block", variant=ActionVariant.DANGER, permissions=("change",))
    def decline_quote(self, request, object_id):
        quote = Quote.objects.get(pk=object_id)
        try:
            services.decline(quote, by=request.user, reason="Declined by sales")
            self.message_user(request, "Quote declined.", messages.SUCCESS)
        except BusinessError as exc:
            self.message_user(request, str(exc.detail), messages.ERROR)
        return redirect(reverse("admin:quotes_quote_change", args=[object_id]))

    @action(description="Message customer", icon="forum")
    def message_customer(self, request, object_id):
        return redirect(reverse("admin:chat_conversation_changelist") + f"?quote__id__exact={object_id}")

    @action(description="Export selected to CSV", icon="download")
    def export_quotes(self, request, queryset):
        return export_csv(
            "quotes",
            ["Number", "Company", "Status", "Pieces", "List total", "Quoted total", "Valid until", "Created"],
            (
                (
                    q.number,
                    q.company.name,
                    q.status,
                    q.total_quantity,
                    q.requested_total,
                    q.quoted_total,
                    q.valid_until,
                    q.created_at.date(),
                )
                for q in queryset
            ),
        )
