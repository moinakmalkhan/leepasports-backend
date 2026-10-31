from collections import defaultdict

from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, F, Q, Sum

from apps.core.cache import make_key
from apps.core.i18n import translate

from .models import Category, Product, ProductVariant


def category_tree(include_empty: bool = False) -> list[dict]:
    """Nested menu tree with subtree product counts; hides empty categories. Cached 10 min."""
    key = make_key("catalog", "tree", int(include_empty))
    tree = cache.get(key)
    if tree is not None:
        return tree
    categories = list(
        Category.objects.active()
        .annotate(direct_count=Count("products", filter=Q(products__is_active=True), distinct=True))
        .order_by("depth", "sort_order", "name")
    )
    by_id = {c.id: c for c in categories}
    subtree = defaultdict(int)
    for cat in sorted(categories, key=lambda c: -c.depth):
        subtree[cat.id] += cat.direct_count
        if cat.parent_id in by_id:
            subtree[cat.parent_id] += subtree[cat.id]
    nodes, roots = {}, []
    for cat in categories:
        if not include_empty and subtree[cat.id] == 0:
            continue
        node = {
            "id": str(cat.uid),
            "name": translate(cat, "name"),
            "slug": cat.slug,
            "icon": cat.icon,
            "image": cat.image.url if cat.image else None,
            "description": translate(cat, "description"),
            "product_count": subtree[cat.id],
            "depth": cat.depth,
            "show_in_menu": cat.show_in_menu,
            "children": [],
        }
        nodes[cat.id] = node
        if cat.parent_id and cat.parent_id in nodes:
            nodes[cat.parent_id]["children"].append(node)
        elif cat.parent_id is None:
            roots.append(node)
    cache.set(key, roots, 600)
    return roots


def category_breadcrumbs(category: Category) -> list[dict]:
    ids = [int(part) for part in category.path.split(".") if part]
    rows = {c.id: c for c in Category.objects.filter(id__in=ids)}
    return [{"name": translate(rows[i], "name"), "slug": rows[i].slug} for i in ids if i in rows]


def record_view(product: Product, user=None, session_key: str = ""):
    from .models import ProductView

    Product.objects.filter(pk=product.pk).update(view_count=F("view_count") + 1)
    if (user and user.is_authenticated) or session_key:
        ProductView.objects.create(
            product=product, user=user if user and user.is_authenticated else None, session_key=session_key[:64]
        )


def refresh_total_stock(product_id: int):
    total = ProductVariant.objects.filter(product_id=product_id, is_active=True).aggregate(s=Sum("stock"))["s"] or 0
    Product.objects.filter(pk=product_id).update(total_stock=total)
    return total


@transaction.atomic
def adjust_stock(variant_id: int, delta: int, *, reason: str = "") -> ProductVariant:
    """Atomically change stock (negative = sell). Raises if it would go below zero."""
    from apps.core.exceptions import BusinessError

    variant = ProductVariant.objects.select_for_update().select_related("product").order_by("pk").get(pk=variant_id)
    if variant.stock + delta < 0:
        raise BusinessError(f"Only {variant.stock} left of {variant.product.name} ({variant.label}).")
    variant.stock += delta
    variant.save(update_fields=["stock", "updated_at"])
    refresh_total_stock(variant.product_id)
    if delta > 0 and variant.stock - delta <= 0:
        from .tasks import notify_back_in_stock

        notify_back_in_stock.delay(variant.pk)
    return variant


def facets(queryset) -> dict:
    """Filter values with counts for the current result set (sizes, colours, price bounds)."""
    from django.db.models import Max, Min

    variants = ProductVariant.objects.filter(product__in=queryset.values("pk"), is_active=True)
    sizes = list(
        variants.exclude(size__isnull=True)
        .values("size__label", "size_id", "size__sort_order")
        .annotate(n=Count("product", distinct=True))
        .order_by("size__sort_order")
    )
    colors = list(
        variants.exclude(color__isnull=True)
        .values("color_id", "color__name", "color__slug", "color__hex", "color__translations")
        .annotate(n=Count("product", distinct=True))
        .order_by("color__sort_order")
    )
    from django.utils import translation

    lang = translation.get_language() or "en"
    price = queryset.aggregate(min=Min("price"), max=Max("price"))
    genders = list(queryset.values("gender").annotate(n=Count("id")).order_by("gender"))
    return {
        "sizes": [{"label": s["size__label"], "count": s["n"]} for s in sizes],
        "colors": [
            {
                "name": ((c["color__translations"] or {}).get(lang) or {}).get("name") or c["color__name"],
                "slug": c["color__slug"],
                "hex": c["color__hex"],
                "count": c["n"],
            }
            for c in colors
        ],
        "price": {"min": price["min"] or 0, "max": price["max"] or 0},
        "genders": [{"value": g["gender"], "count": g["n"]} for g in genders],
    }
