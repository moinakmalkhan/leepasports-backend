import pytest

from apps.accounts.models import CompanyInvitation, User
from apps.chat.models import Conversation
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db


def test_conversation_rest_flow(auth, buyer, staff):
    r = auth.post("/api/v1/chat/conversations/", {"subject": "Sizing help", "body": "Do you have a size chart?"}, format="json")
    assert r.status_code == 201 and r.data["message_count"] == 1
    cid = r.data["id"]
    msgs = auth.get(f"/api/v1/chat/conversations/{cid}/messages/")
    assert msgs.status_code == 200 and len(msgs.data["results"]) == 1 and "next" in msgs.data
    auth.force_authenticate(staff)
    reply = auth.post(f"/api/v1/chat/conversations/{cid}/messages/", {"body": "Yes — attached."}, format="json")
    assert reply.status_code == 201
    assert Notification.objects.filter(user=buyer, kind="chat").exists()
    auth.force_authenticate(buyer)
    unread = auth.get("/api/v1/chat/conversations/unread-count/")
    assert unread.data["count"] == 1
    auth.post(f"/api/v1/chat/conversations/{cid}/read/")
    assert auth.get("/api/v1/chat/conversations/unread-count/").data["count"] == 0
    assert auth.post(f"/api/v1/chat/conversations/{cid}/close/").data["status"] == "closed"
    assert Conversation.objects.get(uid=cid).message_count == 3


def test_other_company_cannot_see_conversation(auth, buyer, db):
    r = auth.post("/api/v1/chat/conversations/", {"body": "hello"}, format="json")
    other = User.objects.create_user(email="other@example.com", password="Str0ngPassw0rd!")
    auth.force_authenticate(other)
    assert auth.get(f"/api/v1/chat/conversations/{r.data['id']}/").status_code == 404


@pytest.mark.asyncio
async def test_websocket_requires_token():
    from channels.testing import WebsocketCommunicator

    from config.asgi import application

    communicator = WebsocketCommunicator(
        application, "/ws/notifications/", headers=[(b"origin", b"http://localhost"), (b"host", b"localhost")]
    )
    connected, code = await communicator.connect()
    assert not connected and code == 4401


def test_invite_and_accept_member(auth, buyer, api):
    r = auth.post("/api/v1/accounts/company/members/invite/", {"email": "mate@example.com", "role": "buyer"}, format="json")
    assert r.status_code == 201
    invitation = CompanyInvitation.objects.get(email="mate@example.com")
    mate = User.objects.create_user(email="mate@example.com", password="Str0ngPassw0rd!")
    api.force_authenticate(mate)
    assert api.get(f"/api/v1/accounts/invitations/{invitation.token}/").status_code == 200
    accept = api.post(f"/api/v1/accounts/invitations/{invitation.token}/")
    assert accept.status_code == 200 and accept.data["user"]["memberships"][0]["role"] == "buyer"
    members = auth.get("/api/v1/accounts/company/members/")
    assert members.data["count"] == 2


def test_viewer_cannot_order(auth, buyer, product, api):
    from apps.accounts.models import CompanyMember

    viewer = User.objects.create_user(email="viewer@example.com", password="Str0ngPassw0rd!", is_email_verified=True)
    CompanyMember.objects.create(company=buyer.memberships.first().company, user=viewer, role=CompanyMember.Role.VIEWER)
    api.force_authenticate(viewer)
    r = api.post(
        "/api/v1/orders/checkout/",
        {"shipping_address": "00000000-0000-0000-0000-000000000000", "shipping_method": "air", "payment_method": "bank_transfer"},
        format="json",
    )
    assert r.status_code == 403


def test_notifications_cursor_pagination(auth, buyer):
    for i in range(35):
        Notification.objects.create(user=buyer, title=f"n{i}")
    first = auth.get("/api/v1/notifications/")
    assert len(first.data["results"]) == 30 and first.data["next"]
    assert auth.get("/api/v1/notifications/unread-count/").data["count"] == 35
    auth.post("/api/v1/notifications/read-all/")
    assert auth.get("/api/v1/notifications/unread-count/").data["count"] == 0
