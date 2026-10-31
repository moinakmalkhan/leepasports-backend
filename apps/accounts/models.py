from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django_extensions.db.fields import AutoSlugField, RandomCharField

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
    """Email-first user. Login is by email or Google OAuth."""

    class AuthProvider(models.TextChoices):
        EMAIL = "email", "Email & password"
        GOOGLE = "google", "Google"

    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=80, blank=True)
    last_name = models.CharField(max_length=80, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    avatar_url = models.URLField(blank=True)
    job_title = models.CharField(max_length=120, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)
    auth_provider = models.CharField(max_length=16, choices=AuthProvider.choices, default=AuthProvider.EMAIL)
    google_sub = models.CharField(max_length=64, blank=True, null=True, unique=True)

    marketing_opt_in = models.BooleanField(default=False)
    notification_preferences = models.JSONField(default=dict, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        indexes = [
            models.Index(fields=["is_active", "is_staff"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return self.email

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or self.email.split("@")[0]

    def touch_last_seen(self):
        now = timezone.now()
        if not self.last_seen_at or (now - self.last_seen_at).total_seconds() > 300:
            type(self).objects.filter(pk=self.pk).update(last_seen_at=now)


class Company(UUIDModel):
    """A buying organisation: club, school, team store, distributor."""

    class BusinessType(models.TextChoices):
        CLUB = "club", "Sports club"
        SCHOOL = "school", "School / University"
        RETAILER = "retailer", "Retailer / Team store"
        DISTRIBUTOR = "distributor", "Distributor / Wholesaler"
        BRAND = "brand", "Private label brand"
        OTHER = "other", "Other"

    class PaymentTerms(models.TextChoices):
        PREPAID = "prepaid", "Prepaid"
        DEPOSIT_50 = "deposit_50", "50% deposit, balance before shipping"
        NET_15 = "net_15", "Net 15"
        NET_30 = "net_30", "Net 30"
        NET_60 = "net_60", "Net 60"

    name = models.CharField(max_length=160)
    slug = AutoSlugField(populate_from="name", overwrite_on_add=False, max_length=170, unique=True)
    legal_name = models.CharField(max_length=200, blank=True)
    business_type = models.CharField(max_length=20, choices=BusinessType.choices, default=BusinessType.CLUB)
    tax_id = models.CharField(max_length=64, blank=True)
    website = models.URLField(blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    logo = models.ImageField(upload_to="companies/logos/", blank=True)
    country = models.CharField(max_length=2, default="US")
    currency = models.CharField(max_length=3, default=settings.DEFAULT_CURRENCY)

    customer_group = models.ForeignKey(
        "pricing.CustomerGroup", null=True, blank=True, on_delete=models.SET_NULL, related_name="companies"
    )
    payment_terms = models.CharField(max_length=20, choices=PaymentTerms.choices, default=PaymentTerms.PREPAID)
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    credit_used = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    # Orders above this subtotal need an admin/owner approval inside the company (0 = never).
    approval_threshold = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False, help_text="Verified by Leepa Sports staff (unlocks net terms).")
    notes = models.TextField(blank=True, help_text="Internal notes (staff only).")

    class Meta:
        verbose_name_plural = "companies"
        indexes = [
            models.Index(fields=["is_active", "is_verified"]),
            models.Index(fields=["customer_group"]),
        ]

    def __str__(self):
        return self.name

    @property
    def credit_available(self):
        return max(self.credit_limit - self.credit_used, 0)

    @property
    def allows_net_terms(self) -> bool:
        return self.is_verified and self.payment_terms.startswith("net_")


class CompanyMember(TimeStampedModel):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        BUYER = "buyer", "Buyer"
        VIEWER = "viewer", "Viewer"

    ROLE_RANK = {Role.VIEWER: 0, Role.BUYER: 1, Role.ADMIN: 2, Role.OWNER: 3}
    CAN_ORDER = (Role.OWNER, Role.ADMIN, Role.BUYER)
    CAN_MANAGE = (Role.OWNER, Role.ADMIN)
    CAN_APPROVE = (Role.OWNER, Role.ADMIN)

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.BUYER)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    # Per-member spending cap per order; above this the order needs approval. 0 = use company threshold.
    order_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "user"], name="uniq_company_user"),
            models.UniqueConstraint(fields=["user"], condition=Q(is_default=True), name="uniq_default_membership_per_user"),
        ]
        indexes = [models.Index(fields=["user", "is_active"])]

    def __str__(self):
        return f"{self.user} @ {self.company} ({self.role})"

    def at_least(self, role: str) -> bool:
        return self.ROLE_RANK[self.role] >= self.ROLE_RANK[role]

    @property
    def can_order(self):
        return self.role in self.CAN_ORDER

    @property
    def can_manage(self):
        return self.role in self.CAN_MANAGE


class CompanyInvitation(UUIDModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REVOKED = "revoked", "Revoked"
        EXPIRED = "expired", "Expired"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField()
    role = models.CharField(max_length=10, choices=CompanyMember.Role.choices, default=CompanyMember.Role.BUYER)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    token = RandomCharField(length=48, unique=True, include_alpha=True, include_digits=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["email", "status"])]

    @property
    def is_valid(self) -> bool:
        return self.status == self.Status.PENDING and self.expires_at > timezone.now()


class Address(UUIDModel):
    class Kind(models.TextChoices):
        SHIPPING = "shipping", "Shipping"
        BILLING = "billing", "Billing"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="addresses")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.SHIPPING)
    label = models.CharField(max_length=80, blank=True, help_text="e.g. Head office, Warehouse 2")
    contact_name = models.CharField(max_length=120)
    contact_phone = models.CharField(max_length=32, blank=True)
    line1 = models.CharField(max_length=200)
    line2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=2)
    is_default = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "addresses"
        ordering = ("-is_default", "-created_at")
        constraints = [
            models.UniqueConstraint(
                fields=["company", "kind"], condition=Q(is_default=True), name="uniq_default_address_per_kind"
            )
        ]
        indexes = [models.Index(fields=["company", "kind"])]

    def __str__(self):
        return f"{self.label or self.line1}, {self.city}"

    def as_snapshot(self) -> dict:
        return {
            "contact_name": self.contact_name,
            "contact_phone": self.contact_phone,
            "line1": self.line1,
            "line2": self.line2,
            "city": self.city,
            "state": self.state,
            "postal_code": self.postal_code,
            "country": self.country,
        }
