from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.accounts.models import User
from apps.core.exceptions import BusinessError
from apps.core.utils import after_commit
from apps.notifications.events import emit

from .models import Conversation, Message, Participant


def serialize_message(message: Message) -> dict:
    sender = message.sender
    return {
        "id": str(message.uid),
        "conversation": str(message.conversation.uid) if hasattr(message, "conversation") else None,
        "kind": message.kind,
        "body": message.body,
        "attachment": message.attachment.url if message.attachment else None,
        "attachment_name": message.attachment_name,
        "client_id": message.client_id,
        "sender": {"id": str(sender.uid), "name": sender.full_name, "is_staff": sender.is_staff, "avatar_url": sender.avatar_url}
        if sender
        else None,
        "created_at": message.created_at.isoformat(),
    }


def broadcast(conversation: Conversation, event: dict):
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer is not None:
            async_to_sync(layer.group_send)(f"chat_{conversation.uid}", {"type": "chat.event", "payload": event})
    except Exception:  # pragma: no cover
        pass


@transaction.atomic
def start_conversation(*, user, company, subject: str, body: str, order=None, quote=None) -> Conversation:
    subject = (subject or "").strip()[:160] or "New conversation"
    if not body.strip():
        raise BusinessError("Write a message to start the conversation.")
    conversation = Conversation.objects.create(company=company, created_by=user, subject=subject, order=order, quote=quote)
    participants = [Participant(conversation=conversation, user=user, last_read_at=timezone.now())]
    for staff in User.objects.filter(is_staff=True, is_active=True)[:10]:
        if staff.pk != user.pk:
            participants.append(Participant(conversation=conversation, user=staff))
    Participant.objects.bulk_create(participants, ignore_conflicts=True)
    post_message(conversation, sender=user, body=body)
    return conversation


@transaction.atomic
def post_message(
    conversation: Conversation, *, sender, body: str = "", attachment=None, client_id: str = "", kind=Message.Kind.TEXT
) -> Message:
    if conversation.status == Conversation.Status.CLOSED and not (sender and sender.is_staff):
        raise BusinessError("This conversation is closed. Start a new one if you need more help.")
    body = (body or "").strip()
    if not body and not attachment:
        raise BusinessError("Message cannot be empty.")
    if attachment is not None:
        kind = Message.Kind.FILE
    message = Message.objects.create(
        conversation=conversation,
        sender=sender,
        kind=kind,
        body=body[:4000],
        attachment=attachment,
        attachment_name=getattr(attachment, "name", "")[:160] if attachment else "",
        client_id=client_id[:64],
    )
    Conversation.objects.filter(pk=conversation.pk).update(
        last_message_at=message.created_at,
        last_message_preview=(body or message.attachment_name)[:160],
        message_count=F("message_count") + 1,
        status=Conversation.Status.PENDING if (sender and sender.is_staff) else Conversation.Status.OPEN,
    )
    Participant.objects.get_or_create(conversation=conversation, user=sender) if sender else None
    if sender:
        Participant.objects.filter(conversation=conversation, user=sender).update(last_read_at=message.created_at)
    payload = {"event": "message", "message": serialize_message(message)}
    after_commit(lambda: broadcast(conversation, payload))
    after_commit(lambda: emit("chat.message", message_id=message.pk))
    return message


def mark_read(conversation: Conversation, user):
    now = timezone.now()
    Participant.objects.update_or_create(conversation=conversation, user=user, defaults={"last_read_at": now})
    broadcast(conversation, {"event": "read", "user_id": str(user.uid), "at": now.isoformat()})


def can_access(user, conversation: Conversation) -> bool:
    if user.is_staff:
        return True
    if conversation.company_id is None:
        return conversation.created_by_id == user.pk
    return user.memberships.filter(company_id=conversation.company_id, is_active=True).exists()
