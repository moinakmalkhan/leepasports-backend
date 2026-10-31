from decimal import Decimal

import pytest
from django.core import mail

from apps.accounts.models import Company, CompanyMember, User
from apps.notifications.models import Notification
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.quotes.models import Quote
from tests.conftest import shipping_address_uid, size_breakdown

pytestmark = pytest.mark.django_db


def test_cart_add_update_remove(auth, product, cart_with_item):
    assert cart_with_item["item_count"] == 1 and cart_with_item["quantity"] == 15
    item = cart_with_item["items"][0]
    update = auth.patch(f"/api/v1/cart/items/{item['id']}/", {"fabric": "dot-knit-performance"}, format="json")
    assert update.status_code == 200 and Decimal(str(update.data["unit_price"])) > Decimal(str(item["unit_price"]))
    assert auth.delete(f"/api/v1/cart/items/{item['id']}/").status_code == 204
    assert auth.get("/api/v1/cart/").data["item_count"] == 0


def test_guest_cart_merges_on_login(api, buyer, product):
    guest = api.post("/api/v1/cart/", {"product": product.slug, "breakdown": size_breakdown(product)}, format="json")
    token = guest.data["guest_token"]
    assert token
    login = api.post("/api/v1/auth/login/", {"email": buyer.email, "password": "Str0ngPassw0rd!"}, format="json")
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}", HTTP_X_CART_TOKEN=token)
    cart = api.get("/api/v1/cart/")
    assert cart.data["item_count"] == 1 and cart.data["guest_token"] is None


def test_checkout_bank_transfer_full_flow(auth, buyer, product, cart_with_item, staff):
    mail.outbox.clear()
    response = auth.post(
        "/api/v1/orders/checkout/",
        {
            "shipping_address": shipping_address_uid(buyer),
            "shipping_method": "air",
            "payment_method": "bank_transfer",
            "po_number": "PO-778",
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    order = Order.objects.get(number=response.data["number"])
    assert order.status == Order.Status.PENDING_PAYMENT and order.po_number == "PO-778"
    assert order.shipping_total > 0 and order.grand_total == order.subtotal + order.shipping_total
    assert order.items.count() == 1 and order.items.first().breakdown[0]["quantity"] == 5
    assert auth.get("/api/v1/cart/").data["item_count"] == 0
    assert Payment.objects.filter(order=order, status=Payment.Status.PENDING).exists()
    assert any("Order" in m.subject for m in mail.outbox)
    assert Notification.objects.filter(user=buyer, kind="order").exists()
    assert Notification.objects.filter(user=staff).exists()

    # Buyer submits bank transfer proof, staff confirms → order confirmed.
    payment = Payment.objects.get(order=order)
    proof = auth.post(f"/api/v1/payments/{payment.uid}/submit-proof/", {"reference": "TRX-1"}, format="json")
    assert proof.status_code == 200 and proof.data["status"] == "submitted"
    auth.force_authenticate(staff)
    confirm = auth.post(f"/api/v1/payments/staff/{payment.uid}/confirm/", {}, format="json")
    assert confirm.status_code == 200
    order.refresh_from_db()
    assert order.status == Order.Status.CONFIRMED and order.payment_status == Order.PaymentStatus.PAID

    # Staff moves through production and ships with tracking.
    for status in ("in_production", "quality_check", "shipped"):
        r = auth.post(
            f"/api/v1/orders/staff/{order.uid}/transition/",
            {"status": status, "carrier": "DHL", "tracking_number": "123"},
            format="json",
        )
        assert r.status_code == 200, r.content
    order.refresh_from_db()
    assert order.status == Order.Status.SHIPPED and order.tracking_number == "123" and order.history.count() >= 5

    # Public tracking without auth.
    auth.force_authenticate(None)
    auth.credentials()
    track = auth.get(f"/api/v1/orders/track/?number={order.number}&email={buyer.email}")
    assert track.status_code == 200 and track.data["status"] == "shipped" and track.data["tracking_number"] == "123"
    assert auth.get(f"/api/v1/orders/track/?number={order.number}&email=wrong@x.com").status_code == 404


def test_checkout_requires_verified_email_and_role(auth, buyer, product, cart_with_item):
    buyer.is_email_verified = False
    buyer.save()
    r = auth.post(
        "/api/v1/orders/checkout/",
        {"shipping_address": shipping_address_uid(buyer), "shipping_method": "air", "payment_method": "bank_transfer"},
        format="json",
    )
    assert r.status_code == 400 and "verify" in r.data["detail"].lower()


def test_net_terms_requires_verified_company_and_credit(auth, buyer, product, cart_with_item):
    r = auth.post(
        "/api/v1/orders/checkout/",
        {"shipping_address": shipping_address_uid(buyer), "shipping_method": "air", "payment_method": "net_terms"},
        format="json",
    )
    assert r.status_code == 400 and "Net terms" in r.data["detail"]
    company = buyer.memberships.first().company
    company.is_verified = True
    company.payment_terms = Company.PaymentTerms.NET_30
    company.credit_limit = Decimal("100000")
    company.save()
    r = auth.post(
        "/api/v1/orders/checkout/",
        {"shipping_address": shipping_address_uid(buyer), "shipping_method": "sea", "payment_method": "net_terms"},
        format="json",
    )
    assert r.status_code == 201 and r.data["status"] == "confirmed" and r.data["due_date"]
    company.refresh_from_db()
    assert company.credit_used == Decimal(str(r.data["grand_total"]))
    # Cancelling releases credit.
    cancel = auth.post(f"/api/v1/orders/{r.data['id']}/cancel/", {"reason": "Changed plans"}, format="json")
    assert cancel.status_code == 200 and cancel.data["status"] == "cancelled"
    company.refresh_from_db()
    assert company.credit_used == 0


def test_approval_threshold_routes_buyer_orders(api, buyer, product):
    company = buyer.memberships.first().company
    company.approval_threshold = Decimal("10")
    company.save()
    junior = User.objects.create_user(email="junior@example.com", password="Str0ngPassw0rd!", is_email_verified=True)
    CompanyMember.objects.create(company=company, user=junior, role=CompanyMember.Role.BUYER)
    api.force_authenticate(junior)
    api.post("/api/v1/cart/", {"product": product.slug, "breakdown": size_breakdown(product)}, format="json")
    r = api.post(
        "/api/v1/orders/checkout/",
        {"shipping_address": shipping_address_uid(buyer), "shipping_method": "air", "payment_method": "bank_transfer"},
        format="json",
    )
    assert r.status_code == 201 and r.data["status"] == "pending_approval"
    assert Notification.objects.filter(user=buyer, title__startswith="Approval needed").exists()
    # Junior cannot approve; owner can.
    assert api.post(f"/api/v1/orders/{r.data['id']}/approve/").status_code == 403
    api.force_authenticate(buyer)
    approve = api.post(f"/api/v1/orders/{r.data['id']}/approve/")
    assert approve.status_code == 200 and approve.data["status"] == "pending_payment"


def test_reorder_and_saved_lists(auth, buyer, product, cart_with_item):
    saved = auth.post("/api/v1/cart/saved-lists/from-cart/", {"name": "Season kit"}, format="json")
    assert saved.status_code == 201 and saved.data["item_count"] == 1
    order = auth.post(
        "/api/v1/orders/checkout/",
        {"shipping_address": shipping_address_uid(buyer), "shipping_method": "air", "payment_method": "bank_transfer"},
        format="json",
    )
    assert auth.get("/api/v1/cart/").data["item_count"] == 0
    reorder = auth.post(f"/api/v1/orders/{order.data['id']}/reorder/")
    assert reorder.status_code == 200 and reorder.data["added"] == 1
    auth.delete("/api/v1/cart/")
    again = auth.post(f"/api/v1/cart/saved-lists/{saved.data['id']}/add-to-cart/")
    assert again.data["added"] == 1
    lists = auth.get("/api/v1/cart/saved-lists/")
    assert lists.data["count"] == 1


def test_quick_order_by_sku(auth):
    r = auth.post(
        "/api/v1/cart/quick-order/",
        {
            "lines": [
                {"sku": "ls-trn-001", "gender": "men", "size": "L", "quantity": 10},
                {"sku": "LS-TRN-001", "gender": "women", "size": "M", "quantity": 10},
                {"sku": "NOPE", "gender": "men", "size": "L", "quantity": 1},
            ]
        },
        format="json",
    )
    assert r.status_code == 201 and r.data["added"] == 1 and r.data["errors"][0]["sku"] == "NOPE"
    assert r.data["cart"]["quantity"] == 20


def test_quote_request_respond_accept(auth, buyer, product, cart_with_item, staff):
    r = auth.post(
        "/api/v1/quotes/", {"customer_notes": "Need by August", "shipping_address": shipping_address_uid(buyer)}, format="json"
    )
    assert r.status_code == 201 and r.data["status"] == "submitted"
    quote = Quote.objects.get(uid=r.data["id"])
    item = quote.items.first()
    auth.force_authenticate(staff)
    resp = auth.post(
        f"/api/v1/quotes/staff/{quote.uid}/respond/",
        {"item_prices": {str(item.uid): "5.00"}, "message": "Best price for 15 pcs", "valid_days": 10},
        format="json",
    )
    assert (
        resp.status_code == 200
        and resp.data["status"] == "quoted"
        and Decimal(str(resp.data["quoted_total"])) == Decimal("75.00")
    )
    auth.force_authenticate(buyer)
    accept = auth.post(
        f"/api/v1/quotes/{quote.uid}/accept/",
        {"shipping_address": shipping_address_uid(buyer), "payment_method": "bank_transfer"},
        format="json",
    )
    assert accept.status_code == 201 and Decimal(str(accept.data["grand_total"])) == Decimal("75.00")
    quote.refresh_from_db()
    assert quote.status == Quote.Status.CONVERTED
    assert auth.get("/api/v1/orders/summary/").data["total"] == 1


def test_order_list_pagination_and_filters(auth, buyer, product):
    for _ in range(3):
        auth.post("/api/v1/cart/", {"product": product.slug, "breakdown": size_breakdown(product)}, format="json")
        auth.post(
            "/api/v1/orders/checkout/",
            {"shipping_address": shipping_address_uid(buyer), "shipping_method": "air", "payment_method": "bank_transfer"},
            format="json",
        )
    page = auth.get("/api/v1/orders/?page_size=2")
    assert page.data["count"] == 3 and len(page.data["results"]) == 2 and page.data["total_pages"] == 2
    assert auth.get("/api/v1/orders/?status=pending_payment").data["count"] == 3
    assert auth.get("/api/v1/orders/?status=shipped").data["count"] == 0


def test_invoice_endpoint(auth, buyer, product, cart_with_item):
    order = auth.post(
        "/api/v1/orders/checkout/",
        {"shipping_address": shipping_address_uid(buyer), "shipping_method": "air", "payment_method": "bank_transfer"},
        format="json",
    )
    inv = auth.get(f"/api/v1/orders/{order.data['id']}/invoice/")
    assert inv.status_code == 200 and inv.data["document_type"] == "Pro-forma invoice" and "seller" in inv.data
