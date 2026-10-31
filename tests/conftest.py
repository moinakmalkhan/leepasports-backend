import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.accounts.models import Address, Company, CompanyMember, User
from apps.accounts.services import create_company
from apps.catalog.models import Product


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    with django_db_blocker.unblock():
        call_command("seed_catalog", verbosity=0)


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def buyer(db):
    user = User.objects.create_user(
        email="buyer@example.com", password="Str0ngPassw0rd!", first_name="Sam", is_email_verified=True
    )
    company = create_company(user=user, name="Test FC", business_type=Company.BusinessType.CLUB, country="GB")
    Address.objects.create(company=company, contact_name="Sam", line1="1 Road", city="Leeds", country="GB", is_default=True)
    return user


@pytest.fixture
def auth(api, buyer):
    response = api.post("/api/v1/auth/login/", {"email": buyer.email, "password": "Str0ngPassw0rd!"}, format="json")
    assert response.status_code == 200, response.content
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
    api.tokens = response.data
    return api


@pytest.fixture
def staff(db):
    return User.objects.create_superuser(email="staff@example.com", password="Str0ngPassw0rd!")


@pytest.fixture
def product(db):
    return Product.objects.for_detail().get(sku="LS-SOC-001")


def size_breakdown(product, qty_each=5, gender="men", labels=("M", "L", "XL")):
    options = {o.size.label: o.size_id for o in product.size_options.all() if o.gender == gender}
    return [{"gender": gender, "size_id": options[label], "quantity": qty_each} for label in labels]


@pytest.fixture
def cart_with_item(auth, product):
    response = auth.post(
        "/api/v1/cart/",
        {
            "product": product.slug,
            "fabric": "micro-mesh",
            "breakdown": size_breakdown(product),
            "color": "Red",
            "customization": {"logo": "Left chest"},
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    return response.data


def shipping_address_uid(user):
    return str(Address.objects.filter(company__members__user=user).first().uid)


__all__ = ["CompanyMember", "size_breakdown", "shipping_address_uid"]
