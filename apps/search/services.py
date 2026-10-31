"""
Search is lexical + fuzzy + behavioural, all inside PostgreSQL:

1. `websearch_to_tsquery` full-text match on the generated `search_vector`
   (weighted name > sku > brand/short description > material/description), ranked with `ts_rank_cd`.
2. Trigram similarity on the product name catches typos ("hodie", "trak suit").
3. Synonym expansion from the `Synonym` table ("joggers" → "track pants").
4. Popularity (sales_count, view_count) and, for signed-in shoppers, a boost for
   categories they've bought from before.

Autocomplete results are cached per normalised query for 5 minutes; the
namespace is bumped whenever the catalog changes.
"""

import re

from django.contrib.postgres.search import SearchQuery, SearchRank, TrigramSimilarity, TrigramWordSimilarity
from django.core.cache import cache
from django.db.models import Case, Count, F, FloatField, Q, Value, When
from django.db.models.functions import Greatest

from apps.catalog.models import Category, Product
from apps.core.cache import make_key

from .models import Synonym

_WS = re.compile(r"\s+")
_LATIN = re.compile(r"^[\x00-\x7f]*$")


def normalize(q: str) -> str:
    return _WS.sub(" ", (q or "").strip().lower())[:200]


def synonyms() -> dict[str, list[str]]:
    key = "search:synonyms"
    data = cache.get(key)
    if data is None:
        data = {s.term.lower(): [e.strip() for e in s.expansions.split(",") if e.strip()] for s in Synonym.objects.all()}
        cache.set(key, data, 3600)
    return data


def expand(q: str) -> str:
    table = synonyms()
    parts = []
    for word in q.split():
        exps = table.get(word)
        parts.append(f"({word} OR {' OR '.join(exps)})" if exps else word)
    return " ".join(parts)


def _authenticated(user) -> bool:
    return user is not None and getattr(user, "is_authenticated", False)


def _user_category_boost(user):
    if not _authenticated(user):
        return Value(0.0, output_field=FloatField())
    key = f"search:boost:{user.pk}"
    cats = cache.get(key)
    if cats is None:
        from apps.orders.models import OrderItem

        cats = list(
            OrderItem.objects.filter(order__user=user, product__isnull=False)
            .values_list("product__category_id", flat=True)
            .distinct()[:20]
        )
        cache.set(key, cats, 900)
    if not cats:
        return Value(0.0, output_field=FloatField())
    return Case(When(category_id__in=cats, then=Value(0.15)), default=Value(0.0), output_field=FloatField())


def product_search_queryset(q: str, user=None):
    q = normalize(q)
    if not q:
        return Product.objects.for_listing().order_by("-is_featured", "-sales_count")
    if not _LATIN.match(q):
        return _translated_search_queryset(q)
    ts = SearchQuery(expand(q), search_type="websearch", config="english")
    return (
        Product.objects.for_listing()
        .annotate(
            rank=SearchRank(F("search_vector"), ts, cover_density=True),
            similarity=Greatest(TrigramWordSimilarity(q, "name"), TrigramSimilarity("sku", q), TrigramSimilarity("name", q)),
            boost=_user_category_boost(user),
        )
        .annotate(score=F("rank") + F("similarity") + F("boost") + (F("sales_count") * Value(0.0005)))
        .filter(Q(search_vector=ts) | Q(similarity__gte=0.45) | Q(tags__overlap=q.split()))
        .order_by("-score", "-sales_count")
    )


def _translated_search_queryset(q: str):
    """Urdu / Arabic queries: match the translated name, description and category name stored in JSONB."""
    terms = [t for t in q.split() if t]
    cond = Q()
    for lang in ("ur", "ar"):
        match = Q()
        for term in terms:
            match &= (
                Q(**{f"translations__{lang}__name__icontains": term})
                | Q(**{f"translations__{lang}__short_description__icontains": term})
                | Q(**{f"category__translations__{lang}__name__icontains": term})
            )
        cond |= match
    return Product.objects.for_listing().filter(cond).order_by("-is_featured", "-sales_count")


def suggest(q: str, user=None, limit: int = 6, request=None) -> dict:
    q = normalize(q)
    if len(q) < 2:
        return {"products": [], "categories": [], "collections": [], "query": q}
    key = make_key("search", "suggest", q, user.pk if _authenticated(user) else 0)
    data = cache.get(key)
    if data is not None:
        return data

    from apps.catalog.models import Collection
    from apps.catalog.serializers import ProductCardSerializer

    products = list(product_search_queryset(q, user)[:limit])
    name_match = (
        Q(name__icontains=q) | Q(similarity__gt=0.3)
        if _LATIN.match(q)
        else Q(translations__ur__name__icontains=q) | Q(translations__ar__name__icontains=q)
    )
    categories = list(
        Category.objects.active()
        .annotate(similarity=TrigramSimilarity("name", q))
        .filter(name_match)
        .annotate(n=Count("products", filter=Q(products__is_active=True)))
        .filter(n__gt=0)
        .order_by("-similarity")[:3]
    )
    collection_match = (
        Q(name__icontains=q)
        if _LATIN.match(q)
        else Q(translations__ur__name__icontains=q) | Q(translations__ar__name__icontains=q)
    )
    collections = list(Collection.objects.filter(collection_match, is_active=True)[:2])
    from apps.core.i18n import translate

    data = {
        "query": q,
        "products": ProductCardSerializer(products, many=True, context={"request": request}).data,
        "categories": [{"name": translate(c, "name"), "slug": c.slug, "product_count": c.n} for c in categories],
        "collections": [{"name": translate(c, "name"), "slug": c.slug} for c in collections],
    }
    cache.set(key, data, 300)
    return data


def trending_queries(limit: int = 8) -> list[str]:
    from datetime import timedelta

    from django.utils import timezone

    from .models import SearchQuery as SQ

    key = make_key("search", "trending")
    data = cache.get(key)
    if data is None:
        since = timezone.now() - timedelta(days=30)
        rows = (
            SQ.objects.filter(created_at__gte=since, result_count__gt=0)
            .values("normalized")
            .annotate(n=Count("id"))
            .order_by("-n")[:limit]
        )
        data = [r["normalized"] for r in rows]
        cache.set(key, data, 1800)
    return data


def recommendations_for_product(product: Product, limit: int = 8):
    """'Bought together' from order history, padded with same-category best sellers."""
    from apps.orders.models import OrderItem

    key = make_key("search", "reco", product.pk)
    ids = cache.get(key)
    if ids is None:
        order_ids = OrderItem.objects.filter(product=product).values("order_id")[:500]
        together = (
            OrderItem.objects.filter(order_id__in=order_ids, product__isnull=False)
            .exclude(product=product)
            .values("product_id")
            .annotate(n=Count("id"))
            .order_by("-n")[:limit]
        )
        ids = [r["product_id"] for r in together]
        if len(ids) < limit:
            extra = (
                Product.objects.active()
                .filter(category=product.category)
                .exclude(pk__in=ids + [product.pk])
                .order_by("-sales_count", "-view_count")
                .values_list("id", flat=True)[: limit - len(ids)]
            )
            ids += list(extra)
        cache.set(key, ids, 1800)
    products = {p.id: p for p in Product.objects.for_listing().filter(id__in=ids)}
    return [products[i] for i in ids if i in products]


def recommendations_for_user(user, session_key: str = "", limit: int = 8):
    """Personalised: categories recently viewed or bought → best sellers there; falls back to best sellers."""
    from apps.catalog.models import ProductView

    viewed = Q(user=user) if _authenticated(user) else Q(session_key=session_key) if session_key else None
    cat_ids: list[int] = []
    seen: list[int] = []
    if viewed is not None:
        for pid, cid in (
            ProductView.objects.filter(viewed).order_by("-viewed_at").values_list("product_id", "product__category_id")[:30]
        ):
            seen.append(pid)
            if cid not in cat_ids:
                cat_ids.append(cid)
    if _authenticated(user):
        from apps.orders.models import OrderItem

        for cid in OrderItem.objects.filter(order__user=user).values_list("product__category_id", flat=True).distinct()[:5]:
            if cid and cid not in cat_ids:
                cat_ids.append(cid)
    qs = Product.objects.for_listing().exclude(pk__in=seen[:10])
    if cat_ids:
        qs = qs.annotate(pref=Case(When(category_id__in=cat_ids[:6], then=Value(1)), default=Value(0))).order_by(
            "-pref", "-sales_count", "-view_count"
        )
    else:
        qs = qs.order_by("-sales_count", "-view_count")
    return list(qs[:limit])


def recently_viewed(user, session_key: str = "", limit: int = 8):
    from apps.catalog.models import ProductView

    if _authenticated(user):
        flt = Q(user=user)
    elif session_key:
        flt = Q(session_key=session_key)
    else:
        return []
    ids: list[int] = []
    for pid in ProductView.objects.filter(flt).order_by("-viewed_at").values_list("product_id", flat=True)[:50]:
        if pid not in ids:
            ids.append(pid)
        if len(ids) >= limit:
            break
    products = {p.id: p for p in Product.objects.for_listing().filter(id__in=ids)}
    return [products[i] for i in ids if i in products]
