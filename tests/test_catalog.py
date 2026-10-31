import pytest

from apps.catalog.models import ProductVariant

pytestmark = pytest.mark.django_db


def test_category_tree_hides_empty(api):
    r = api.get("/api/v1/catalog/categories/")
    slugs = {n["slug"] for n in r.data}
    assert "men" in slugs and "gift-cards" not in slugs
    men = next(n for n in r.data if n["slug"] == "men")
    assert men["product_count"] >= 10 and men["children"]


def test_listing_filters_and_pagination(api):
    r = api.get("/api/v1/catalog/products/?category=men&page_size=6")
    assert r.status_code == 200 and len(r.data["results"]) == 6 and r.data["total_pages"] >= 2
    sale = api.get("/api/v1/catalog/products/?on_sale=true")
    assert sale.data["count"] >= 5 and all(p["is_on_sale"] for p in sale.data["results"])
    sized = api.get("/api/v1/catalog/products/?size=M&color=black&in_stock=true")
    assert sized.data["count"] >= 1
    priced = api.get("/api/v1/catalog/products/?min_price=4000&ordering=price")
    assert all(float(p["price"]) >= 4000 for p in priced.data["results"])


def test_facets(api):
    r = api.get("/api/v1/catalog/products/facets/?category=men")
    assert r.status_code == 200 and r.data["sizes"] and r.data["colors"] and r.data["price"]["max"] > 0


def test_product_detail_variants_and_images(api, product):
    r = api.get(f"/api/v1/catalog/products/{product.slug}/")
    assert r.status_code == 200
    assert len(r.data["variants"]) == 4 * 6 and r.data["size_group"]["sizes"]
    assert r.data["breadcrumbs"][0]["slug"] == "men" and r.data["discount_percent"] > 0
    assert any(v["in_stock"] for v in r.data["variants"])


def test_collections_and_home_feeds(api):
    cols = api.get("/api/v1/catalog/collections/")
    assert any(c["slug"] == "sale" and c["product_count"] > 0 for c in cols.data)
    assert len(api.get("/api/v1/catalog/products/new-arrivals/").data) > 0
    assert len(api.get("/api/v1/catalog/products/best-sellers/").data) > 0


def test_search_suggest_and_results(api):
    assert api.get("/api/v1/search/suggest/?q=hodie").data["products"]
    r = api.get("/api/v1/search/?q=joggers")
    assert r.status_code == 200 and r.data["count"] >= 1
    assert api.get("/api/v1/search/?q=track pants").data["count"] >= 1  # synonym


def test_stock_alert(api, product):
    v = ProductVariant.objects.filter(product=product, stock=0).first() or ProductVariant.objects.filter(product=product).first()
    r = api.post("/api/v1/catalog/stock-alerts/", {"variant": str(v.uid), "email": "me@example.com"}, format="json")
    assert r.status_code == 201


def test_storefront_content(api):
    r = api.get("/api/v1/content/storefront/")
    assert r.status_code == 200 and r.data["announcements"] and r.data["pages"]
    assert api.get("/api/v1/content/pages/returns-exchanges/").status_code == 200
    assert len(api.get("/api/v1/content/faq/").data) >= 5
