from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.shortcuts import redirect
from django.urls import reverse
from unfold.admin import ModelAdmin, StackedInline
from unfold.contrib.filters.admin import ChoicesDropdownFilter, RangeDateFilter, RangeNumericFilter
from unfold.decorators import action, display
from unfold.enums import ActionVariant
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from apps.core.admin_utils import export_csv

from .models import Address, NewsletterSubscriber, User


class AddressInline(StackedInline):
    model = Address
    extra = 0
    tab = True
    fields = (("label", "is_default"), ("full_name", "phone"), "line1", "line2", ("city", "province", "postal_code", "country"))


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    ordering = ("-created_at",)
    list_display = ("email", "full_name", "phone", "provider", "verified", "orders", "spent", "last_login", "is_staff")
    list_filter = (
        ("auth_provider", ChoicesDropdownFilter),
        "is_staff",
        "is_active",
        "is_email_verified",
        "marketing_opt_in",
        ("total_spent", RangeNumericFilter),
        ("created_at", RangeDateFilter),
    )
    list_filter_submit = True
    search_fields = ("email", "first_name", "last_name", "phone")
    readonly_fields = ("uid", "last_login", "created_at", "updated_at", "last_seen_at", "order_count", "total_spent")
    inlines = (AddressInline,)
    fieldsets = (
        ("Account", {"fields": ("uid", "email", "password")}),
        ("Profile", {"fields": (("first_name", "last_name"), ("phone", "date_of_birth", "shop_for"), "avatar_url")}),
        (
            "Status",
            {
                "fields": (
                    ("is_active", "is_email_verified", "marketing_opt_in"),
                    ("is_staff", "is_superuser"),
                    ("auth_provider", "google_sub"),
                )
            },
        ),
        ("Shopping", {"fields": (("order_count", "total_spent"), "notification_preferences")}),
        ("Permissions", {"classes": ("collapse",), "fields": ("groups", "user_permissions")}),
        ("Activity", {"classes": ("collapse",), "fields": ("last_login", "last_seen_at", "created_at", "updated_at")}),
    )
    add_fieldsets = ((None, {"fields": ("email", "password1", "password2", "first_name", "last_name")}),)
    actions = ("deactivate_users", "resend_verification", "export_users")
    actions_detail = ("view_orders", "resend_verification_detail")

    @display(description="Sign-in", label={"email": "default", "google": "info"})
    def provider(self, obj):
        return obj.auth_provider

    @display(description="Verified", boolean=True)
    def verified(self, obj):
        return obj.is_email_verified

    @display(description="Orders", ordering="order_count")
    def orders(self, obj):
        return obj.order_count

    @display(description="Spent", ordering="total_spent")
    def spent(self, obj):
        return f"Rs {obj.total_spent:,.0f}"

    @action(description="Deactivate selected", icon="person_off", variant=ActionVariant.DANGER)
    def deactivate_users(self, request, queryset):
        n = queryset.filter(is_superuser=False).update(is_active=False)
        self.message_user(request, f"{n} customer(s) deactivated.", messages.SUCCESS)

    @action(description="Resend verification email", icon="mark_email_unread")
    def resend_verification(self, request, queryset):
        from apps.accounts.services import send_verification_email

        n = 0
        for user in queryset.filter(is_email_verified=False):
            send_verification_email(user)
            n += 1
        self.message_user(request, f"Verification email sent to {n} customer(s).", messages.SUCCESS)

    @action(description="Resend verification", icon="mark_email_unread", permissions=("change",))
    def resend_verification_detail(self, request, object_id):
        from apps.accounts.services import send_verification_email

        user = User.objects.get(pk=object_id)
        if user.is_email_verified:
            self.message_user(request, "Already verified.", messages.INFO)
        else:
            send_verification_email(user)
            self.message_user(request, f"Verification email sent to {user.email}.", messages.SUCCESS)
        return redirect(reverse("admin:accounts_user_change", args=[object_id]))

    @action(description="Orders", icon="shopping_bag")
    def view_orders(self, request, object_id):
        return redirect(reverse("admin:orders_order_changelist") + f"?user__id__exact={object_id}")

    @action(description="Export selected to CSV", icon="download")
    def export_users(self, request, queryset):
        return export_csv(
            "customers",
            ["Email", "Name", "Phone", "Orders", "Spent", "Verified", "Marketing", "Joined"],
            (
                (
                    u.email,
                    u.full_name,
                    u.phone,
                    u.order_count,
                    u.total_spent,
                    u.is_email_verified,
                    u.marketing_opt_in,
                    u.created_at.date(),
                )
                for u in queryset
            ),
        )


@admin.register(NewsletterSubscriber)
class NewsletterAdmin(ModelAdmin):
    list_display = ("email", "source", "is_active", "created_at", "unsubscribed_at")
    list_filter = ("is_active", "source", ("created_at", RangeDateFilter))
    search_fields = ("email",)
    actions = ("export_subscribers",)

    @action(description="Export active subscribers to CSV", icon="download")
    def export_subscribers(self, request, queryset):
        return export_csv(
            "newsletter",
            ["Email", "Source", "Joined"],
            ((s.email, s.source, s.created_at.date()) for s in queryset.filter(is_active=True)),
        )


@admin.register(Address)
class AddressAdmin(ModelAdmin):
    list_display = ("full_name", "user", "city", "province", "phone", "is_default")
    search_fields = ("full_name", "phone", "city", "user__email")
    list_filter = ("province", "city")
    list_select_related = ("user",)
    autocomplete_fields = ("user",)
