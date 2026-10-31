import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import BusinessError
from apps.core.utils import unique_slug

from . import tokens
from .models import Company, CompanyInvitation, CompanyMember, User


@transaction.atomic
def register_user(*, email, password, first_name="", last_name="", phone="", company_name=None, business_type=None, country="US"):
    user = User.objects.create_user(email=email, password=password, first_name=first_name, last_name=last_name, phone=phone)
    if company_name:
        create_company(user=user, name=company_name, business_type=business_type or Company.BusinessType.CLUB, country=country)
    send_verification_email(user)
    return user


def create_company(*, user, name, business_type, country="US", **extra) -> Company:
    company = Company.objects.create(
        name=name, slug=unique_slug(Company, name), business_type=business_type, country=country, **extra
    )
    CompanyMember.objects.create(
        company=company,
        user=user,
        role=CompanyMember.Role.OWNER,
        is_default=not CompanyMember.objects.filter(user=user, is_default=True).exists(),
    )
    return company


def send_verification_email(user: User):
    from apps.notifications.tasks import send_email_task

    token = tokens.make_token(user, tokens.VERIFY_SALT)
    send_email_task.delay(
        template="verify_email",
        to=[user.email],
        context={"name": user.full_name, "url": f"{settings.FRONTEND_URL}/verify-email?token={token}"},
    )


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
        return  # Do not reveal whether the account exists.
    token = tokens.make_token(user, tokens.RESET_SALT)
    send_email_task.delay(
        template="password_reset",
        to=[user.email],
        context={"name": user.full_name, "url": f"{settings.FRONTEND_URL}/reset-password?token={token}"},
    )


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


def google_login(id_token: str) -> User:
    """Verify a Google ID token and return (or create) the matching user."""
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


@transaction.atomic
def invite_member(*, company: Company, inviter: User, email: str, role: str) -> CompanyInvitation:
    from apps.notifications.tasks import send_email_task

    email = email.lower()
    if CompanyMember.objects.filter(company=company, user__email=email).exists():
        raise BusinessError("This person is already a member of your company.")
    CompanyInvitation.objects.filter(company=company, email=email, status=CompanyInvitation.Status.PENDING).update(
        status=CompanyInvitation.Status.REVOKED
    )
    invitation = CompanyInvitation.objects.create(
        company=company,
        email=email,
        role=role,
        invited_by=inviter,
        token=secrets.token_urlsafe(32),
        expires_at=timezone.now() + timedelta(days=7),
    )
    send_email_task.delay(
        template="company_invitation",
        to=[email],
        context={
            "company": company.name,
            "inviter": inviter.full_name,
            "role": invitation.get_role_display(),
            "url": f"{settings.FRONTEND_URL}/invitations/{invitation.token}",
        },
    )
    return invitation


@transaction.atomic
def accept_invitation(*, token: str, user: User) -> CompanyMember:
    invitation = CompanyInvitation.objects.select_for_update().select_related("company").filter(token=token).first()
    if not invitation or not invitation.is_valid:
        raise BusinessError("This invitation is invalid or has expired.")
    if invitation.email.lower() != user.email.lower():
        raise BusinessError("This invitation was sent to a different email address.")
    membership, _ = CompanyMember.objects.get_or_create(company=invitation.company, user=user, defaults={"role": invitation.role})
    invitation.status = CompanyInvitation.Status.ACCEPTED
    invitation.accepted_at = timezone.now()
    invitation.save(update_fields=["status", "accepted_at"])
    return membership


@transaction.atomic
def set_default_company(user: User, company: Company) -> CompanyMember:
    membership = CompanyMember.objects.filter(user=user, company=company, is_active=True).first()
    if not membership:
        raise BusinessError("You are not a member of that company.")
    CompanyMember.objects.filter(user=user, is_default=True).update(is_default=False)
    membership.is_default = True
    membership.save(update_fields=["is_default"])
    return membership
