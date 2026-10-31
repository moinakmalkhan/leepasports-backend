from decimal import Decimal

from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector, SearchVectorField
from django.db import models
from django.db.models import Q
from django_extensions.db.fields import AutoSlugField

from apps.core.models import TimeStampedModel, UUIDModel


class Gender(models.TextChoices):
    MEN = "men", "Men"
    WOMEN = "women", "Women"
    UNISEX = "unisex", "Unisex"
    BOYS = "boys", "Boys"
    GIRLS = "girls", "Girls"
    YOUTH = "youth", "Youth"


class CategoryQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def with_product_counts(self):
        """Annotate direct active-product count. Subtree totals are computed in
        `services.category_tree` from the materialised path in one pass."""
        return self.annotate(direct_product_count=models.Count("products", filter=Q(products__is_active=True), distinct=True))


class Category(UUIDModel):
    """Category tree stored with a materialised path for O(1) subtree lookups.

    `path` is built from zero-padded ids ("0001.0007.0012"), so every descendant
    of a node satisfies `path__startswith=node.path`. This keeps "products in
    this category and all sub-categories" a single indexed range scan.
    """

    name = models.CharField(max_length=120)
    slug = AutoSlugField(populate_from="name", max_length=140, unique=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    path = models.CharField(max_length=255, editable=False, db_index=True, default="")
    depth = models.PositiveSmallIntegerField(default=0, editable=False)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="categories/", blank=True)
    icon = models.CharField(max_length=40, blank=True, help_text="Lucide icon name used by the storefront.")
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    meta_title = models.CharField(max_length=160, blank=True)
    meta_description = models.CharField(max_length=320, blank=True)

    objects = CategoryQuerySet.as_manager()

    class Meta:
        verbose_name_plural = "categories"
        ordering = ("sort_order", "name")
        indexes = [models.Index(fields=["parent", "is_active", "sort_order"])]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        new_path = f"{self.parent.path}.{self.pk:04d}" if self.parent_id else f"{self.pk:04d}"
        new_depth = (self.parent.depth + 1) if self.parent_id else 0
        if new_path != self.path or new_depth != self.depth:
            old_path = self.path
            self.path, self.depth = new_path, new_depth
            type(self).objects.filter(pk=self.pk).update(path=new_path, depth=new_depth)
            if old_path:
                for child in self.children.all():
                    child.save()

    def descendants_q(self) -> Q:
        return Q(path__startswith=self.path)


class Fabric(UUIDModel):
    """A fabric sourced from Pakistani mills (Faisalabad / Karachi / Lahore).

    Prices are kept in PKR per kg exactly as mills quote them; the storefront
    converts to the selling currency at the current `pricing.ExchangeRate`.
    Changing a fabric's price here changes every product that uses it.
    """

    class Quality(models.TextChoices):
        ECONOMY = "economy", "Economy"
        STANDARD = "standard", "Standard"
        PREMIUM = "premium", "Premium"
        ELITE = "elite", "Elite / Pro"

    class Unit(models.TextChoices):
        KG = "kg", "per kg"
        METER = "m", "per meter"

    name = models.CharField(max_length=120, unique=True)
    slug = AutoSlugField(populate_from="name", max_length=140, unique=True)
    composition = models.CharField(max_length=160, help_text="e.g. 100% Polyester, 92% Polyester 8% Spandex")
    gsm = models.PositiveSmallIntegerField(help_text="Grams per square metre")
    quality = models.CharField(max_length=10, choices=Quality.choices, default=Quality.STANDARD)
    quality_rank = models.PositiveSmallIntegerField(default=2, help_text="1 lowest … 4 highest; used for sorting")
    price_pkr = models.DecimalField(max_digits=10, decimal_places=2, help_text="Mill price in PKR")
    price_unit = models.CharField(max_length=2, choices=Unit.choices, default=Unit.KG)
    width_inches = models.PositiveSmallIntegerField(default=72)
    description = models.TextField(blank=True)
    features = ArrayField(models.CharField(max_length=60), default=list, blank=True)
    best_for = ArrayField(models.CharField(max_length=60), default=list, blank=True)
    typical_mills = models.CharField(max_length=200, blank=True, help_text="Source region / mills")
    is_available_in_pakistan = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    image = models.ImageField(upload_to="fabrics/", blank=True)
    swatch_color = models.CharField(max_length=7, default="#9CA3AF", help_text="Hex used when no image")
    price_updated_at = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ("quality_rank", "price_pkr")
        indexes = [models.Index(fields=["is_active", "quality_rank"])]

    def __str__(self):
        return f"{self.name} ({self.gsm} GSM)"


class SizeGroup(models.Model):
    """e.g. Adult alpha (XS–5XL), Youth (YXS–YXL), Numeric (28–44)."""

    name = models.CharField(max_length=60, unique=True)
    slug = AutoSlugField(populate_from="name", max_length=60, unique=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("sort_order",)

    def __str__(self):
        return self.name


class Size(models.Model):
    group = models.ForeignKey(SizeGroup, on_delete=models.CASCADE, related_name="sizes")
    label = models.CharField(max_length=12)
    sort_order = models.PositiveSmallIntegerField(default=0)
    # Larger sizes consume more fabric – surcharge as % of unit price (e.g. 2XL +8%).
    surcharge_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    chest_cm = models.CharField(max_length=20, blank=True)
    length_cm = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ("group__sort_order", "sort_order")
        constraints = [models.UniqueConstraint(fields=["group", "label"], name="uniq_size_per_group")]

    def __str__(self):
        return f"{self.group.name} {self.label}"


class ProductQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True, category__is_active=True)

    def for_listing(self):
        """Everything a product card needs, in two queries regardless of page size."""
        return (
            self.active()
            .select_related("category", "base_fabric")
            .prefetch_related(
                models.Prefetch(
                    "images", queryset=ProductImage.objects.order_by("-is_primary", "sort_order")[:1], to_attr="primary_images"
                ),
            )
        )

    def for_detail(self):
        return (
            self.active()
            .select_related("category", "base_fabric", "size_group")
            .prefetch_related(
                "images",
                models.Prefetch(
                    "fabric_options",
                    queryset=ProductFabricOption.objects.select_related("fabric")
                    .filter(fabric__is_active=True)
                    .order_by("fabric__quality_rank", "fabric__price_pkr"),
                ),
                models.Prefetch(
                    "size_options",
                    queryset=ProductSizeOption.objects.select_related("size")
                    .filter(is_active=True)
                    .order_by("gender", "size__sort_order"),
                ),
                models.Prefetch("volume_tiers"),
            )
        )

    def in_category(self, category: Category):
        return self.filter(category__path__startswith=category.path)


class Product(UUIDModel):
    name = models.CharField(max_length=200)
    slug = AutoSlugField(populate_from="name", max_length=220, unique=True)
    sku = models.CharField(max_length=40, unique=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    short_description = models.CharField(max_length=300, blank=True)
    description = models.TextField(blank=True)
    specifications = models.JSONField(default=dict, blank=True, help_text='{"Collar": "Rib knit", "Fit": "Athletic"}')
    tags = ArrayField(models.CharField(max_length=40), default=list, blank=True)

    # --- pricing inputs --------------------------------------------------
    base_fabric = models.ForeignKey(Fabric, on_delete=models.PROTECT, related_name="base_products")
    fabric_consumption_kg = models.DecimalField(
        max_digits=6, decimal_places=3, default=Decimal("0.300"), help_text="Average fabric used per piece (kg)"
    )
    labor_price = models.DecimalField(
        max_digits=10, decimal_places=2, help_text="Cutting, stitching, printing, trims & margin per piece (selling currency)"
    )
    # Denormalised "from" price = labor + base fabric cost at the latest rate. Refreshed by signals/tasks.
    base_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, editable=False)
    compare_at_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    size_group = models.ForeignKey(SizeGroup, on_delete=models.PROTECT, related_name="products")
    genders = ArrayField(models.CharField(max_length=8, choices=Gender.choices), default=list)
    colors = ArrayField(models.CharField(max_length=40), default=list, blank=True)

    min_order_quantity = models.PositiveIntegerField(default=10)
    order_increment = models.PositiveIntegerField(default=1)
    lead_time_days = models.PositiveSmallIntegerField(default=21)
    is_made_to_order = models.BooleanField(default=True)
    stock_quantity = models.IntegerField(default=0, help_text="Only used when not made to order")
    weight_grams = models.PositiveIntegerField(default=250)

    is_customizable = models.BooleanField(default=True)
    customization_options = models.JSONField(
        default=dict,
        blank=True,
        help_text='{"logo_placements": ["Left chest", "Back"], "print_methods": ["Sublimation", "Screen print"], "name_number": true}',
    )

    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    is_new = models.BooleanField(default=False)
    view_count = models.PositiveIntegerField(default=0)
    order_count = models.PositiveIntegerField(default=0)
    meta_title = models.CharField(max_length=160, blank=True)
    meta_description = models.CharField(max_length=320, blank=True)

    # Full-text search vector maintained by Postgres itself (generated column).
    search_vector = models.GeneratedField(
        expression=(
            SearchVector("name", weight="A", config="english")
            + SearchVector("sku", weight="A", config="english")
            + SearchVector("short_description", weight="B", config="english")
            + SearchVector("description", weight="C", config="english")
        ),
        output_field=SearchVectorField(),
        db_persist=True,
    )

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ("-is_featured", "-order_count", "-created_at")
        indexes = [
            models.Index(fields=["category", "is_active"]),
            models.Index(fields=["is_active", "is_featured", "-order_count"], name="catalog_prod_featured_idx"),
            models.Index(fields=["is_active", "base_price"]),
            models.Index(fields=["is_active", "-created_at"]),
            GinIndex(fields=["search_vector"], name="catalog_prod_search_gin"),
            GinIndex(fields=["tags"], name="catalog_prod_tags_gin"),
            GinIndex(fields=["genders"], name="catalog_prod_genders_gin"),
            GinIndex(name="catalog_prod_name_trgm", fields=["name"], opclasses=["gin_trgm_ops"]),
        ]

    def __str__(self):
        return self.name

    @property
    def primary_image(self):
        images = getattr(self, "primary_images", None)
        if images is not None:
            return images[0] if images else None
        return self.images.order_by("-is_primary", "sort_order").first()


class ProductImage(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/%Y/%m/")
    alt = models.CharField(max_length=160, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_primary = models.BooleanField(default=False)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ("-is_primary", "sort_order")
        indexes = [models.Index(fields=["product", "is_primary", "sort_order"])]


class ProductFabricOption(models.Model):
    """Fabrics a product can be made from. Price is derived from the fabric's
    mill rate × consumption, plus an optional per-fabric adjustment (e.g. extra
    labour for bonded fabrics)."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="fabric_options")
    fabric = models.ForeignKey(Fabric, on_delete=models.CASCADE, related_name="product_options")
    price_adjustment = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    is_default = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["product", "fabric"], name="uniq_product_fabric")]

    def __str__(self):
        return f"{self.product_id} / {self.fabric_id}"


class ProductSizeOption(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="size_options")
    gender = models.CharField(max_length=8, choices=Gender.choices)
    size = models.ForeignKey(Size, on_delete=models.CASCADE, related_name="+")
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["product", "gender", "size"], name="uniq_product_gender_size")]
        indexes = [models.Index(fields=["product", "gender"])]

    def __str__(self):
        return f"{self.product_id} {self.gender} {self.size_id}"


class ProductView(models.Model):
    """Lightweight view log used for 'recently viewed' & recommendations.
    Rows are aggregated / pruned by a periodic task."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="+")
    user = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    session_key = models.CharField(max_length=64, blank=True)
    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "-viewed_at"]),
            models.Index(fields=["session_key", "-viewed_at"]),
            models.Index(fields=["product", "-viewed_at"]),
        ]

    def __str__(self):
        return f"view {self.product_id}"
