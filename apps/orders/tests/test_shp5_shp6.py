"""SHP-5/6: страница «Versand & Lieferung», приписка «zzgl. Versandkosten» (§ 6 PAngV),
доставка в фиде Google и способы получения в каталоге города.

Замки: страница перечисляет только включённые способы (цены, ступени веса, зоны, адреса
самовывоза); приписки нет, если доставки нет (один самовывоз) или заказы выключены;
`g:shipping` — только способы с одной ценой по Германии (по весу/по зонам — нет), вес —
`g:shipping_weight`; фид наличия «в магазине» пуст, если забрать в магазине нельзя;
листинг города знает способы получения, а факт «Erhältlich per» — только у товаров."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.http import Http404
from django.template import Context, Template
from django.test import RequestFactory

from apps.catalog.feed import _shipping_weight, build_google_feed, merchant_shipping
from apps.catalog.tests.factories import ProductFactory
from apps.orders import public_views, shipping
from apps.orders.models import ShippingMethod
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(**kw):
    kw.setdefault("schema_name", "public")
    return TenantFactory.build(**kw)


def _request(tenant=None):
    request = RequestFactory().get("/versand/")
    request.tenant = tenant or _tenant()
    return request


def _note(tenant) -> bool:
    out = Template("{% load shipping_tags %}{% shipping_note as n %}{{ n }}").render(
        Context({"request": SimpleNamespace(tenant=tenant)})
    )
    return out.strip() == "True"


# --- SHP-5: страница и приписка ----------------------------------------------------------


def test_page_lists_active_methods_with_prices_tiers_zones_and_locations():
    ShippingMethod.objects.create(
        kind="pickup", locations=[{"name": "Laden Mitte", "address": "Markt 1"}]
    )
    ShippingMethod.objects.create(
        kind="courier",
        fee_cents=350,
        zones=[{"plz": "42651", "fee_cents": 250}],
        restrict_to_zones=True,
        delivery_time="heute",
    )
    ShippingMethod.objects.create(
        kind="carrier",
        carrier="dhl",
        pricing="weight",
        weight_tiers=[{"max_g": 2000, "fee_cents": 499}, {"max_g": 10000, "fee_cents": 999}],
        free_from_cents=5000,
    )
    ShippingMethod.objects.create(kind="carrier", carrier="hermes", fee_cents=399, active=False)
    tenant = _tenant()
    shipping.forget(tenant)
    body = public_views.shipping_info(_request(tenant)).content.decode()
    assert "Laden Mitte" in body and "Markt 1" in body
    assert "42651" in body and "2,50" in body and "3,50" in body
    assert "4,99" in body and "9,99" in body and "50,00" in body
    assert 'data-shipping-row="carrier"' in body and "Hermes" not in body


def test_page_is_404_without_orders(monkeypatch):
    tenant = _tenant()
    monkeypatch.setattr(tenant, "is_module_active", lambda key: False)
    with pytest.raises(Http404):
        public_views.shipping_info(_request(tenant))


def test_note_only_when_something_is_delivered(monkeypatch):
    tenant = _tenant()
    ShippingMethod.objects.create(kind="pickup")
    shipping.forget(tenant)
    assert _note(tenant) is False  # один самовывоз — приписки нет
    ShippingMethod.objects.create(kind="carrier", carrier="dhl", fee_cents=499)
    shipping.forget(tenant)
    assert _note(tenant) is True
    monkeypatch.setattr(tenant, "is_module_active", lambda key: False)
    assert _note(tenant) is False  # без заказов страницы /versand/ нет — и ссылки


# --- SHP-6: Google ------------------------------------------------------------------------


def test_feed_shipping_only_flat_german_prices():
    ShippingMethod.objects.create(kind="pickup")
    ShippingMethod.objects.create(kind="carrier", carrier="dhl", fee_cents=499)
    ShippingMethod.objects.create(
        kind="carrier", carrier="dpd", pricing="weight", weight_tiers=[{"max_g": 1, "fee_cents": 1}]
    )
    ShippingMethod.objects.create(
        kind="courier", fee_cents=300, zones=[{"plz": "42651"}], restrict_to_zones=True
    )
    tenant = _tenant()
    shipping.forget(tenant)
    rows = merchant_shipping(tenant)
    assert rows == [{"country": "DE", "service": "Versand mit DHL", "price": "4.99 EUR"}]


def test_feed_item_carries_shipping_and_weight():
    from apps.catalog.models import Product

    p = ProductFactory(base_price=Decimal("10"), shipping_weight_g=750)
    xml = build_google_feed(
        products=Product.objects.filter(pk=p.pk),
        title="t",
        link="https://x/",
        description="d",
        product_url=lambda _p: "https://x/p",
        absolutize=lambda u: "https://x" + u,
        merchant=True,
        shipping=[{"country": "DE", "service": "DHL", "price": "4.99 EUR"}],
    )
    assert (
        "<g:shipping><g:country>DE</g:country><g:service>DHL</g:service>"
        "<g:price>4.99 EUR</g:price></g:shipping>"
    ) in xml
    assert "<g:shipping_weight>750 g</g:shipping_weight>" in xml


def test_shipping_weight_variant_overrides_product():
    product = SimpleNamespace(shipping_weight_g=500)
    assert _shipping_weight(product) == "500 g"
    assert _shipping_weight(product, SimpleNamespace(shipping_weight_g=900)) == "900 g"
    assert _shipping_weight(product, SimpleNamespace(shipping_weight_g=None)) == "500 g"
    assert _shipping_weight(SimpleNamespace(shipping_weight_g=None)) == ""


# --- SHP-6: каталог города ----------------------------------------------------------------


def test_listing_fulfilment_and_fact():
    from apps.aggregator import offer_facts, tasks

    ShippingMethod.objects.create(kind="pickup")
    ShippingMethod.objects.create(kind="carrier", carrier="dhl", fee_cents=499)
    tenant = _tenant()
    shipping.forget(tenant)
    assert tasks._fulfilment(tenant) == ["pickup", "carrier"]

    product = SimpleNamespace(
        listing_kind="product", fulfilment=["pickup", "carrier"], availability=""
    )
    facts = {f["key"]: f for f in offer_facts.facts(product)}
    assert str(facts["fulfilment"]["value"]) == "Abholung · Versand"
    room = SimpleNamespace(listing_kind="stay", fulfilment=["pickup"], availability="")
    assert "fulfilment" not in {f["key"] for f in offer_facts.facts(room)}


def test_fulfilment_failure_is_unknown_not_crash(monkeypatch):
    from apps.aggregator import tasks

    def boom(_tenant):
        raise RuntimeError("x")

    monkeypatch.setattr(shipping, "methods", boom)
    tenant = _tenant()
    assert tasks._fulfilment(tenant) is None  # «не знаем» — не пустой список
    assert "fulfilment" not in tasks._tenant_base_defaults(tenant)  # старое не затираем


def test_fulfilment_empty_without_orders(monkeypatch):
    from apps.aggregator import tasks

    tenant = _tenant()
    monkeypatch.setattr(tenant, "is_module_active", lambda key: False)
    assert tasks._fulfilment(tenant) == []


def test_no_note_when_delivery_is_always_free():
    ShippingMethod.objects.create(kind="carrier", carrier="dhl", fee_cents=0)
    tenant = _tenant()
    shipping.forget(tenant)
    assert _note(tenant) is False


# --- SHP-7: отчёт и демо ------------------------------------------------------------------


def test_report_lists_legacy_delivery_and_flags_parcel_wording():
    from apps.orders.management.commands.shipping_report import report_for

    tenant = _tenant(delivery_enabled=True, delivery_fee_cents=490, delivery_area="Versand mit DHL")
    row = report_for(tenant)
    assert row["looks_like_parcel"] is True and row["fee_cents"] == 490
    tenant.delivery_area = "Nur 42651 Solingen"
    assert report_for(tenant)["looks_like_parcel"] is False
    assert report_for(_tenant(delivery_enabled=False)) is None
    ShippingMethod.objects.create(kind="pickup")
    assert report_for(tenant) is None  # способы уже сохранены — переезжать нечего


def test_demo_kits_seed_shipping_methods_once():
    from apps.tenants import demo_kits

    tenant = TenantFactory(schema_name="public")
    demo_kits._seed_shipping(tenant, demo_kits.ONLINE_SHOP)
    kinds = list(ShippingMethod.objects.values_list("kind", flat=True))
    assert kinds == ["courier", "carrier", "carrier", "pickup"]
    demo_kits._seed_shipping(tenant, demo_kits.ONLINE_SHOP)
    assert ShippingMethod.objects.count() == 4
    for kit in (demo_kits.CLOTHING, demo_kits.OUTLET, demo_kits.ONLINE_SHOP):
        assert any(s["kind"] == "carrier" for s in kit.shipping), kit.key
