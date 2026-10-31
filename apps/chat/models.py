from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel, UUIDModel


class Conversation(UUIDModel):
    """A support thread between a shopper and Chobbar staff, optionally about an order."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        PENDING = "pending", "Waiting on customer"
        CLOSED = "closed", "Closed"

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="conversations")
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_conversations"
    )
    subject = models.CharField(max_length=160)
    topic = models.CharField(max_length=20, blank=True, help_text="order, sizing, returns, payment, other")
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.OPEN)
    order = models.ForeignKey("orders.Order", null=True, blank=True, on_delete=models.SET_NULL, related_name="conversations")
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_message_preview = models.CharField(max_length=160, blank=True)
    message_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("-last_message_at", "-created_at")
        indexes = [
            models.Index(fields=["created_by", "status", "-last_message_at"]),
            models.Index(fields=["status", "-last_message_at"]),
        ]

    def __str__(self):
        return self.subject


class Participant(TimeStampedModel):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="participants")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_participations")
    last_read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["conversation", "user"], name="uniq_participant")]
        indexes = [models.Index(fields=["user", "conversation"])]

    def __str__(self):
        return f"{self.user_id} in {self.conversation_id}"


class Message(UUIDModel):
    class Kind(models.TextChoices):
        TEXT = "text", "Text"
        SYSTEM = "system", "System"
        FILE = "file", "File"

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    kind = models.CharField(max_length=6, choices=Kind.choices, default=Kind.TEXT)
    body = models.TextField(max_length=4000, blank=True)
    attachment = models.FileField(upload_to="chat/%Y/%m/", blank=True)
    attachment_name = models.CharField(max_length=160, blank=True)
    client_id = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["conversation", "-created_at"])]

    def __str__(self):
        return f"{self.conversation_id}: {self.body[:30]}"
