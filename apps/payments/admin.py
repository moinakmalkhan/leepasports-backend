from django.contrib import admin

from .models import BankAccount, Payment


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ("label", "bank_name", "currency", "is_active")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("order", "kind", "method", "status", "amount", "currency", "reference", "submitted_at", "confirmed_at")
    list_filter = ("status", "kind", "method")
    search_fields = ("order__number", "reference")
    list_select_related = ("order",)
