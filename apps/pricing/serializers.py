from rest_framework import serializers

from apps.catalog.models import Gender


class BreakdownLineSerializer(serializers.Serializer):
    gender = serializers.ChoiceField(choices=Gender.choices)
    size_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=0, max_value=100000)


class PriceQuoteRequestSerializer(serializers.Serializer):
    product = serializers.SlugField()
    fabric = serializers.SlugField(required=False, allow_null=True)
    breakdown = BreakdownLineSerializer(many=True, allow_empty=False)
