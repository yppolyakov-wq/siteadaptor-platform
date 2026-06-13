"""R2: Grundpreis (PAngV) — расчёт, свойства модели, форма, витрина."""

from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.forms import ProductForm
from apps.catalog.models import ProductVariant
from apps.catalog.pricing import grundpreis
from apps.catalog.tests.factories import ProductFactory
from apps.promotions import public_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


# --- расчёт -----------------------------------------------------------------------


def test_grundpreis_units():
    assert grundpreis(Decimal("4.90"), "g", Decimal("250")) == (Decimal("19.60"), "kg")
    assert grundpreis(Decimal("10.00"), "kg", Decimal("2")) == (Decimal("5.00"), "kg")
    assert grundpreis(Decimal("3.00"), "ml", Decimal("500")) == (Decimal("6.00"), "l")
    assert grundpreis(Decimal("9.00"), "l", Decimal("0.75")) == (Decimal("12.00"), "l")


def test_grundpreis_none_cases():
    assert grundpreis(Decimal("5"), "", Decimal("100")) is None  # Stück/несчётное
    assert grundpreis(Decimal("5"), "g", None) is None
    assert grundpreis(Decimal("5"), "g", Decimal("0")) is None
    assert grundpreis(None, "g", Decimal("100")) is None


# --- модель -----------------------------------------------------------------------


def test_product_grundpreis_property():
    p = ProductFactory(base_price=Decimal("4.90"), unit="g", content_amount=Decimal("250"))
    assert p.grundpreis == (Decimal("19.60"), "kg")
    assert ProductFactory(base_price=Decimal("4.90")).grundpreis is None  # unit пусто


def test_variant_grundpreis_own_and_fallback_content():
    product = ProductFactory(base_price=Decimal("9.90"), unit="g", content_amount=Decimal("100"))
    own = ProductVariant.objects.create(
        product=product, label="250 g", price=Decimal("19.00"), content_amount=Decimal("250")
    )
    fallback = ProductVariant.objects.create(product=product, label="X", price=Decimal("5.00"))
    assert own.grundpreis == (Decimal("76.00"), "kg")  # 19.00 / 0.25 kg
    assert fallback.grundpreis == (Decimal("50.00"), "kg")  # 5.00 / 0.1 kg (контент товара)


# --- форма ------------------------------------------------------------------------


def test_product_form_saves_unit_and_content():
    form = ProductForm(
        {
            "name_de": "Mehl",
            "base_price": "1.99",
            "currency": "EUR",
            "unit": "kg",
            "content_amount": "1",
        }
    )
    assert form.is_valid(), form.errors
    product = form.save()
    assert product.unit == "kg"
    assert product.content_amount == Decimal("1")


# --- витрина ----------------------------------------------------------------------


def _req(path, tenant=None):
    request = RequestFactory().get(path)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant or TenantFactory.build(name="Shop")
    return request


def test_storefront_shows_grundpreis():
    p = ProductFactory(base_price=Decimal("4.90"), unit="g", content_amount=Decimal("250"))
    body = public_views.product_detail(_req(f"/sortiment/{p.pk}/"), pk=p.pk).content.decode()
    assert "/ kg" in body  # строка Grundpreis отрисована


def test_storefront_no_grundpreis_for_stueck():
    p = ProductFactory(base_price=Decimal("4.90"))  # unit пусто
    body = public_views.product_detail(_req(f"/sortiment/{p.pk}/"), pk=p.pk).content.decode()
    assert "/ kg" not in body
