from django.db import models
from django.utils import timezone
from django_extensions.db.fields import AutoSlugField

from apps.core.models import TimeStampedModel
from apps.core.translation import TranslatableModel


class Banner(TranslatableModel, TimeStampedModel):
    """Hero / promo banners managed from the admin."""

    class Placement(models.TextChoices):
        HERO = "hero", "Home hero"
        PROMO = "promo", "Home promo strip"
        CATEGORY = "category", "Category page top"

    title = models.CharField(max_length=120)
    subtitle = models.CharField(max_length=200, blank=True)
    eyebrow = models.CharField(max_length=60, blank=True, help_text="Small label above the title, e.g. NEW DROP")
    image = models.ImageField(upload_to="banners/")
    mobile_image = models.ImageField(upload_to="banners/", blank=True)
    cta_label = models.CharField(max_length=40, blank=True, default="Shop now")
    cta_url = models.CharField(max_length=300, blank=True, default="/products")
    placement = models.CharField(max_length=10, choices=Placement.choices, default=Placement.HERO)
    theme = models.CharField(max_length=5, choices=[("dark", "Dark text"), ("light", "Light text")], default="light")
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("placement", "sort_order")

    def __str__(self):
        return self.title

    @property
    def is_live(self):
        now = timezone.now()
        return self.is_active and (not self.starts_at or self.starts_at <= now) and (not self.ends_at or self.ends_at >= now)


class Announcement(TranslatableModel, TimeStampedModel):
    """The thin bar above the header ("Free delivery over Rs 3,000")."""

    text = models.CharField(max_length=160)
    url = models.CharField(max_length=300, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("sort_order",)

    def __str__(self):
        return self.text


class Page(TranslatableModel, TimeStampedModel):
    """Static pages: shipping & returns, size guide, about, privacy, terms, FAQ."""

    title = models.CharField(max_length=120)
    slug = AutoSlugField(populate_from="title", overwrite_on_add=False, max_length=140, unique=True)
    body = models.TextField(help_text="Markdown")
    is_published = models.BooleanField(default=True)
    show_in_footer = models.BooleanField(default=True)
    meta_description = models.CharField(max_length=320, blank=True)

    class Meta:
        ordering = ("title",)

    def __str__(self):
        return self.title


class FAQ(TranslatableModel, TimeStampedModel):
    question = models.CharField(max_length=200)
    answer = models.TextField()
    category = models.CharField(max_length=40, default="Orders", help_text="Orders, Shipping, Returns, Sizing, Payments")
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("category", "sort_order")
        verbose_name = "FAQ"

    def __str__(self):
        return self.question
