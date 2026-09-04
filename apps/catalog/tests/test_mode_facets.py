"""MODE-1/MODE-2: фасеты цвета и «только со скидкой» + карточка товара в
контракте `sellable_card`.

Почему замки нужны. Магазин одежды выбирают цветом и размером; размер фасетом
был, ЦВЕТА не было вовсе (ось `ProductVariant.color` существовала только как
свотч на карточке). «Nur reduziert» — второй по частоте фильтр витрины с
акциями. Карточка товара в `_sellable_card.html` не имела своей ветки и падала
в «услугу»: вместо цены печаталась пустая длительность («min») — это видно на
странице лукбука и в выдаче Finder.
"""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.models import ProductVariant
from apps.catalog.tests.factories import CategoryFactory, ProductFactory
from apps.promotions import public_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _body(params=None):
    request = RequestFactory().get("/sortiment/", params or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(name="Studio X", business_type="clothing")
    return public_views.product_list(request).content.decode()


def _shop():
    cat = CategoryFactory(slug="damen", name={"de": "Damen"})
    blue = ProductFactory(name={"de": "Blaues Kleid"}, category=cat, base_price="45.00")
    red = ProductFactory(name={"de": "Rotes Kleid"}, category=cat, base_price="55.00")
    for size in ("S", "M"):
        ProductVariant.objects.create(product=blue, size=size, color="Blau", stock_quantity=3)
        ProductVariant.objects.create(product=red, size=size, color="Rot", stock_quantity=3)
    return blue, red


def test_color_facet_filters_and_shows_swatches():
    blue, red = _shop()
    body = _body()
    assert 'name="farbe"' in body and 'value="Blau"' in body
    assert "#2563eb" in body  # свотч красится HEX'ом реестра option_styles

    only_blue = _body({"farbe": "Blau"})
    assert "Blaues Kleid" in only_blue and "Rotes Kleid" not in only_blue


def test_color_chips_hidden_when_shop_has_one_color():
    cat = CategoryFactory(slug="uni", name={"de": "Uni"})
    p = ProductFactory(name={"de": "Nur Blau"}, category=cat, base_price="10.00")
    ProductVariant.objects.create(product=p, size="S", color="Blau", stock_quantity=2)
    assert 'name="farbe"' not in _body()  # один цвет — фильтр был бы шумом


def test_sold_out_color_is_not_offered():
    """Фильтр обещает наличие: вариант с нулём в фасет не попадает (как у размера)."""
    cat = CategoryFactory(slug="d2", name={"de": "D2"})
    p = ProductFactory(name={"de": "Ausverkauft Grün"}, category=cat, base_price="20.00")
    ProductVariant.objects.create(product=p, size="S", color="Grün", stock_quantity=0)
    ProductVariant.objects.create(product=p, size="M", color="Blau", stock_quantity=4)
    assert "Ausverkauft Grün" not in _body({"farbe": "Grün"})
    assert "Ausverkauft Grün" in _body({"farbe": "Blau"})


def test_sale_facet_follows_the_active_promotion():
    from apps.promotions.models import Promotion

    blue, red = _shop()
    assert 'name="sale"' not in _body()  # скидок нет — тумблера нет
    Promotion.objects.create(
        title={"de": "Blaues Kleid −20 %"}, product=blue, discount_percent=20, status="active"
    )
    body = _body()
    assert 'name="sale"' in body
    reduced = _body({"sale": "1"})
    assert "Blaues Kleid" in reduced and "Rotes Kleid" not in reduced


def test_sellable_card_of_a_product_shows_price_not_a_service_duration():
    """MODE-2: ветки товара не было — карточка лукбука печатала «min» без цены."""
    from django.template import Context, Template

    cat = CategoryFactory(slug="d3", name={"de": "D3"})
    p = ProductFactory(name={"de": "Leinenbluse"}, category=cat, base_price="39.90")
    html = Template("{% load sellable_ui %}{% sellable_card 'product' obj edit=False %}").render(
        Context({"obj": p})
    )
    assert "39,90" in html or "39.90" in html
    assert "min" not in html.replace("min-w-0", "").replace("min-h", "")
