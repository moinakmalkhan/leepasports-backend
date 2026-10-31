import pytest

from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db


def test_support_conversation_flow(auth, customer, staff):
    r = auth.post(
        "/api/v1/chat/conversations/", {"subject": "Sizing", "body": "Does the tee run big?", "topic": "sizing"}, format="json"
    )
    assert r.status_code == 201 and r.data["message_count"] == 1
    cid = r.data["id"]
    assert len(auth.get(f"/api/v1/chat/conversations/{cid}/messages/").data["results"]) == 1
    auth.force_authenticate(staff)
    assert (
        auth.post(f"/api/v1/chat/conversations/{cid}/messages/", {"body": "Slightly — size down."}, format="json").status_code
        == 201
    )
    assert Notification.objects.filter(user=customer, kind="chat").exists()
    auth.force_authenticate(customer)
    assert auth.get("/api/v1/chat/conversations/unread-count/").data["count"] == 1
    assert auth.post(f"/api/v1/chat/conversations/{cid}/close/").data["status"] == "closed"


def test_other_user_cannot_read_conversation(auth, api, db):
    r = auth.post("/api/v1/chat/conversations/", {"body": "hello"}, format="json")
    from apps.accounts.models import User

    api.force_authenticate(User.objects.create_user(email="x@test.com", password="Str0ngPassw0rd!"))
    assert api.get(f"/api/v1/chat/conversations/{r.data['id']}/").status_code == 404


@pytest.mark.asyncio
async def test_websocket_requires_token():
    from channels.testing import WebsocketCommunicator

    from config.asgi import application

    communicator = WebsocketCommunicator(
        application, "/ws/notifications/", headers=[(b"origin", b"http://localhost"), (b"host", b"localhost")]
    )
    connected, code = await communicator.connect()
    assert not connected and code == 4401


def test_notifications_feed(auth, customer):
    for i in range(35):
        Notification.objects.create(user=customer, title=f"n{i}")
    first = auth.get("/api/v1/notifications/")
    assert len(first.data["results"]) == 30 and first.data["next"]
    auth.post("/api/v1/notifications/read-all/")
    assert auth.get("/api/v1/notifications/unread-count/").data["count"] == 0
