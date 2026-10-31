import uuid

from django.db import models
from django_extensions.db.fields import CreationDateTimeField, ModificationDateTimeField


class TimeStampedModel(models.Model):
    """Abstract base with created/updated timestamps (indexed on created).

    Uses django-extensions' Creation/ModificationDateTimeField so `save(update_modified=False)`
    can skip touching `updated_at` for background bookkeeping writes."""

    created_at = CreationDateTimeField(db_index=True)
    updated_at = ModificationDateTimeField()

    class Meta:
        abstract = True


class UUIDModel(TimeStampedModel):
    """Abstract base exposing a public, non-sequential identifier.

    Sequential BigAutoField primary keys stay for fast joins; `uid` is what
    leaves the API so clients cannot enumerate rows.
    """

    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def dead(self):
        return self.filter(deleted_at__isnull=False)


class SoftDeleteModel(models.Model):
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = SoftDeleteQuerySet.as_manager()

    class Meta:
        abstract = True

    def soft_delete(self):
        from django.utils import timezone

        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])
