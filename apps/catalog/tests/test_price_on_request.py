"""AIS W4-6b: «Preis auf Anfrage» — товар «nur auf Anfrage» без цены не печатает «0,00 €».

План docs/ais-w4-6b-price-on-request-plan-2026-11-06.md. Живой дефект: импорт с сайта клиента
создаёт `Product(primary_action="request", base_price=0)`, и витрина печатала «0,00 €».
Замки: свойство · контракт продаваемой сущности · JSON-LD без Offer · фиды исключают · каталог
города не листит (v1) · обычный товар за 0 € остаётся «0,00 €».
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.catalog.models import ProductVariant
from apps.catalog.tests.factories import ProductFactory

pytestmark = pytest.mark.django_db

IMG = [{"url": "/media/p.webp", "is_primary": True}]


def _request(**kw):
    kw.setdefault("images", IMG)
    return ProductFactory(primary_action="request", base_price=Decimal("0"), **kw)


# --- свойство -----------------------------------------------------------------------------


def test_price_on_request_only_for_request_without_price():
    assert _request().price_on_request is True
    assert (
        ProductFactory(primary_action="request", base_price=Decimal("89")).price_on_request is False
    )
    assert ProductFactory(primary_action="", base_price=Decimal("0")).price_on_request is False


def test_request_with_priced_variant_is_not_on_request():
    p = _request()
    ProductVariant.objects.create(product=p, label="Groß", price=Decimal("12.00"), is_active=True)
    p = type(p).objects.get(pk=p.pk)
    assert p.price_on_request is False


# --- контракт и JSON-LD ------------------------------------------------------------------


def test_sellable_says_preis_auf_anfrage_and_has_no_machine_price():
    from apps.core import sellable

    s = sellable.sellable_for("product", _request())
    assert s.price_value is None
    assert "0,00" not in s.price_display and str(s.price_display) == "Preis auf Anfrage"


def test_free_regular_product_still_shows_zero():
    from apps.core import sellable

    s = sellable.sellable_for("product", ProductFactory(primary_action="", base_price=0))
    assert s.price_display == "0,00 €"  # подпись прежняя; машинной цены 0 € и раньше не было


def test_entity_jsonld_has_no_offer():
    from apps.core import sellable, seo

    ld = seo.entity_ld(sellable.sellable_for("product", _request()), url="/x/")
    assert '"offers"' not in ld and '"price"' not in ld


# --- машинные выходы ---------------------------------------------------------------------


def test_merchant_feed_excludes_request_product():
    from apps.catalog import google

    ok, reasons, _ = google.eligibility(_request(description={"de": "Frisch."}))
    assert not ok and "no_price" in reasons


def test_city_catalog_does_not_list_request_product_v1():
    from apps.aggregator import tasks

    assert tasks._product_snapshot(_request().pk) is None


# --- витрина (батч 2) ---------------------------------------------------------------------

ZERO = ("0,00", "0.00")


def _web(path):
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.tenants.tests.factories import TenantFactory

    request = RequestFactory().get(path)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(name="Dachdecker X", contact_phone="02103 1")
    return request


@pytest.fixture
def _tenant_urls(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.mark.parametrize("form", ["", "overlay", "compact", "etikett", "regal", "lookbook", "deal"])
def test_every_card_form_says_preis_auf_anfrage_without_cart(form, _tenant_urls):
    from django.template.loader import render_to_string

    p = _request()
    html = render_to_string(
        "storefront/_product_card.html",
        {"p": p, "storefront_card_style": form, "storefront_quick_add": True},
        request=_web("/"),
    )
    assert "data-price-on-request" in html and "Preis auf Anfrage" in html
    assert not any(z in html for z in ZERO), form
    assert "data-quick-url" not in html and "js-add-form" not in html, form


def test_priced_request_product_keeps_price_but_has_no_quick_add(_tenant_urls):
    """MX-5 «Richtpreis»: цена видна, а «в корзину» — нет (корзины у товара по запросу нет)."""
    from django.template.loader import render_to_string

    p = ProductFactory(primary_action="request", base_price=Decimal("89"), images=IMG)
    html = render_to_string(
        "storefront/_product_card.html",
        {"p": p, "storefront_card_style": "", "storefront_quick_add": True},
        request=_web("/"),
    )
    assert "89" in html and "data-price-on-request" not in html
    assert "data-quick-url" not in html and "js-add-form" not in html


def test_detail_page_shows_label_no_zero_and_no_buybar(_tenant_urls):
    from apps.promotions import public_views

    p = _request()
    html = public_views.product_detail(_web(f"/sortiment/{p.pk}/"), pk=p.pk).content.decode()
    main = html.split("</main>")[0] if "</main>" in html else html
    assert "data-price-on-request" in main
    assert "0,00" not in main and "data-buybar" not in html
    assert 'action="/warenkorb/add/"' not in html


def test_catalog_list_shows_label(_tenant_urls):
    from apps.promotions import public_views

    _request(name={"de": "Dachreparatur"})
    html = public_views.product_list(_web("/sortiment/")).content.decode()
    assert "Dachreparatur" in html and "Preis auf Anfrage" in html
    assert "0,00 €" not in html
