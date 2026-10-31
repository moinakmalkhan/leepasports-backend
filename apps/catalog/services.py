from collections import defaultdict

from django.core.cache import cache
from django.db.models import Count, Q

from apps.core.cache import make_key

from .models import Category, Product


def category_tree(include_empty: bool = False) -> list[dict]:
    """Nested category tree with subtree product counts.

    Only categories that (transitively) contain active products are returned,
    unless `include_empty`. Two queries, cached for 10 minutes and invalidated
    by the catalog signals whenever a product/category changes.
    """
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
    subtree_count = defaultdict(int)
    # Walk deepest first so counts roll up to ancestors in one pass.
    for cat in sorted(categories, key=lambda c: -c.depth):
        subtree_count[cat.id] += cat.direct_count
        if cat.parent_id in by_id:
            subtree_count[cat.parent_id] += subtree_count[cat.id]

    nodes = {}
    roots = []
    for cat in categories:
        if not include_empty and subtree_count[cat.id] == 0:
            continue
        node = {
            "id": str(cat.uid),
            "name": cat.name,
            "slug": cat.slug,
            "icon": cat.icon,
            "image": cat.image.url if cat.image else None,
            "description": cat.description,
            "product_count": subtree_count[cat.id],
            "depth": cat.depth,
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
    rows = Category.objects.filter(id__in=ids).values("id", "name", "slug")
    ordered = sorted(rows, key=lambda r: ids.index(r["id"]))
    return [{"name": r["name"], "slug": r["slug"]} for r in ordered]


def record_view(product: Product, user=None, session_key: str = ""):
    from django.db.models import F

    from .models import ProductView

    Product.objects.filter(pk=product.pk).update(view_count=F("view_count") + 1)
    if user is not None or session_key:
        ProductView.objects.create(
            product=product, user=user if user and user.is_authenticated else None, session_key=session_key[:64]
        )
