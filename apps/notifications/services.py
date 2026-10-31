from django.conf import settings
from django.core.cache import cache

from apps.accounts.models import CompanyMember, User

from .models import Notification


def unread_cache_key(user_id: int) -> str:
    return f"notif:unread:{user_id}"


def push_realtime(user_id: int, payload: dict):
    """Fan a payload out to the user's websocket group (no-op if layer down)."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(f"user_{user_id}", {"type": "notify", "payload": payload})
    except Exception:  # pragma: no cover
        pass


def notify_users(users, *, kind, title, body="", url="", level=Notification.Level.INFO, company=None, data=None):
    users = [u for u in users if u is not None]
    if not users:
        return []
    rows = Notification.objects.bulk_create(
        [
            Notification(user=u, company=company, kind=kind, level=level, title=title, body=body, url=url, data=data or {})
            for u in users
        ]
    )
    for row in rows:
        cache.delete(unread_cache_key(row.user_id))
        push_realtime(
            row.user_id,
            {
                "event": "notification",
                "id": str(row.uid),
                "kind": kind,
                "level": level,
                "title": title,
                "body": body,
                "url": url,
                "created_at": row.created_at.isoformat(),
            },
        )
    return rows


def company_recipients(company, roles=None):
    qs = CompanyMember.objects.filter(company=company, is_active=True, user__is_active=True).select_related("user")
    if roles:
        qs = qs.filter(role__in=roles)
    return [m.user for m in qs]


def notify_company(company, *, roles=None, **kwargs):
    return notify_users(company_recipients(company, roles), company=company, **kwargs)


def staff_users():
    return list(User.objects.filter(is_staff=True, is_active=True))


def notify_staff(*, event: str, subject: str, context: dict, url: str = "/admin/"):
    from .tasks import send_email_task

    users = staff_users()
    notify_users(
        users,
        kind=Notification.Kind.SYSTEM,
        title=subject,
        body=context.get("summary", ""),
        url=url,
        data={"event": event, **{k: str(v) for k, v in context.items()}},
    )
    emails = settings.ADMIN_NOTIFICATION_EMAILS or [u.email for u in users]
    if emails:
        send_email_task.delay(
            template="staff_alert",
            to=emails,
            context={
                "event": event,
                "subject": subject,
                "items": {k: str(v) for k, v in context.items()},
                "url": f"{settings.FRONTEND_URL}{url}",
            },
            subject=f"[{settings.SITE_NAME}] {subject}",
        )


def unread_count(user) -> int:
    key = unread_cache_key(user.pk)
    count = cache.get(key)
    if count is None:
        count = Notification.objects.filter(user=user, is_read=False).count()
        cache.set(key, count, 120)
    return count
