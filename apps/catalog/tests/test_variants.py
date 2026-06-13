"""R1: варианты товара — модель (цена/has_variants/price_from) и CRUD-вьюхи."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog import views
from apps.catalog.models import ProductVariant
from apps.catalog.tests.factories import ProductFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        username="o", email="o@test.de", password="pw12345678"
    )


def _post(user, data):
    req = RequestFactory().post("/x/", data)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = user
    return req


# --- модель -----------------------------------------------------------------------


def test_price_value_fallback_to_base():
    product = ProductFactory(base_price=Decimal("9.90"))
    v1 = ProductVariant.objects.create(product=product, label="100 g")  # без своей цены
    v2 = ProductVariant.objects.create(product=product, label="250 g", price=Decimal("19.00"))
    assert v1.price_value == Decimal("9.90")
    assert v2.price_value == Decimal("19.00")


def test_has_variants_and_price_from():
    product = ProductFactory(base_price=Decimal("9.90"))
    assert product.has_variants is False
    assert product.price_from == Decimal("9.90")
    ProductVariant.objects.create(product=product, label="100 g", price=Decimal("5.00"))
    ProductVariant.objects.create(product=product, label="250 g", price=Decimal("12.00"))
    ProductVariant.objects.create(
        product=product, label="alt", price=Decimal("1.00"), is_active=False
    )
    assert product.has_variants is True
    assert product.price_from == Decimal("5.00")  # min активных; неактивный игнорируем


# --- вьюхи ------------------------------------------------------------------------


def test_variant_add(user):
    product = ProductFactory()
    resp = views.variant_add(
        _post(user, {"label": "100 g", "price": "5,50", "stock": "10"}), pk=product.pk
    )
    assert resp.status_code == 302
    v = ProductVariant.objects.get(product=product)
    assert v.label == "100 g"
    assert v.price == Decimal("5.50")
    assert v.stock_quantity == 10


def test_variant_add_requires_label(user):
    product = ProductFactory()
    views.variant_add(_post(user, {"label": "  "}), pk=product.pk)
    assert ProductVariant.objects.filter(product=product).count() == 0


def test_variant_add_rejects_duplicate_label(user):
    product = ProductFactory()
    ProductVariant.objects.create(product=product, label="M")
    views.variant_add(_post(user, {"label": "M"}), pk=product.pk)
    assert ProductVariant.objects.filter(product=product, label="M").count() == 1


def test_variant_update(user):
    product = ProductFactory()
    v = ProductVariant.objects.create(product=product, label="M", price=Decimal("5.00"))
    views.variant_update(
        _post(user, {"price": "7,00", "stock": "3", "sort": "2"}), pk=product.pk, vid=v.pk
    )
    v.refresh_from_db()
    assert v.price == Decimal("7.00")
    assert v.stock_quantity == 3
    assert v.sort_order == 2
    assert v.is_active is False  # чекбокс не передан → снят


def test_variant_delete(user):
    product = ProductFactory()
    v = ProductVariant.objects.create(product=product, label="M")
    views.variant_delete(_post(user, {}), pk=product.pk, vid=v.pk)
    assert not ProductVariant.objects.filter(pk=v.pk).exists()
