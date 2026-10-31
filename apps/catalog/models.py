from decimal import Decimal

from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector, SearchVectorField
from django.db import models
from django.db.models import Q
from django_extensions.db.fields import AutoSlugField

from apps.core.models import TimeStampedModel, UUIDModel
from apps.core.translation import TranslatableModel


class Gender(models.TextChoices):
    MEN = "men", "Men"
    WOMEN = "women", "Women"
    UNISEX = "unisex", "Unisex"
    KIDS = "kids", "Kids"


class CategoryQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class Category(TranslatableModel, UUIDModel):
    """Category tree with a materialised path ("0001.0007") so a whole subtree
    is one indexed `path__startswith` filter."""

    name = models.CharField(max_length=120)
    slug = AutoSlugField(populate_from="name", overwrite_on_add=False, max_length=140, unique=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    path = models.CharField(max_length=255, editable=False, db_index=True, default="")
    depth = models.PositiveSmallIntegerField(default=0, editable=False)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="categories/", blank=True)
    icon = models.CharField(max_length=40, blank=True, help_text="Lucide icon name used by the storefront")
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    show_in_menu = models.BooleanField(default=True)
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


class Collection(TranslatableModel, UUIDModel):
    """Curated merchandising groups: "New arrivals", "Summer drop", "Under Rs 2,000"."""

    name = models.CharField(max_length=120)
    slug = AutoSlugField(populate_from="name", overwrite_on_add=False, max_length=140, unique=True)
    tagline = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="collections/", blank=True)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False, help_text="Show on the home page")
    sort_order = models.PositiveSmallIntegerField(default=0)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("sort_order", "name")

    def __str__(self):
        return self.name


class Color(TranslatableModel, models.Model):
    name = models.CharField(max_length=40, unique=True)
    slug = AutoSlugField(populate_from="name", overwrite_on_add=False, max_length=50, unique=True)
    hex = models.CharField(max_length=7, default="#000000")
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "name")

    def __str__(self):
        return self.name


class SizeGroup(models.Model):
    name = models.CharField(max_length=60, unique=True)
    slug = AutoSlugField(populate_from="name", overwrite_on_add=False, max_length=60, unique=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    guide = models.JSONField(
        default=list, blank=True, help_text='Size chart rows: [{"size": "M", "chest": "96-101", "length": "70"}]'
    )

    class Meta:
        ordering = ("sort_order",)

    def __str__(self):
        return self.name


class Size(models.Model):
    group = models.ForeignKey(SizeGroup, on_delete=models.CASCADE, related_name="sizes")
    label = models.CharField(max_length=12)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("group__sort_order", "sort_order")
        constraints = [models.UniqueConstraint(fields=["group", "label"], name="uniq_size_per_group")]

    def __str__(self):
        return self.label


class ProductQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True, category__is_active=True)

    def for_listing(self):
        """Everything a product card needs: 3 queries regardless of page size."""
        return (
            self.active()
            .select_related("category")
            .prefetch_related(
                models.Prefetch(
                    "images", queryset=ProductImage.objects.order_by("-is_primary", "sort_order"), to_attr="all_images"
                ),
                models.Prefetch(
                    "variants",
                    queryset=ProductVariant.objects.filter(is_active=True).select_related("color", "size"),
                    to_attr="active_variants",
                ),
            )
        )

    def for_detail(self):
        return (
            self.active()
            .select_related("category", "size_group")
            .prefetch_related(
                models.Prefetch(
                    "images",
                    queryset=ProductImage.objects.select_related("color").order_by("-is_primary", "sort_order"),
                    to_attr="all_images",
                ),
                models.Prefetch(
                    "variants",
                    queryset=ProductVariant.objects.filter(is_active=True)
                    .select_related("color", "size")
                    .order_by("color__sort_order", "size__sort_order"),
                    to_attr="active_variants",
                ),
                "collections",
                "size_group__sizes",
            )
        )


class Product(TranslatableModel, UUIDModel):
    name = models.CharField(max_length=200)
    slug = AutoSlugField(populate_from="name", overwrite_on_add=False, max_length=220, unique=True)
    sku = models.CharField(max_length=40, unique=True, help_text="Base SKU; variants append -COLOR-SIZE")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    collections = models.ManyToManyField(Collection, blank=True, related_name="products")
    brand = models.CharField(max_length=60, default="Chobbar")
    gender = models.CharField(max_length=6, choices=Gender.choices, default=Gender.MEN, db_index=True)

    short_description = models.CharField(max_length=300, blank=True)
    description = models.TextField(blank=True)
    material = models.CharField(max_length=160, blank=True, help_text="e.g. 100% polyester micro-mesh, 150 GSM")
    care_instructions = models.TextField(blank=True)
    specifications = models.JSONField(default=dict, blank=True, help_text='{"Fit": "Regular", "Neck": "Crew"}')
    tags = ArrayField(models.CharField(max_length=40), default=list, blank=True)

    price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Selling price (PKR)")
    compare_at_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, help_text="Original price when on sale"
    )
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Internal — never exposed")

    size_group = models.ForeignKey(SizeGroup, null=True, blank=True, on_delete=models.PROTECT, related_name="products")
    weight_grams = models.PositiveIntegerField(default=300)

    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    is_new = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)

    rating_avg = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    rating_count = models.PositiveIntegerField(default=0)
    view_count = models.PositiveIntegerField(default=0)
    sales_count = models.PositiveIntegerField(default=0)
    # Denormalised from variants so listing filters never join: total stock + available sizes/colours.
    total_stock = models.IntegerField(default=0)
    meta_title = models.CharField(max_length=160, blank=True)
    meta_description = models.CharField(max_length=320, blank=True)

    search_vector = models.GeneratedField(
        expression=(
            SearchVector("name", weight="A", config="english")
            + SearchVector("sku", weight="A", config="english")
            + SearchVector("brand", weight="B", config="english")
            + SearchVector("short_description", weight="B", config="english")
            + SearchVector("material", weight="C", config="english")
            + SearchVector("description", weight="C", config="english")
        ),
        output_field=SearchVectorField(),
        db_persist=True,
    )

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ("-is_featured", "-sales_count", "-created_at")
        indexes = [
            models.Index(fields=["category", "is_active"]),
            models.Index(fields=["is_active", "is_featured", "-sales_count"], name="catalog_prod_featured_idx"),
            models.Index(fields=["is_active", "price"]),
            models.Index(fields=["is_active", "-created_at"]),
            models.Index(fields=["is_active", "gender"]),
            models.Index(fields=["is_active", "-rating_avg"]),
            GinIndex(fields=["search_vector"], name="catalog_prod_search_gin"),
            GinIndex(fields=["tags"], name="catalog_prod_tags_gin"),
            GinIndex(name="catalog_prod_name_trgm", fields=["name"], opclasses=["gin_trgm_ops"]),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(price__gte=0), name="product_price_non_negative"),
            models.CheckConstraint(
                condition=Q(compare_at_price__isnull=True) | Q(compare_at_price__gt=models.F("price")),
                name="product_compare_above_price",
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def is_on_sale(self) -> bool:
        return bool(self.compare_at_price and self.compare_at_price > self.price)

    @property
    def discount_percent(self) -> int:
        if not self.is_on_sale:
            return 0
        return int(round((self.compare_at_price - self.price) / self.compare_at_price * 100))

    @property
    def primary_image(self):
        images = getattr(self, "all_images", None)
        if images is not None:
            return images[0] if images else None
        return self.images.order_by("-is_primary", "sort_order").first()

    @property
    def in_stock(self) -> bool:
        return self.total_stock > 0


class ProductVariant(UUIDModel):
    """A sellable unit: product × colour × size, with its own SKU, stock and optional price."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    color = models.ForeignKey(Color, null=True, blank=True, on_delete=models.PROTECT, related_name="variants")
    size = models.ForeignKey(Size, null=True, blank=True, on_delete=models.PROTECT, related_name="variants")
    sku = models.CharField(max_length=60, unique=True)
    barcode = models.CharField(max_length=64, blank=True)
    price_override = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    stock = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("color__sort_order", "size__sort_order")
        constraints = [
            models.UniqueConstraint(
                fields=["product", "color", "size"], name="uniq_variant_per_color_size", nulls_distinct=False
            ),
            models.CheckConstraint(condition=Q(stock__gte=0), name="variant_stock_non_negative"),
        ]
        indexes = [models.Index(fields=["product", "is_active"]), models.Index(fields=["stock"])]

    def __str__(self):
        return self.sku

    @property
    def price(self) -> Decimal:
        return self.price_override if self.price_override is not None else self.product.price

    @property
    def label(self) -> str:
        return (
            " / ".join(
                part for part in (self.color.name if self.color_id else "", self.size.label if self.size_id else "") if part
            )
            or "One size"
        )

    @property
    def in_stock(self) -> bool:
        return self.stock > 0


class ProductImage(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    color = models.ForeignKey(
        Color, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", help_text="Shown when this colour is selected"
    )
    image = models.ImageField(upload_to="products/%Y/%m/")
    alt = models.CharField(max_length=160, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_primary = models.BooleanField(default=False)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ("-is_primary", "sort_order")
        indexes = [models.Index(fields=["product", "is_primary", "sort_order"])]

    def __str__(self):
        return f"{self.product_id} image {self.pk}"


class ProductView(models.Model):
    """Lightweight view log for 'recently viewed' and recommendations; pruned periodically."""

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


class StockAlert(TimeStampedModel):
    """'Notify me when back in stock' for a variant."""

    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name="stock_alerts")
    email = models.EmailField()
    user = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["variant", "email"], name="uniq_stock_alert")]
        indexes = [models.Index(fields=["variant", "notified_at"])]

    def __str__(self):
        return f"{self.email} → {self.variant_id}"
