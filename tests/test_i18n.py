import pytest

pytestmark = pytest.mark.django_db


def test_locale_detection_by_country_header(api):
    assert api.get("/api/v1/locale/", HTTP_CF_IPCOUNTRY="PK").data["language"] == "ur"
    sa = api.get("/api/v1/locale/", HTTP_CF_IPCOUNTRY="SA").data
    assert sa["language"] == "ar" and sa["rtl"] is True and sa["source"] == "country"
    assert api.get("/api/v1/locale/", HTTP_CF_IPCOUNTRY="GB").data["language"] == "en"


def test_explicit_choice_beats_country(api):
    r = api.get("/api/v1/locale/?lang=en", HTTP_CF_IPCOUNTRY="PK")
    assert r.data["language"] == "en" and r.data["source"] == "explicit"
    assert api.get("/api/v1/locale/", HTTP_X_LANGUAGE="ar").data["language"] == "ar"
    assert api.get("/api/v1/locale/", HTTP_ACCEPT_LANGUAGE="ur-PK,ur;q=0.9").data["language"] == "ur"


def test_catalog_is_translated_and_cached_per_language(api):
    en = api.get("/api/v1/catalog/categories/").data
    ur = api.get("/api/v1/catalog/categories/", HTTP_X_LANGUAGE="ur").data
    ar = api.get("/api/v1/catalog/categories/", HTTP_X_LANGUAGE="ar").data
    assert next(c for c in en if c["slug"] == "men")["name"] == "Men"
    assert next(c for c in ur if c["slug"] == "men")["name"] == "مردانہ"
    assert next(c for c in ar if c["slug"] == "men")["name"] == "رجال"
    p = api.get("/api/v1/catalog/products/essential-heavyweight-tee/", HTTP_X_LANGUAGE="ar")
    assert p.data["name"] == "تيشيرت أساسي ثقيل" and p.headers["Content-Language"] == "ar"
    assert api.get("/api/v1/content/storefront/", HTTP_X_LANGUAGE="ur").data["announcements"][0]["text"].startswith("3,000")
