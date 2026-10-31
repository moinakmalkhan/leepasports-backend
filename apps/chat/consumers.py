import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .models import Conversation
from .services import can_access, mark_read, post_message, serialize_message


class ChatConsumer(AsyncJsonWebsocketConsumer):
    """ws://…/ws/chat/<conversation_uid>/?token=<access>

    Client → server: {"type": "message", "body": "...", "client_id": "..."}
                     {"type": "typing", "is_typing": true}
                     {"type": "read"}
    Server → client: {"event": "message", "message": {...}}
                     {"event": "typing", "user": {...}, "is_typing": true}
                     {"event": "read", "user_id": "...", "at": "..."}
    """

    async def connect(self):
        user = self.scope["user"]
        if not user.is_authenticated:
            await self.close(code=4401)
            return
        self.conversation = await self._get_conversation(self.scope["url_route"]["kwargs"]["uid"], user)
        if self.conversation is None:
            await self.close(code=4403)
            return
        self.group = f"chat_{self.conversation.uid}"
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        await self.send_json({"event": "connected", "conversation": str(self.conversation.uid)})

    async def disconnect(self, code):
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        user = self.scope["user"]
        kind = content.get("type")
        if kind == "message":
            body = str(content.get("body", ""))[:4000]
            if not body.strip():
                return
            try:
                message = await database_sync_to_async(post_message)(
                    self.conversation, sender=user, body=body, client_id=str(content.get("client_id", ""))[:64]
                )
            except Exception as exc:  # BusinessError → tell only this client
                await self.send_json({"event": "error", "detail": str(getattr(exc, "detail", exc))})
                return
            # post_message broadcasts on commit; echo immediately for snappy UI.
            await self.send_json({"event": "ack", "client_id": content.get("client_id"), "message": serialize_message(message)})
        elif kind == "typing":
            await self.channel_layer.group_send(
                self.group,
                {
                    "type": "chat.event",
                    "payload": {
                        "event": "typing",
                        "user": {"id": str(user.uid), "name": user.full_name, "is_staff": user.is_staff},
                        "is_typing": bool(content.get("is_typing")),
                    },
                },
            )
        elif kind == "read":
            await database_sync_to_async(mark_read)(self.conversation, user)

    async def chat_event(self, event):
        await self.send_json(event["payload"])

    @database_sync_to_async
    def _get_conversation(self, uid, user):
        conversation = Conversation.objects.filter(uid=uid).first()
        if conversation and can_access(user, conversation):
            return conversation
        return None


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    """ws://…/ws/notifications/?token=<access> — realtime in-app notifications."""

    async def connect(self):
        user = self.scope["user"]
        if not user.is_authenticated:
            await self.close(code=4401)
            return
        self.group = f"user_{user.pk}"
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if text_data == "ping":
            await self.send(text_data="pong")

    async def notify(self, event):
        await self.send(text_data=json.dumps(event["payload"], default=str))
