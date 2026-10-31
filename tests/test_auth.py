import pytest
from django.core import mail

from apps.accounts import tokens
from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def test_register_creates_company_and_sends_verification(api):
    response = api.post(
        "/api/v1/auth/register/",
        {
            "email": "New@Example.com",
            "password": "Sup3rSecurePass!",
            "first_name": "Ava",
            "company_name": "Ava Athletics",
            "business_type": "retailer",
            "country": "US",
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    assert "access" in response.data and "refresh" in response.data
    user = User.objects.get(email="new@example.com")
    assert user.memberships.filter(role="owner").count() == 1
    assert response.data["user"]["memberships"][0]["company"]["name"] == "Ava Athletics"
    assert len(mail.outbox) >= 1 and "Verify" in mail.outbox[0].alternatives[0][0] or "verify" in mail.outbox[0].body.lower()


def test_login_wrong_password_is_friendly(api, buyer):
    response = api.post("/api/v1/auth/login/", {"email": buyer.email, "password": "nope"}, format="json")
    assert response.status_code == 401
    assert response.data["detail"] == "Incorrect email or password."


def test_refresh_rotates_and_blacklists_old_token(auth):
    old_refresh = auth.tokens["refresh"]
    first = auth.post("/api/v1/auth/refresh/", {"refresh": old_refresh}, format="json")
    assert first.status_code == 200 and first.data["refresh"] != old_refresh
    second = auth.post("/api/v1/auth/refresh/", {"refresh": old_refresh}, format="json")
    assert second.status_code == 401


def test_logout_blacklists_refresh(auth):
    response = auth.post("/api/v1/auth/logout/", {"refresh": auth.tokens["refresh"]}, format="json")
    assert response.status_code == 204
    assert auth.post("/api/v1/auth/refresh/", {"refresh": auth.tokens["refresh"]}, format="json").status_code == 401


def test_email_verification_token_roundtrip(api, db):
    user = User.objects.create_user(email="v@example.com", password="Sup3rSecurePass!")
    token = tokens.make_token(user, tokens.VERIFY_SALT)
    response = api.post("/api/v1/auth/verify-email/", {"token": token}, format="json")
    assert response.status_code == 200
    user.refresh_from_db()
    assert user.is_email_verified


def test_password_reset_flow(api, db):
    user = User.objects.create_user(email="r@example.com", password="Sup3rSecurePass!")
    api.post("/api/v1/auth/password/reset/", {"email": user.email}, format="json")
    token = tokens.make_token(user, tokens.RESET_SALT)
    response = api.post("/api/v1/auth/password/reset/confirm/", {"token": token, "password": "An0therSecurePass!"}, format="json")
    assert response.status_code == 200
    assert (
        api.post("/api/v1/auth/login/", {"email": user.email, "password": "An0therSecurePass!"}, format="json").status_code == 200
    )
    # Old token is dead once the password changed.
    assert (
        api.post(
            "/api/v1/auth/password/reset/confirm/", {"token": token, "password": "Yet4notherPass!!"}, format="json"
        ).status_code
        == 400
    )


def test_me_requires_auth(api):
    assert api.get("/api/v1/accounts/me/").status_code == 401


def test_jwt_contains_company_claims(auth):
    import jwt as pyjwt

    payload = pyjwt.decode(auth.tokens["access"], options={"verify_signature": False})
    assert payload["role"] == "owner" and payload["company_id"]
