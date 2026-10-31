from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User


@receiver(post_save, sender=User)
def welcome_new_user(sender, instance: User, created, **kwargs):
    if created and not instance.is_staff:
        from apps.notifications.events import emit

        emit("user.registered", user_id=instance.pk)
