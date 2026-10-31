from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import BusinessError

from . import tokens
from .models import Address, NewsletterSubscriber, User


@transaction.atomic
def register_user(*, email, password, first_name="", last_name="", phone="", marketing_opt_in=True):
    user = User.objects.create_user(
        email=email, password=password, first_name=first_name, last_name=last_name, phone=phone, marketing_opt_in=marketing_opt_in
    )
    if marketing_opt_in:
        subscribe_newsletter(email, user=user, source="signup")
    send_verification_email(user)
    return user


def send_verification_email(user: User):
    from apps.notifications.tasks import send_email_task

    token = tokens.make_token(user, tokens.VERIFY_SALT)
    send_email_task.delay(
        template="verify_email",
        to=[user.email],
        context={"name": user.full_name, "url": f"{settings.FRONTEND_URL}/verify-email?token={token}"},
    )


@transaction.atomic
def verify_email(token: str) -> User:
    data = tokens.read_token(token, tokens.VERIFY_SALT, tokens.VERIFY_MAX_AGE)
    if not data:
        raise BusinessError("This verification link is invalid or has expired.")
    user = User.objects.filter(uid=data["u"]).first()
    if not user:
        raise BusinessError("Account not found.")
    if not user.is_email_verified:
        user.is_email_verified = True
        user.save(update_fields=["is_email_verified"])
    return user


def request_password_reset(email: str):
    from apps.notifications.tasks import send_email_task

    user = User.objects.filter(email__iexact=email, is_active=True).first()
    if not user:
        return
    token = tokens.make_token(user, tokens.RESET_SALT)
    send_email_task.delay(
        template="password_reset",
        to=[user.email],
        context={"name": user.full_name, "url": f"{settings.FRONTEND_URL}/reset-password?token={token}"},
    )


@transaction.atomic
def reset_password(token: str, new_password: str) -> User:
    data = tokens.read_token(token, tokens.RESET_SALT, tokens.RESET_MAX_AGE)
    if not data:
        raise BusinessError("This reset link is invalid or has expired.")
    user = User.objects.filter(uid=data["u"]).first()
    if not user or (user.password or "")[-12:] != data["p"]:
        raise BusinessError("This reset link is no longer valid.")
    user.set_password(new_password)
    user.is_email_verified = True
    user.save(update_fields=["password", "is_email_verified"])
    return user


@transaction.atomic
def google_login(id_token: str) -> User:
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token

    if not settings.GOOGLE_OAUTH_CLIENT_ID:
        raise BusinessError("Google sign-in is not configured.")
    try:
        info = google_id_token.verify_oauth2_token(id_token, google_requests.Request(), settings.GOOGLE_OAUTH_CLIENT_ID)
    except ValueError as exc:
        raise BusinessError("Google sign-in failed. Please try again.") from exc
    if info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise BusinessError("Google sign-in failed.")
    if not info.get("email_verified"):
        raise BusinessError("Your Google account email is not verified.")

    email = info["email"].lower()
    sub = info["sub"]
    user = User.objects.filter(google_sub=sub).first() or User.objects.filter(email=email).first()
    if user is None:
        user = User.objects.create_user(
            email=email,
            password=None,
            first_name=info.get("given_name", ""),
            last_name=info.get("family_name", ""),
            avatar_url=info.get("picture", ""),
            auth_provider=User.AuthProvider.GOOGLE,
            google_sub=sub,
            is_email_verified=True,
        )
    else:
        updates = []
        if not user.google_sub:
            user.google_sub = sub
            updates.append("google_sub")
        if not user.is_email_verified:
            user.is_email_verified = True
            updates.append("is_email_verified")
        if not user.avatar_url and info.get("picture"):
            user.avatar_url = info["picture"]
            updates.append("avatar_url")
        if updates:
            user.save(update_fields=updates)
    if not user.is_active:
        raise BusinessError("This account has been deactivated.")
    return user


def subscribe_newsletter(email: str, user=None, source: str = "footer") -> NewsletterSubscriber:
    sub, created = NewsletterSubscriber.objects.get_or_create(email=email.lower(), defaults={"user": user, "source": source})
    if not created and not sub.is_active:
        sub.is_active = True
        sub.unsubscribed_at = None
        sub.save(update_fields=["is_active", "unsubscribed_at"])
    return sub


def unsubscribe_newsletter(email: str):
    NewsletterSubscriber.objects.filter(email=email.lower(), is_active=True).update(
        is_active=False, unsubscribed_at=timezone.now()
    )


@transaction.atomic
def save_address(user: User, data: dict, instance: Address | None = None) -> Address:
    if data.get("is_default") or not Address.objects.filter(user=user).exclude(pk=getattr(instance, "pk", None)).exists():
        Address.objects.filter(user=user, is_default=True).exclude(pk=getattr(instance, "pk", None)).update(is_default=False)
        data["is_default"] = True
    if instance:
        for key, value in data.items():
            setattr(instance, key, value)
        instance.save()
        return instance
    return Address.objects.create(user=user, **data)
