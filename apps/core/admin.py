from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.models import Group
from django_celery_beat.admin import ClockedScheduleAdmin as BaseClockedScheduleAdmin
from django_celery_beat.admin import CrontabScheduleAdmin as BaseCrontabScheduleAdmin
from django_celery_beat.admin import PeriodicTaskAdmin as BasePeriodicTaskAdmin
from django_celery_beat.models import ClockedSchedule, CrontabSchedule, IntervalSchedule, PeriodicTask, SolarSchedule
from rest_framework_simplejwt.token_blacklist.admin import BlacklistedTokenAdmin, OutstandingTokenAdmin
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from unfold.admin import ModelAdmin

admin.site.site_header = "Leepa Sports"
admin.site.site_title = "Leepa Sports Operations"
admin.site.index_title = "Dashboard"

# Hide noisy third-party models from the panel; re-register with Unfold styling where useful.
for model in (OutstandingToken, BlacklistedToken, SolarSchedule, IntervalSchedule):
    try:
        admin.site.unregister(model)
    except admin.sites.NotRegistered:
        pass

admin.site.unregister(Group)
admin.site.unregister(PeriodicTask)
admin.site.unregister(CrontabSchedule)
admin.site.unregister(ClockedSchedule)


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass


@admin.register(PeriodicTask)
class PeriodicTaskAdmin(BasePeriodicTaskAdmin, ModelAdmin):
    pass


@admin.register(CrontabSchedule)
class CrontabScheduleAdmin(BaseCrontabScheduleAdmin, ModelAdmin):
    pass


@admin.register(ClockedSchedule)
class ClockedScheduleAdmin(BaseClockedScheduleAdmin, ModelAdmin):
    pass


__all__ = ["OutstandingTokenAdmin", "BlacklistedTokenAdmin"]
