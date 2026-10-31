from rest_framework import serializers

from .models import Conversation, Message


class MessageSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="uid", read_only=True)
    sender = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ("id", "kind", "body", "attachment", "attachment_name", "client_id", "sender", "created_at")

    def get_sender(self, obj):
        s = obj.sender
        return {"id": str(s.uid), "name": s.full_name, "is_staff": s.is_staff, "avatar_url": s.avatar_url} if s else None


class ConversationSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="uid", read_only=True)
    created_by = serializers.CharField(source="created_by.full_name", read_only=True, default="")
    assigned_to = serializers.CharField(source="assigned_to.full_name", read_only=True, default="")
    order = serializers.SerializerMethodField()
    unread_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Conversation
        fields = (
            "id",
            "subject",
            "topic",
            "status",
            "created_by",
            "assigned_to",
            "order",
            "last_message_at",
            "last_message_preview",
            "message_count",
            "unread_count",
            "created_at",
        )

    def get_order(self, obj):
        return {"id": str(obj.order.uid), "number": obj.order.number} if obj.order_id else None


class StartConversationSerializer(serializers.Serializer):
    subject = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    body = serializers.CharField(max_length=4000)
    order = serializers.UUIDField(required=False, allow_null=True)
    topic = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")


class PostMessageSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=4000, required=False, allow_blank=True, default="")
    attachment = serializers.FileField(required=False, allow_null=True)
    client_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")

    def validate_attachment(self, value):
        if value and value.size > 15 * 1024 * 1024:
            raise serializers.ValidationError("Attachments must be under 15 MB.")
        return value
