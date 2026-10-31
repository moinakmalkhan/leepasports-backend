from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Company, CompanyMember


@receiver(post_save, sender=CompanyMember)
def ensure_single_default_membership(sender, instance: CompanyMember, created, **kwargs):
    if created and not CompanyMember.objects.filter(user=instance.user, is_default=True).exists():
        CompanyMember.objects.filter(pk=instance.pk).update(is_default=True)


@receiver(post_save, sender=Company)
def notify_staff_new_company(sender, instance: Company, created, **kwargs):
    if created:
        from apps.notifications.services import notify_staff

        notify_staff(
            event="company.created",
            subject=f"New company registered: {instance.name}",
            context={"company": instance.name, "type": instance.get_business_type_display(), "country": instance.country},
        )
