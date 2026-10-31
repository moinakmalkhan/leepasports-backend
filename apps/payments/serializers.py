from rest_framework import serializers

from apps.core.serializers import MoneyField

from .models import BankAccount, Payment


class BankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankAccount
        fields = ("label", "bank_name", "account_name", "account_number", "iban", "instructions")


class PaymentSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="uid", read_only=True)
    order_number = serializers.CharField(source="order.number", read_only=True)
    amount = MoneyField(read_only=True)

    class Meta:
        model = Payment
        fields = (
            "id",
            "order_number",
            "method",
            "status",
            "amount",
            "currency",
            "reference",
            "proof",
            "note",
            "submitted_at",
            "confirmed_at",
            "created_at",
        )


class ProofSerializer(serializers.Serializer):
    reference = serializers.CharField(max_length=120)
    note = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    proof = serializers.ImageField(required=False, allow_null=True)


class ConfirmSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
