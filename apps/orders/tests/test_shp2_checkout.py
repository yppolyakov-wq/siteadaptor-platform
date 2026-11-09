"""SHP-2: оформление по СПИСКУ способов доставки.

Замки: способ берётся только из включённых способов бизнеса (чужой/выключенный id —
ошибка, а не тихий самовывоз); выключенный самовывоз выбрать нельзя; доставка компанией
до двери требует адрес; пункт выдачи — номер, PLZ, город, у Packstation — PostNummer;
вес корзины решает цену и доступность; заказ хранит снимок способа (компания, подпись,
пункт выдачи), ссылка отслеживания — по компании; один способ — без выбора в форме."""

import uuid
from decimal import Decimal

import pytest
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.template.loader import render_to_string
from django.test import RequestFactory

from apps.catalog.tests.factories import ProductFactory
from apps.orders import delivery_choice, public_views
from apps.orders.models import Order, ShippingMethod
from apps.orders.shipping import Parcel
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(data, cart):
    request = RequestFactory().post("/warenkorb/bestellen/", data)
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.8"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.session["cart"] = cart
    request.tenant = TenantFactory.build()
    return request


def _dhl(**kw):
    kw.setdefault("fee_cents", 499)
    kw.setdefault("delivery_time", "2–4 Tage")
    return ShippingMethod.objects.create(kind="carrier", carrier="dhl", **kw)


ADDR = {"street": "Hauptstr. 1", "plz": "42651", "city": "Solingen"}


def test_carrier_home_delivery_creates_order_with_snapshot():
    dhl = _dhl()
    product = ProductFactory(base_price=Decimal("10.00"))
    request = _req({"name": "K", "fulfillment": str(dhl.pk), **ADDR}, {str(product.pk): 1})
    public_views.checkout(request)
    order = Order.objects.get()
    assert order.is_delivery and order.shipping_cents == 499
    assert order.total == Decimal("14.99")
    assert (order.shipping_kind, order.shipping_carrier) == ("carrier", "dhl")
    assert order.shipping_method_id == str(dhl.pk)
    assert order.shipping_label == "Versand mit DHL · 2–4 Tage"
    order.tracking_code = "00340434"
    assert order.tracking_url.endswith("piececode=00340434")


def test_foreign_or_disabled_method_is_refused_not_silent_pickup():
    _dhl()
    off = _dhl(active=False)
    tenant = TenantFactory.build()
    for raw in (str(off.pk), str(uuid.uuid4()), "pickup"):
        choice = delivery_choice.resolve({"fulfillment": raw, **ADDR}, tenant, 1000)
        assert not choice and choice.error, raw  # самовывоза у бизнеса нет


def test_pickup_switched_off_cannot_be_chosen():
    ShippingMethod.objects.create(kind="pickup", active=False)
    dhl = _dhl()
    product = ProductFactory(base_price=Decimal("10.00"))
    request = _req({"name": "K", "fulfillment": "pickup"}, {str(product.pk): 1})
    public_views.checkout(request)
    assert not Order.objects.exists()
    assert any("erhalten" in str(m) for m in get_messages(request))
    choice = delivery_choice.resolve({"fulfillment": "delivery", **ADDR}, TenantFactory.build(), 0)
    assert choice.method.pk == dhl.pk  # устаревшая форма «delivery» → первая доставка


def test_home_delivery_requires_address():
    dhl = _dhl()
    choice = delivery_choice.resolve({"fulfillment": str(dhl.pk)}, TenantFactory.build(), 1000)
    assert not choice


def test_packstation_needs_number_and_postnummer():
    point = _dhl(service="pickup_point")
    base = {"fulfillment": str(point.pk), "point_type": "packstation", "point_ref": "123"}
    base.update({"point_plz": "42651", "point_city": "Solingen"})
    tenant = TenantFactory.build()
    assert not delivery_choice.resolve(base, tenant, 1000)  # без PostNummer
    choice = delivery_choice.resolve({**base, "postnummer": "12345678"}, tenant, 1000)
    assert choice and choice.delivery
    assert choice.shipping_address == "Packstation 123\nPostNummer 12345678\n42651 Solingen"
    assert choice.snapshot["pickup_point_postnummer"] == "12345678"
    hermes = ShippingMethod.objects.create(kind="carrier", carrier="hermes", service="pickup_point")
    shop = {"fulfillment": str(hermes.pk), "point_ref": "4711", "point_plz": "1", "point_city": "X"}
    tenant = TenantFactory.build()  # новый запрос: список способов мемо на объекте тенанта
    choice = delivery_choice.resolve(shop, tenant, 1000)  # PaketShop: PostNummer не нужна
    assert choice and choice.snapshot["pickup_point_type"] == "paketshop"
    bogus = {**shop, "point_type": "packstation"}  # у Hermes нет Packstation
    assert delivery_choice.resolve(bogus, tenant, 1000).snapshot["pickup_point_type"] == "paketshop"


def test_weight_decides_price_and_too_heavy_is_not_offered():
    tiers = [{"max_g": 2000, "fee_cents": 499}, {"max_g": 10000, "fee_cents": 999}]
    dhl = _dhl(pricing="weight", weight_tiers=tiers)
    tenant = TenantFactory.build()
    post = {"fulfillment": str(dhl.pk), **ADDR}
    assert (
        delivery_choice.resolve(post, tenant, 0, parcel=Parcel(known_g=3000)).shipping_cents == 999
    )
    heavy = Parcel(known_g=20000)
    assert not delivery_choice.resolve(post, tenant, 0, parcel=heavy)
    keys = [o["key"] for o in delivery_choice.context(tenant, 0, parcel=heavy)["shipping_options"]]
    assert str(dhl.pk) not in keys


def test_single_method_has_no_choice_and_legacy_form_is_unchanged():
    dhl = _dhl()
    ctx = delivery_choice.context(TenantFactory.build())
    html = render_to_string("storefront/_fulfillment_choice.html", ctx)
    assert f'type="hidden" name="fulfillment" value="{dhl.pk}"' in html
    assert 'type="radio"' not in html and "Versand mit DHL" in html
    ShippingMethod.objects.all().update(active=False)  # (только для этого теста)
    legacy = TenantFactory.build(delivery_enabled=True, delivery_fee_cents=390)
    # строки есть, но все выключены — по правилу «строки есть = только они» нет ни одной
    assert delivery_choice.context(legacy)["shipping_options"] == []


def test_control_chars_cannot_forge_address_lines_or_crash():
    point = _dhl(service="pickup_point")
    post = {
        "fulfillment": str(point.pk),
        "point_type": "packstation",
        "point_ref": "123\nPostNummer 999999\x00",
        "postnummer": "12345678",
        "point_plz": "42651\r\n",
        "point_city": "Solingen\x00",
    }
    choice = delivery_choice.resolve(post, TenantFactory.build(), 1000)
    assert choice.shipping_address.count("\n") == 2  # три строки, не больше
    assert "\x00" not in choice.shipping_address
    home = _dhl()
    choice = delivery_choice.resolve(
        {"fulfillment": str(home.pk), **ADDR, "street": "A\nB 1"}, TenantFactory.build(), 1000
    )
    assert choice.shipping_address.splitlines()[0] == "A B 1"


def test_offer_without_products_hides_methods_with_weight_limits():
    from apps.orders.models import Offer, OfferLine
    from apps.orders.offers import parcel_for_offer

    offer = Offer.objects.create(customer_name="K", customer_email="k@t.de")
    OfferLine.objects.create(offer=offer, title="Freitext", qty=2, unit_price=Decimal("10"))
    parcel = parcel_for_offer(offer)
    assert parcel.unknown_qty == 2
    limited = _dhl(max_weight_g=31500)
    keys = [
        o["key"]
        for o in delivery_choice.context(TenantFactory.build(), 0, parcel=parcel)[
            "shipping_options"
        ]
    ]
    assert str(limited.pk) not in keys


def test_dsgvo_clears_pickup_point_data():
    from apps.crm.dsgvo import ERASURE_POLICY

    cleared = ERASURE_POLICY["orders.Order"][1]
    assert "pickup_point_ref" in cleared and "pickup_point_postnummer" in cleared


def test_only_one_pickup_method_and_display_fee_before_free_threshold():
    ShippingMethod.objects.create(kind="pickup", locations=[{"name": "A", "address": "1"}])
    ShippingMethod.objects.create(kind="pickup", locations=[{"name": "B", "address": "2"}])
    _dhl(free_from_cents=2000)
    opts = delivery_choice.context(TenantFactory.build(), 5000)["shipping_options"]
    assert [o["kind"] for o in opts] == ["pickup", "carrier"]  # второй самовывоз не предлагается
    assert opts[1]["fee_cents"] == 499  # показ — до порога; порог применяется к итогу


def test_no_fitting_method_says_so_instead_of_promising_pickup():
    _dhl(bulky_ok=False)
    ctx = delivery_choice.context(TenantFactory.build(), 0, parcel=Parcel(bulky=True))
    html = render_to_string("storefront/_fulfillment_choice.html", ctx)
    assert "data-no-shipping" in html and "Pickup in store" not in html


def test_switching_delivery_to_pickup_clears_the_method_snapshot():
    from apps.orders import editing, services

    order = services.create_order(
        items=[(ProductFactory(base_price=Decimal("5")), 1)],
        name="K",
        fulfillment="delivery",
        shipping_address="A 1\n1 X",
        shipping_cents=499,
        shipping_snapshot={"shipping_kind": "carrier", "shipping_carrier": "dhl"},
    )
    assert order.shipping_carrier == "dhl"
    editing.update_delivery(order, fulfillment="pickup")
    order.refresh_from_db()
    assert (order.shipping_carrier, order.shipping_kind) == ("", "")
