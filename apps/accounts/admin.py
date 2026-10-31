from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.db import transaction
from django.db.models import Count, Sum
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin, StackedInline, TabularInline
from unfold.contrib.filters.admin import ChoicesDropdownFilter, RangeDateFilter, RelatedDropdownFilter
from unfold.contrib.forms.widgets import WysiwygWidget  # noqa: F401
from unfold.decorators import action, display
from unfold.enums import ActionVariant
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from apps.core.admin_forms import CompanyTermsForm
from apps.core.admin_utils import export_csv

from .models import Address, Company, CompanyInvitation, CompanyMember, User


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    ordering = ("-created_at",)
    list_display = ("email", "full_name", "companies", "provider", "verified", "is_staff", "last_login")
    list_filter = (
        ("auth_provider", ChoicesDropdownFilter),
        "is_staff",
        "is_active",
        "is_email_verified",
        ("created_at", RangeDateFilter),
    )
    list_filter_submit = True
    search_fields = ("email", "first_name", "last_name", "phone")
    readonly_fields = ("uid", "last_login", "created_at", "updated_at", "last_seen_at")
    fieldsets = (
        ("Account", {"fields": ("uid", "email", "password")}),
        ("Profile", {"fields": (("first_name", "last_name"), ("phone", "job_title"), "avatar_url")}),
        (
            "Status",
            {"fields": (("is_active", "is_email_verified"), ("is_staff", "is_superuser"), ("auth_provider", "google_sub"))},
        ),
        ("Permissions", {"classes": ("collapse",), "fields": ("groups", "user_permissions")}),
        ("Activity", {"classes": ("collapse",), "fields": ("last_login", "last_seen_at", "created_at", "updated_at")}),
    )
    add_fieldsets = ((None, {"fields": ("email", "password1", "password2", "first_name", "last_name")}),)
    actions = ("deactivate_users", "resend_verification", "export_users")
    actions_detail = ("resend_verification_detail",)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("memberships__company")

    @display(description="Companies")
    def companies(self, obj):
        return ", ".join(f"{m.company.name} ({m.role})" for m in obj.memberships.all()) or "—"

    @display(description="Sign-in", label={"email": "default", "google": "info"})
    def provider(self, obj):
        return obj.auth_provider

    @display(description="Verified", boolean=True)
    def verified(self, obj):
        return obj.is_email_verified

    @action(description="Deactivate selected users", icon="person_off", variant=ActionVariant.DANGER)
    def deactivate_users(self, request, queryset):
        n = queryset.filter(is_superuser=False).update(is_active=False)
        self.message_user(request, f"{n} user(s) deactivated.", messages.SUCCESS)

    @action(description="Resend verification email", icon="mark_email_unread")
    def resend_verification(self, request, queryset):
        from apps.accounts.services import send_verification_email

        n = 0
        for user in queryset.filter(is_email_verified=False):
            send_verification_email(user)
            n += 1
        self.message_user(request, f"Verification email sent to {n} user(s).", messages.SUCCESS)

    @action(description="Resend verification", icon="mark_email_unread", permissions=("change",))
    def resend_verification_detail(self, request, object_id):
        from apps.accounts.services import send_verification_email

        user = User.objects.get(pk=object_id)
        if user.is_email_verified:
            self.message_user(request, "This user is already verified.", messages.INFO)
        else:
            send_verification_email(user)
            self.message_user(request, f"Verification email sent to {user.email}.", messages.SUCCESS)
        return redirect(reverse("admin:accounts_user_change", args=[object_id]))

    @action(description="Export selected to CSV", icon="download")
    def export_users(self, request, queryset):
        return export_csv(
            "users",
            ["Email", "First name", "Last name", "Phone", "Verified", "Provider", "Joined"],
            (
                (u.email, u.first_name, u.last_name, u.phone, u.is_email_verified, u.auth_provider, u.created_at.date())
                for u in queryset
            ),
        )


class MemberInline(TabularInline):
    model = CompanyMember
    extra = 0
    autocomplete_fields = ("user",)
    fields = ("user", "role", "order_limit", "is_default", "is_active")
    tab = True


class AddressInline(StackedInline):
    model = Address
    extra = 0
    tab = True
    fields = (
        ("kind", "label", "is_default"),
        ("contact_name", "contact_phone"),
        "line1",
        "line2",
        ("city", "state", "postal_code", "country"),
    )


@admin.register(Company)
class CompanyAdmin(ModelAdmin):
    list_display = (
        "name",
        "business_type_badge",
        "country",
        "customer_group",
        "terms",
        "credit",
        "verified",
        "orders_count",
        "lifetime_value",
        "created_at",
    )
    list_filter = (
        ("business_type", ChoicesDropdownFilter),
        "is_verified",
        "is_active",
        ("payment_terms", ChoicesDropdownFilter),
        ("customer_group", RelatedDropdownFilter),
        ("created_at", RangeDateFilter),
    )
    list_filter_submit = True
    search_fields = ("name", "legal_name", "email", "tax_id", "members__user__email")
    readonly_fields = ("uid", "credit_used", "created_at", "updated_at", "orders_summary")
    inlines = (MemberInline, AddressInline)
    list_select_related = ("customer_group",)
    autocomplete_fields = ("customer_group",)
    compressed_fields = True
    warn_unsaved_form = True
    fieldsets = (
        (
            "Company",
            {
                "fields": (
                    "name",
                    "legal_name",
                    ("business_type", "country", "currency"),
                    ("email", "phone", "website"),
                    "tax_id",
                    "logo",
                )
            },
        ),
        (
            "Commercial terms",
            {
                "fields": (
                    "customer_group",
                    ("payment_terms", "is_verified"),
                    ("credit_limit", "credit_used"),
                    "approval_threshold",
                )
            },
        ),
        ("Internal", {"fields": ("is_active", "notes", "orders_summary", "uid", "created_at", "updated_at")}),
    )
    actions = ("verify_companies", "export_companies")
    actions_detail = ("set_terms", "view_orders", "start_conversation")

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_orders=Count("orders", distinct=True), _ltv=Sum("orders__grand_total"))

    @display(
        description="Type",
        label={
            "club": "info",
            "school": "info",
            "retailer": "primary",
            "distributor": "success",
            "brand": "warning",
            "other": "default",
        },
    )
    def business_type_badge(self, obj):
        return obj.business_type

    @display(description="Terms")
    def terms(self, obj):
        return obj.get_payment_terms_display()

    @display(description="Credit used / limit")
    def credit(self, obj):
        if not obj.credit_limit:
            return "—"
        pct = min(int(obj.credit_used / obj.credit_limit * 100), 100) if obj.credit_limit else 0
        return format_html(
            '<div class="min-w-28"><div class="flex justify-between text-xs"><span>{:,.0f}</span><span>{:,.0f}</span></div><div class="h-1.5 bg-base-200 rounded dark:bg-base-700"><div class="h-1.5 rounded {}" style="width:{}%"></div></div></div>',
            obj.credit_used,
            obj.credit_limit,
            "bg-red-500" if pct > 90 else "bg-primary-500",
            pct,
        )

    @display(description="Verified", boolean=True)
    def verified(self, obj):
        return obj.is_verified

    @display(description="Orders", ordering="_orders")
    def orders_count(self, obj):
        return obj._orders

    @display(description="Lifetime value", ordering="_ltv")
    def lifetime_value(self, obj):
        return f"{obj.currency} {obj._ltv or 0:,.0f}"

    @display(description="Order history")
    def orders_summary(self, obj):
        if not obj.pk:
            return "—"
        url = reverse("admin:orders_order_changelist") + f"?company__id__exact={obj.pk}"
        return format_html(
            '<a class="text-primary-600 underline" href="{}">{} orders · lifetime {} {:,.2f}</a>',
            url,
            obj._orders if hasattr(obj, "_orders") else obj.orders.count(),
            obj.currency,
            obj._ltv or 0 if hasattr(obj, "_ltv") else 0,
        )

    @action(description="Mark as verified", icon="verified", variant=ActionVariant.SUCCESS)
    def verify_companies(self, request, queryset):
        n = queryset.update(is_verified=True)
        self.message_user(request, f"{n} company(ies) verified. They can now be granted net terms.", messages.SUCCESS)

    @action(description="Export selected to CSV", icon="download")
    def export_companies(self, request, queryset):
        return export_csv(
            "companies",
            [
                "Name",
                "Type",
                "Country",
                "Email",
                "Phone",
                "Terms",
                "Credit limit",
                "Credit used",
                "Verified",
                "Orders",
                "Lifetime value",
            ],
            (
                (
                    c.name,
                    c.business_type,
                    c.country,
                    c.email,
                    c.phone,
                    c.payment_terms,
                    c.credit_limit,
                    c.credit_used,
                    c.is_verified,
                    c._orders,
                    c._ltv or 0,
                )
                for c in queryset
            ),
        )

    @action(
        description="Set commercial terms",
        icon="handshake",
        variant=ActionVariant.PRIMARY,
        permissions=("change",),
        dialog={
            "title": "Commercial terms",
            "description": "Payment terms, credit limit and pricing group for this company.",
            "form_class": CompanyTermsForm,
            "form_submit_text": "Save terms",
        },
    )
    def set_terms(self, request, form, object_id):
        with transaction.atomic():
            company = Company.objects.select_for_update().get(pk=object_id)
            company.payment_terms = form.cleaned_data["payment_terms"]
            company.credit_limit = form.cleaned_data["credit_limit"]
            if form.cleaned_data.get("approval_threshold") is not None:
                company.approval_threshold = form.cleaned_data["approval_threshold"]
            if form.cleaned_data.get("customer_group"):
                company.customer_group_id = int(form.cleaned_data["customer_group"])
            company.is_verified = form.cleaned_data["is_verified"]
            company.save()
        self.message_user(request, f"Terms updated for {company.name}.", messages.SUCCESS)
        return redirect(reverse("admin:accounts_company_change", args=[object_id]))

    @action(description="View orders", icon="shopping_bag")
    def view_orders(self, request, object_id):
        return redirect(reverse("admin:orders_order_changelist") + f"?company__id__exact={object_id}")

    @action(description="Message company", icon="forum")
    def start_conversation(self, request, object_id):
        return redirect(reverse("admin:chat_conversation_changelist") + f"?company__id__exact={object_id}")


@admin.register(CompanyInvitation)
class InvitationAdmin(ModelAdmin):
    list_display = ("email", "company", "role", "status_badge", "expires_at", "invited_by")
    list_filter = (("status", ChoicesDropdownFilter), "role")
    search_fields = ("email", "company__name")
    list_select_related = ("company", "invited_by")
    readonly_fields = ("token", "accepted_at")

    @display(description="Status", label={"pending": "warning", "accepted": "success", "revoked": "danger", "expired": "default"})
    def status_badge(self, obj):
        return obj.status
