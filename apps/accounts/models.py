from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.models import TimeStampedModel, UUIDModel


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("is_email_verified", True)
        return self._create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin, UUIDModel):
    """Shopper account. Login by email/password or Google."""

    class AuthProvider(models.TextChoices):
        EMAIL = "email", "Email & password"
        GOOGLE = "google", "Google"

    class Gender(models.TextChoices):
        MEN = "men", "Men"
        WOMEN = "women", "Women"
        UNSPECIFIED = "", "Prefer not to say"

    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=80, blank=True)
    last_name = models.CharField(max_length=80, blank=True)
    phone = models.CharField(max_length=20, blank=True, db_index=True, help_text="Used for delivery calls / SMS")
    avatar_url = models.URLField(blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    shop_for = models.CharField(max_length=6, choices=Gender.choices, blank=True, default="")
    language = models.CharField(
        max_length=5, choices=settings.LANGUAGES, default="en", help_text="Language for emails and notifications"
    )

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)
    auth_provider = models.CharField(max_length=16, choices=AuthProvider.choices, default=AuthProvider.EMAIL)
    google_sub = models.CharField(max_length=64, blank=True, null=True, unique=True)

    marketing_opt_in = models.BooleanField(default=True)
    notification_preferences = models.JSONField(default=dict, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    # Denormalised shopper stats for admin segmentation (maintained by order services).
    order_count = models.PositiveIntegerField(default=0)
    total_spent = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        indexes = [models.Index(fields=["is_active", "is_staff"]), models.Index(fields=["-created_at"])]

    def __str__(self):
        return self.email

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or self.email.split("@")[0]

    def touch_last_seen(self):
        now = timezone.now()
        if not self.last_seen_at or (now - self.last_seen_at).total_seconds() > 300:
            type(self).objects.filter(pk=self.pk).update(last_seen_at=now)


class Address(UUIDModel):
    """Saved delivery address. Pakistan-first: province + city drive shipping zones."""

    class Label(models.TextChoices):
        HOME = "home", "Home"
        WORK = "work", "Work"
        OTHER = "other", "Other"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(max_length=6, choices=Label.choices, default=Label.HOME)
    full_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20)
    line1 = models.CharField(max_length=200, help_text="House / street")
    line2 = models.CharField(max_length=200, blank=True, help_text="Area / landmark")
    city = models.CharField(max_length=100, db_index=True)
    province = models.CharField(max_length=60, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=2, default="PK")
    is_default = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "addresses"
        ordering = ("-is_default", "-created_at")
        constraints = [
            models.UniqueConstraint(fields=["user"], condition=Q(is_default=True), name="uniq_default_address_per_user"),
        ]

    def __str__(self):
        return f"{self.full_name}, {self.city}"

    def as_snapshot(self) -> dict:
        return {
            "full_name": self.full_name,
            "phone": self.phone,
            "line1": self.line1,
            "line2": self.line2,
            "city": self.city,
            "province": self.province,
            "postal_code": self.postal_code,
            "country": self.country,
        }


class NewsletterSubscriber(TimeStampedModel):
    email = models.EmailField(unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    is_active = models.BooleanField(default=True)
    source = models.CharField(max_length=40, blank=True, default="footer")
    unsubscribed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.email
