from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="uid", read_only=True)

    class Meta:
        model = Notification
        fields = ("id", "kind", "level", "title", "body", "url", "data", "is_read", "read_at", "created_at")
