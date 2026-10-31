from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Address, Company, CompanyInvitation, CompanyMember, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("-created_at",)
    list_display = ("email", "first_name", "last_name", "is_email_verified", "auth_provider", "is_staff", "last_login")
    list_filter = ("is_staff", "is_active", "is_email_verified", "auth_provider")
    search_fields = ("email", "first_name", "last_name", "phone")
    readonly_fields = ("uid", "last_login", "created_at", "updated_at", "last_seen_at")
    fieldsets = (
        (None, {"fields": ("uid", "email", "password")}),
        ("Profile", {"fields": ("first_name", "last_name", "phone", "job_title", "avatar_url")}),
        ("Status", {"fields": ("is_active", "is_staff", "is_superuser", "is_email_verified", "auth_provider", "google_sub")}),
        ("Permissions", {"fields": ("groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "last_seen_at", "created_at", "updated_at")}),
    )
    add_fieldsets = ((None, {"fields": ("email", "password1", "password2")}),)


class MemberInline(admin.TabularInline):
    model = CompanyMember
    extra = 0
    autocomplete_fields = ("user",)


class AddressInline(admin.StackedInline):
    model = Address
    extra = 0


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "business_type",
        "country",
        "customer_group",
        "payment_terms",
        "is_verified",
        "is_active",
        "created_at",
    )
    list_filter = ("business_type", "is_verified", "is_active", "payment_terms", "customer_group")
    search_fields = ("name", "legal_name", "email", "tax_id")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("uid", "credit_used", "created_at", "updated_at")
    inlines = (MemberInline, AddressInline)
    list_select_related = ("customer_group",)


@admin.register(CompanyInvitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ("email", "company", "role", "status", "expires_at")
    list_filter = ("status", "role")
    search_fields = ("email", "company__name")
    list_select_related = ("company",)
