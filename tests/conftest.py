import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.accounts.models import Address, User
from apps.catalog.models import Product, ProductVariant


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    with django_db_blocker.unblock():
        call_command("seed_catalog", "--no-images", verbosity=0)


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def customer(db):
    user = User.objects.create_user(
        email="ali@test.com", password="Str0ngPassw0rd!", first_name="Ali", phone="03001234567", is_email_verified=True
    )
    Address.objects.create(
        user=user, full_name="Ali Raza", phone="03001234567", line1="House 1", city="Lahore", province="Punjab", is_default=True
    )
    return user


@pytest.fixture
def auth(api, customer):
    response = api.post("/api/v1/auth/login/", {"email": customer.email, "password": "Str0ngPassw0rd!"}, format="json")
    assert response.status_code == 200, response.content
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
    api.tokens = response.data
    return api


@pytest.fixture
def staff(db):
    return User.objects.create_superuser(email="staff@test.com", password="Str0ngPassw0rd!")


@pytest.fixture
def product(db):
    return Product.objects.for_detail().get(sku="CH-TEE-001")


@pytest.fixture
def variant(product):
    return ProductVariant.objects.filter(product=product, stock__gte=5, stock__lt=10).select_related("color", "size").first()


ADDRESS = {
    "full_name": "Ali Raza",
    "phone": "03001234567",
    "line1": "House 1, Street 2",
    "city": "Lahore",
    "province": "Punjab",
    "postal_code": "54000",
    "country": "PK",
}
