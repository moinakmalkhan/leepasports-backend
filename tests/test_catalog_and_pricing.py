from decimal import Decimal

import pytest

from apps.catalog.models import Category, Fabric, Product
from tests.conftest import size_breakdown

pytestmark = pytest.mark.django_db


def test_category_tree_hides_empty_categories(api):
    response = api.get("/api/v1/catalog/categories/")
    assert response.status_code == 200
    slugs = {node["slug"] for node in response.data}
    assert "teamwear" in slugs and "esports-apparel" not in slugs
    teamwear = next(n for n in response.data if n["slug"] == "teamwear")
    assert teamwear["product_count"] >= 10 and teamwear["children"]


def test_product_list_filters_by_category_subtree_and_paginates(api):
    response = api.get("/api/v1/catalog/products/?category=teamwear&page_size=5")
    assert response.status_code == 200
    assert response.data["count"] >= 10 and len(response.data["results"]) == 5 and response.data["total_pages"] >= 2
    assert response.data["next"]


def test_product_detail_has_fabric_and_size_options(api, product):
    response = api.get(f"/api/v1/catalog/products/{product.slug}/")
    assert response.status_code == 200
    assert len(response.data["fabric_options"]) == 5
    assert any(o["is_default"] for o in response.data["fabric_options"])
    genders = {o["gender"] for o in response.data["size_options"]}
    assert {"men", "women", "youth"} <= genders
    assert response.data["breadcrumbs"][0]["slug"] == "teamwear"


def test_price_quote_changes_with_fabric_and_volume(api, product):
    breakdown = size_breakdown(product, qty_each=4)  # 12 pcs
    cheap = api.post(
        "/api/v1/pricing/quote/",
        {"product": product.slug, "fabric": "polyester-interlock", "breakdown": breakdown},
        format="json",
    )
    premium = api.post(
        "/api/v1/pricing/quote/",
        {"product": product.slug, "fabric": "dot-knit-performance", "breakdown": breakdown},
        format="json",
    )
    assert cheap.status_code == premium.status_code == 200
    assert Decimal(str(premium.data["unit_price"])) > Decimal(str(cheap.data["unit_price"]))
    assert cheap.data["next_tier"]["min_quantity"] == 50
    bulk = api.post(
        "/api/v1/pricing/quote/",
        {"product": product.slug, "fabric": "polyester-interlock", "breakdown": size_breakdown(product, qty_each=40)},
        format="json",
    )
    assert Decimal(str(bulk.data["volume_discount_percent"])) == Decimal("10")
    assert Decimal(str(bulk.data["unit_price"])) < Decimal(str(cheap.data["unit_price"]))


def test_size_surcharge_applies_to_big_sizes(api, product):
    options = {o.size.label: o.size_id for o in product.size_options.all() if o.gender == "men"}
    breakdown = [
        {"gender": "men", "size_id": options["M"], "quantity": 5},
        {"gender": "men", "size_id": options["3XL"], "quantity": 5},
    ]
    response = api.post("/api/v1/pricing/quote/", {"product": product.slug, "breakdown": breakdown}, format="json")
    lines = {line["size_label"]: line for line in response.data["lines"]}
    assert Decimal(str(lines["3XL"]["unit_price"])) > Decimal(str(lines["M"]["unit_price"]))


def test_below_moq_rejected(api, product):
    response = api.post(
        "/api/v1/pricing/quote/", {"product": product.slug, "breakdown": size_breakdown(product, qty_each=1)}, format="json"
    )
    assert response.status_code == 400 and "Minimum order" in response.data["detail"]


def test_fabric_price_change_reprices_products(product):
    before = Product.objects.get(pk=product.pk).base_price
    fabric = Fabric.objects.get(slug="bird-eye-mesh")
    fabric.price_pkr = fabric.price_pkr * 2
    fabric.save()
    after = Product.objects.get(pk=product.pk).base_price
    assert after > before


def test_customer_group_discount_applied(auth, buyer, product):
    from apps.pricing.models import CustomerGroup

    company = buyer.memberships.first().company
    company.customer_group = CustomerGroup.objects.get(slug="distributor")
    company.save()
    response = auth.post(
        "/api/v1/pricing/quote/", {"product": product.slug, "breakdown": size_breakdown(product, qty_each=4)}, format="json"
    )
    assert Decimal(str(response.data["group_discount_percent"])) == Decimal("12")


def test_search_suggest_and_results(api):
    suggest = api.get("/api/v1/search/suggest/?q=jersy")
    assert suggest.status_code == 200 and suggest.data["products"]
    results = api.get("/api/v1/search/?q=hoodie")
    assert results.status_code == 200 and results.data["count"] >= 2
    assert all("hood" in p["name"].lower() or "hoodie" in p["name"].lower() for p in results.data["results"][:2])
    synonyms = api.get("/api/v1/search/?q=football kit")
    assert synonyms.data["count"] >= 1


def test_category_detail(api):
    response = api.get("/api/v1/catalog/categories/soccer-kits/")
    assert response.status_code == 200 and response.data["product_count"] == 3
    assert Category.objects.get(slug="soccer-kits").depth == 1
