"""Stateless signed tokens for email verification & password reset.

Using Django's signer means no extra table and tokens expire on their own.
"""

from django.core import signing

VERIFY_SALT = "accounts.verify-email"
RESET_SALT = "accounts.reset-password"
VERIFY_MAX_AGE = 60 * 60 * 48
RESET_MAX_AGE = 60 * 60 * 2


def make_token(user, salt: str) -> str:
    # Include password hash fragment so a token dies once the password changes.
    return signing.dumps({"u": str(user.uid), "p": (user.password or "")[-12:]}, salt=salt)


def read_token(token: str, salt: str, max_age: int):
    try:
        return signing.loads(token, salt=salt, max_age=max_age)
    except signing.BadSignature:
        return None
