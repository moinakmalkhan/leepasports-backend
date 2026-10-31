import pytest
from django.core import mail

from apps.accounts import tokens
from apps.accounts.models import NewsletterSubscriber, User

pytestmark = pytest.mark.django_db


def test_register_sends_verification_and_subscribes(api):
    r = api.post(
        "/api/v1/auth/register/",
        {"email": "New@Example.com", "password": "Sup3rSecurePass!", "first_name": "Sara", "phone": "03001112222"},
        format="json",
    )
    assert r.status_code == 201 and "access" in r.data and "refresh" in r.data
    assert User.objects.filter(email="new@example.com").exists()
    assert NewsletterSubscriber.objects.filter(email="new@example.com", is_active=True).exists()
    assert any("Verify" in m.subject or "verify" in m.body.lower() for m in mail.outbox)


def test_login_wrong_password(api, customer):
    r = api.post("/api/v1/auth/login/", {"email": customer.email, "password": "nope"}, format="json")
    assert r.status_code == 401 and r.data["detail"] == "Incorrect email or password."


def test_refresh_rotates_and_blacklists(auth):
    old = auth.tokens["refresh"]
    first = auth.post("/api/v1/auth/refresh/", {"refresh": old}, format="json")
    assert first.status_code == 200 and first.data["refresh"] != old
    assert auth.post("/api/v1/auth/refresh/", {"refresh": old}, format="json").status_code == 401


def test_password_reset_flow(api, db):
    user = User.objects.create_user(email="r@example.com", password="Sup3rSecurePass!")
    token = tokens.make_token(user, tokens.RESET_SALT)
    assert (
        api.post(
            "/api/v1/auth/password/reset/confirm/", {"token": token, "password": "An0therSecurePass!"}, format="json"
        ).status_code
        == 200
    )
    assert (
        api.post("/api/v1/auth/login/", {"email": user.email, "password": "An0therSecurePass!"}, format="json").status_code == 200
    )


def test_addresses_crud_and_default(auth):
    r = auth.post(
        "/api/v1/accounts/addresses/",
        {
            "full_name": "Ali",
            "phone": "03001234567",
            "line1": "Flat 3",
            "city": "Karachi",
            "province": "Sindh",
            "is_default": True,
        },
        format="json",
    )
    assert r.status_code == 201 and r.data["is_default"] is True
    lst = auth.get("/api/v1/accounts/addresses/")
    assert len(lst.data) == 2 and sum(1 for a in lst.data if a["is_default"]) == 1
    assert auth.delete(f"/api/v1/accounts/addresses/{r.data['id']}/").status_code == 204


def test_newsletter_and_provinces(api):
    assert api.post("/api/v1/accounts/newsletter/", {"email": "fan@example.com"}, format="json").status_code == 201
    assert "Punjab" in api.get("/api/v1/accounts/provinces/").data


def test_marketing_toggle_syncs_newsletter(auth, customer):
    from apps.accounts.models import NewsletterSubscriber

    auth.patch("/api/v1/accounts/me/", {"marketing_opt_in": True}, format="json")
    customer.refresh_from_db()
    assert auth.patch("/api/v1/accounts/me/", {"marketing_opt_in": False}, format="json").status_code == 200
    sub = NewsletterSubscriber.objects.filter(email=customer.email).first()
    assert sub is None or sub.is_active is False
    assert auth.patch("/api/v1/accounts/me/", {"marketing_opt_in": True}, format="json").status_code == 200
    assert NewsletterSubscriber.objects.get(email=customer.email).is_active is True
