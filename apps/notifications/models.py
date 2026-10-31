from django.conf import settings
from django.db import models

from apps.core.models import UUIDModel


class Notification(UUIDModel):
    class Kind(models.TextChoices):
        ORDER = "order", "Order"
        QUOTE = "quote", "Quote"
        PAYMENT = "payment", "Payment"
        ACCOUNT = "account", "Account"
        CHAT = "chat", "Chat"
        SYSTEM = "system", "System"

    class Level(models.TextChoices):
        INFO = "info", "Info"
        SUCCESS = "success", "Success"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    company = models.ForeignKey("accounts.Company", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.SYSTEM)
    level = models.CharField(max_length=8, choices=Level.choices, default=Level.INFO)
    title = models.CharField(max_length=160)
    body = models.CharField(max_length=500, blank=True)
    url = models.CharField(max_length=300, blank=True, help_text="Frontend path to open")
    data = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["user", "is_read", "-created_at"]),
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self):
        return self.title
