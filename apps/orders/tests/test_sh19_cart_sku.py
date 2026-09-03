"""SH-19: артикул в строке корзины (вариант сильнее товара)."""

import uuid
from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.models import ProductVariant
from apps.catalog.tests.factories import ProductFactory
from apps.orders import public_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(session):
    request = RequestFactory().get("/warenkorb/")
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.9"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.session.update(session)
    request.tenant = TenantFactory.build()
    return request


def test_cart_row_shows_article_number_of_product_and_variant():
    product = ProductFactory(base_price=Decimal("3.00"), sku="BR-001")
    body = public_views.cart_view(_req({"cart": {str(product.pk): 1}})).content.decode()
    assert "data-artno" in body and "BR-001" in body
    variant = ProductVariant.objects.create(
        product=product, label="Groß", price=Decimal("4.00"), sku="BR-001-G"
    )
    body = public_views.cart_view(
        _req({"cart": {f"{product.pk}:{variant.pk}": 1}})
    ).content.decode()
    assert "BR-001-G" in body


def test_cart_row_without_sku_prints_no_label():
    product = ProductFactory(base_price=Decimal("3.00"), sku="")
    body = public_views.cart_view(_req({"cart": {str(product.pk): 1}})).content.decode()
    assert "data-artno" not in body
