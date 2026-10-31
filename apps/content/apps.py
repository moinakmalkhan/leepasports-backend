from django.apps import AppConfig


class ContentConfig(AppConfig):
    name = "apps.content"
    verbose_name = "Storefront content"

    def ready(self):
        from . import signals  # noqa: F401
