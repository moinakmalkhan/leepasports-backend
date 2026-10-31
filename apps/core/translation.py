from django.db import models


class TranslatableModel(models.Model):
    """Adds a JSON `translations` column: {"ur": {"name": "…"}, "ar": {"name": "…"}}.

    One JSONB column instead of a field per language keeps the schema stable as
    languages are added, and reads stay a single row fetch.
    """

    translations = models.JSONField(default=dict, blank=True, help_text='{"ur": {"name": "…"}, "ar": {"name": "…"}}')
    translatable_fields: tuple[str, ...] = ()

    class Meta:
        abstract = True


class TranslatedSerializerMixin:
    """Overrides `Meta.translated_fields` in the output with the active language's text."""

    def to_representation(self, instance):
        from .i18n import translate

        data = super().to_representation(instance)
        for field in getattr(self.Meta, "translated_fields", ()):
            if field in data:
                data[field] = translate(instance, field)
        return data
