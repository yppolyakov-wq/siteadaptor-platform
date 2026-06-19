"""CA2: содержимое ЛК — разделы по активным модулям (история клиента)."""

from decimal import Decimal

import pytest
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.account import account_data
from apps.catalog.tests.factories import ProductFactory
from apps.orders.services import create_order
from apps.promotions.models import Customer
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(disabled=None):
    request = RequestFactory().get("/konto/")
    SessionMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(
        business_type="restaurant", disabled_modules=disabled or []
    )
    return request


def test_orders_section_lists_customer_orders():
    product = ProductFactory(base_price=Decimal("8.00"))
    order = create_order(items=[(product, 1)], name="Max", email="max@test.de")
    customer = Customer.objects.get(email__iexact="max@test.de")
    sections = account_data.sections_for(_req(), customer)
    orders = next((s for s in sections if s["key"] == "orders"), None)
    assert orders and any(order.reference_code in it["title"] for it in orders["items"])


def test_section_hidden_when_module_inactive():
    product = ProductFactory(base_price=Decimal("8.00"))
    create_order(items=[(product, 1)], name="Max", email="max@test.de")
    customer = Customer.objects.get(email__iexact="max@test.de")
    sections = account_data.sections_for(_req(disabled=["orders"]), customer)
    assert not any(s["key"] == "orders" for s in sections)


def test_empty_customer_has_no_sections():
    customer = Customer.objects.create(name="", email="leer@test.de")
    assert account_data.sections_for(_req(), customer) == []
