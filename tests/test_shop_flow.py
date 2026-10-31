from decimal import Decimal

import pytest
from django.core import mail

from apps.catalog.models import ProductVariant
from apps.notifications.models import Notification
from apps.orders.models import Order, ReturnRequest
from apps.payments.models import Payment
from apps.promotions.models import Coupon
from apps.reviews.models import Review
from tests.conftest import ADDRESS

pytestmark = pytest.mark.django_db


def add(client, variant, qty=1):
    return client.post("/api/v1/cart/", {"variant": str(variant.uid), "quantity": qty}, format="json")


def test_cart_add_update_remove_and_stock_limit(auth, variant):
    r = add(auth, variant, 2)
    assert r.status_code == 201 and r.data["quantity"] == 2 and Decimal(str(r.data["subtotal"])) == variant.price * 2
    item = r.data["items"][0]
    assert auth.patch(f"/api/v1/cart/items/{item['id']}/", {"quantity": 3}, format="json").data["quantity"] == 3
    too_many = auth.patch(f"/api/v1/cart/items/{item['id']}/", {"quantity": variant.stock + 1}, format="json")
    assert too_many.status_code == 400 and "left" in too_many.data["detail"]
    assert auth.delete(f"/api/v1/cart/items/{item['id']}/").data["item_count"] == 0


def test_guest_cart_merges_on_login(api, customer, variant):
    guest = add(api, variant)
    token = guest.data["guest_token"]
    login = api.post("/api/v1/auth/login/", {"email": customer.email, "password": "Str0ngPassw0rd!"}, format="json")
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}", HTTP_X_CART_TOKEN=token)
    assert api.get("/api/v1/cart/").data["item_count"] == 1


def test_coupon_apply_and_rules(auth, variant):
    add(auth, variant, 2)
    bad = auth.post("/api/v1/cart/coupon/", {"code": "NOPE"}, format="json")
    assert bad.status_code == 400
    ok = auth.post("/api/v1/cart/coupon/", {"code": "welcome10"}, format="json")
    assert (
        ok.status_code == 200
        and ok.data["coupon_code"] == "WELCOME10"
        and Decimal(str(ok.data["discount"])) == (variant.price * 2 * Decimal("0.10")).quantize(Decimal("0.01"))
    )
    free = auth.post("/api/v1/cart/coupon/", {"code": "FREESHIP"}, format="json")
    assert free.data["free_shipping"] is True
    assert auth.delete("/api/v1/cart/coupon/").data["coupon_code"] == ""


def test_shipping_quote_by_city(auth, variant):
    add(auth, variant)
    lahore = auth.post("/api/v1/orders/shipping-quote/", {"city": "Lahore"}, format="json").data
    far = auth.post("/api/v1/orders/shipping-quote/", {"city": "Gilgit", "payment_method": "cod"}, format="json").data
    assert lahore["zone"] == "Lahore & Sialkot" and far["zone"] == "Rest of Pakistan"
    assert Decimal(str(far["cod_fee"])) == Decimal("50") and Decimal(str(far["rate"])) == Decimal("300")


def test_checkout_cod_full_lifecycle(auth, customer, variant, staff):
    before = variant.stock
    add(auth, variant, 2)
    auth.post("/api/v1/cart/coupon/", {"code": "WELCOME10"}, format="json")
    mail.outbox.clear()
    r = auth.post(
        "/api/v1/orders/checkout/",
        {
            "email": customer.email,
            "address": ADDRESS,
            "payment_method": "cod",
            "notes": "Call before delivery",
            "save_address": True,
        },
        format="json",
    )
    assert r.status_code == 201, r.content
    order = Order.objects.get(number=r.data["number"])
    assert order.status == Order.Status.PENDING and order.payment_status == Order.PaymentStatus.COD_PENDING
    assert order.discount_total > 0 and order.coupon_code == "WELCOME10"
    assert order.shipping_total == Decimal("0")  # Lahore zone is free over Rs 3,000
    variant.refresh_from_db()
    assert variant.stock == before - 2
    assert Coupon.objects.get(code="WELCOME10").uses_count == 1
    assert auth.get("/api/v1/cart/").data["item_count"] == 0
    assert any(order.number in m.subject for m in mail.outbox)
    assert Notification.objects.filter(user=customer, kind="order").exists()
    customer.refresh_from_db()
    assert customer.order_count == 1

    # Staff: confirm → pack → ship → deliver (COD becomes paid on delivery)
    auth.force_authenticate(staff)
    for status, extra in (
        ("confirmed", {}),
        ("processing", {}),
        ("shipped", {"carrier": "TCS", "tracking_number": "TCS123"}),
        ("delivered", {}),
    ):
        res = auth.post(f"/api/v1/orders/staff/{order.uid}/transition/", {"status": status, **extra}, format="json")
        assert res.status_code == 200, res.content
    order.refresh_from_db()
    assert (
        order.status == Order.Status.DELIVERED
        and order.payment_status == Order.PaymentStatus.PAID
        and order.tracking_number == "TCS123"
    )

    # Public tracking by phone
    auth.force_authenticate(None)
    auth.credentials()
    track = auth.get(f"/api/v1/orders/track/?number={order.number}&contact=03001234567")
    assert track.status_code == 200 and track.data["status"] == "delivered" and track.data["steps"][-1]["reached"]
    assert auth.get(f"/api/v1/orders/track/?number={order.number}&contact=wrong@x.com").status_code == 404


def test_guest_checkout_bank_transfer_and_proof(api, variant, staff):
    token = add(api, variant).data["guest_token"]
    api.credentials(HTTP_X_CART_TOKEN=token)
    r = api.post(
        "/api/v1/orders/checkout/",
        {"email": "guest@example.com", "address": ADDRESS, "payment_method": "bank_transfer"},
        format="json",
    )
    assert r.status_code == 201, r.content
    assert r.data["payment_status"] == "unpaid"
    order = Order.objects.get(number=r.data["number"])
    assert order.user is None and Payment.objects.filter(order=order, status="pending").exists()
    proof = api.post(
        f"/api/v1/payments/orders/{order.uid}/", {"email": "guest@example.com", "reference": "TRX-9"}, format="multipart"
    )
    assert proof.status_code == 200 and proof.data["status"] == "submitted"
    api.force_authenticate(staff)
    payment = Payment.objects.get(order=order)
    assert api.post(f"/api/v1/payments/staff/{payment.uid}/confirm/", {}, format="json").status_code == 200
    order.refresh_from_db()
    assert order.status == Order.Status.CONFIRMED and order.payment_status == Order.PaymentStatus.PAID


def test_cancel_restocks(auth, customer, variant):
    before = variant.stock
    add(auth, variant, 1)
    r = auth.post(
        "/api/v1/orders/checkout/", {"email": customer.email, "address": ADDRESS, "payment_method": "cod"}, format="json"
    )
    assert r.status_code == 201 and Decimal(str(r.data["shipping_total"])) == Decimal("150")  # below free threshold
    cancel = auth.post(f"/api/v1/orders/{r.data['id']}/cancel/", {"reason": "Changed my mind"}, format="json")
    assert cancel.status_code == 200 and cancel.data["status"] == "cancelled"
    variant.refresh_from_db()
    assert variant.stock == before


def test_sold_out_blocks_checkout(auth, customer, variant):
    add(auth, variant, 1)
    ProductVariant.objects.filter(pk=variant.pk).update(stock=0)
    r = auth.post(
        "/api/v1/orders/checkout/", {"email": customer.email, "address": ADDRESS, "payment_method": "cod"}, format="json"
    )
    assert r.status_code == 400 and "sold out" in r.data["detail"].lower()


def test_return_request_and_resolution(auth, customer, variant, staff):
    add(auth, variant, 2)
    r = auth.post(
        "/api/v1/orders/checkout/", {"email": customer.email, "address": ADDRESS, "payment_method": "cod"}, format="json"
    )
    order = Order.objects.get(uid=r.data["id"])
    from apps.orders import services

    for s in ("confirmed", "processing", "shipped", "delivered"):
        services.transition(order, s, by=staff)
    item = order.items.first()
    before = ProductVariant.objects.get(pk=variant.pk).stock
    req = auth.post(
        f"/api/v1/orders/{order.uid}/returns/",
        {"kind": "refund", "reason": "size", "details": "Too big", "items": [{"order_item": str(item.uid), "quantity": 1}]},
        format="json",
    )
    assert req.status_code == 201 and Decimal(str(req.data["refund_amount"])) == item.unit_price
    rr = ReturnRequest.objects.get(uid=req.data["id"])
    services.resolve_return(rr, status="approved", by=staff)
    services.resolve_return(rr, status="completed", by=staff, refund_method="JazzCash/EasyPaisa")
    order.refresh_from_db()
    assert order.payment_status == Order.PaymentStatus.PARTIALLY_REFUNDED and order.refunded_total == item.unit_price
    assert ProductVariant.objects.get(pk=variant.pk).stock == before + 1
    assert auth.get("/api/v1/orders/returns/").data["count"] == 1


def test_reviews_verified_and_moderated(auth, customer, variant, staff, api):
    add(auth, variant)
    r = auth.post(
        "/api/v1/orders/checkout/", {"email": customer.email, "address": ADDRESS, "payment_method": "cod"}, format="json"
    )
    order = Order.objects.get(uid=r.data["id"])
    from apps.orders import services

    for s in ("confirmed", "processing", "shipped", "delivered"):
        services.transition(order, s, by=staff)
    rev = auth.post(
        "/api/v1/reviews/",
        {"product": variant.product.slug, "rating": 5, "title": "Great fit", "body": "Heavy and soft."},
        format="json",
    )
    assert rev.status_code == 201 and rev.data["is_verified_purchase"] is True and rev.data["status"] == "approved"
    variant.product.refresh_from_db()
    assert float(variant.product.rating_avg) == 5.0 and variant.product.rating_count == 1
    assert auth.post("/api/v1/reviews/", {"product": variant.product.slug, "rating": 4}, format="json").status_code == 400
    other = api
    other.credentials()
    from apps.accounts.models import User

    u2 = User.objects.create_user(email="u2@test.com", password="Str0ngPassw0rd!")
    other.force_authenticate(u2)
    pend = other.post("/api/v1/reviews/", {"product": variant.product.slug, "rating": 2}, format="json")
    assert pend.data["status"] == "pending"
    assert Review.objects.filter(status="pending").count() == 1
    assert other.get(f"/api/v1/reviews/?product={variant.product.slug}").data["count"] == 1
    assert other.get(f"/api/v1/reviews/summary/?product={variant.product.slug}").data["total"] == 1


def test_wishlist_toggle(auth, product):
    assert auth.post("/api/v1/cart/wishlist/", {"product": product.slug}, format="json").data["wishlisted"] is True
    assert auth.get("/api/v1/cart/wishlist/").data["count"] == 1
    assert auth.post("/api/v1/cart/wishlist/", {"product": product.slug}, format="json").data["wishlisted"] is False


def test_orders_list_pagination(auth, customer, variant):
    for _ in range(3):
        add(auth, variant)
        auth.post(
            "/api/v1/orders/checkout/", {"email": customer.email, "address": ADDRESS, "payment_method": "cod"}, format="json"
        )
    page = auth.get("/api/v1/orders/?page_size=2")
    assert page.data["count"] == 3 and len(page.data["results"]) == 2 and page.data["total_pages"] == 2
    assert auth.get("/api/v1/orders/summary/").data["open"] == 3
