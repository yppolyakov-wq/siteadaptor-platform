"""SHP-0/1: способы доставки — единый читатель `orders.shipping`.

Замки: пока у бизнеса нет строк, способы строятся из прежних полей Tenant и курьер считает
РОВНО как `services.delivery_quote` (паритет на наборе конфигураций); сохранённые строки
заменяют прежние настройки целиком; Paketdienst — плоско или по весу, неизвестный/лишний
вес и превышение ограничений скрывают способ (никогда 0 €); «frei ab» обнуляет сбор."""

from types import SimpleNamespace

import pytest

from apps.orders import carriers, shipping
from apps.orders.models import ShippingMethod
from apps.orders.services import delivery_quote
from apps.orders.shipping import Parcel

pytestmark = pytest.mark.django_db


def _tenant(**kw):
    base = {
        "delivery_enabled": True,
        "delivery_fee_cents": 400,
        "delivery_free_cents": 0,
        "delivery_min_cents": 0,
        "delivery_zones": [],
        "delivery_restrict_to_zones": False,
        "delivery_area": "",
        "pickup_points": [],
        "pickup_min_cents": 0,
    }
    base.update(kw)
    return SimpleNamespace(**base)


ZONES = [
    {"plz": "40, 41", "fee_cents": 200, "free_cents": 3000, "min_cents": ""},
    {"plz": "42651", "fee_cents": 0, "free_cents": "", "min_cents": 1500},
    {"plz": "43", "fee_cents": "kaputt", "free_cents": None, "min_cents": None},
]
CONFIGS = [
    {},
    {"delivery_free_cents": 2500},
    {"delivery_min_cents": 1000, "delivery_fee_cents": 0},
    {"delivery_zones": ZONES},
    {"delivery_zones": ZONES, "delivery_restrict_to_zones": True},
    {"delivery_zones": ZONES, "delivery_free_cents": 5000, "delivery_min_cents": 800},
]


@pytest.mark.parametrize("cfg", CONFIGS)
@pytest.mark.parametrize("subtotal", [0, 999, 2500, 3000, 6000])
@pytest.mark.parametrize("plz", ["", "40210", "41000", "42651", "43111", "50667", "ab"])
def test_legacy_courier_quotes_exactly_like_delivery_quote(cfg, subtotal, plz):
    tenant = _tenant(**cfg)
    courier = shipping.by_kind(shipping.methods(tenant), "courier")[0]
    assert shipping.quote(courier, subtotal, plz) == delivery_quote(tenant, subtotal, plz)


def test_without_rows_pickup_always_and_courier_only_when_enabled():
    kinds = [m.kind for m in shipping.methods(_tenant(delivery_enabled=False))]
    assert kinds == ["pickup"]
    tenant = _tenant(pickup_points=[{"name": "Markt", "address": "Platz 1"}], pickup_min_cents=500)
    pickup, courier = shipping.methods(tenant)
    assert (pickup.kind, courier.kind) == ("pickup", "courier")
    assert pickup.locations == [{"name": "Markt", "address": "Platz 1"}]
    assert shipping.quote(pickup, 100)["min_cents"] == 500
    assert pickup._state.adding and not ShippingMethod.objects.exists()  # чтение ничего не пишет


def test_stored_rows_replace_legacy_settings():
    ShippingMethod.objects.create(kind="carrier", carrier="dhl", fee_cents=499)
    ShippingMethod.objects.create(kind="pickup", active=False)
    got = shipping.methods(_tenant())
    assert [m.kind for m in got] == ["carrier"]  # выключенный самовывоз не предлагается
    assert len(shipping.methods(_tenant(), active_only=False)) == 2


def test_other_schema_reads_legacy_not_foreign_rows(django_assert_num_queries):
    from unittest import mock

    from django.db import connection

    ShippingMethod.objects.create(kind="carrier", carrier="dhl", fee_cents=499)
    foreign = _tenant(schema_name="t_somebody_else", delivery_enabled=False)
    with mock.patch.object(connection, "schema_name", "t_this_shop"):
        with django_assert_num_queries(0):
            assert [m.kind for m in shipping.methods(foreign)] == ["pickup"]


def test_public_schema_without_table_reads_legacy():
    from unittest import mock

    with mock.patch.object(shipping, "_table_in_public", return_value=False):
        assert [m.kind for m in shipping.methods(_tenant(delivery_enabled=False))] == ["pickup"]


def test_one_query_per_request_and_forget_after_write(django_assert_num_queries):
    tenant = _tenant()
    with django_assert_num_queries(1):
        shipping.methods(tenant)
        shipping.methods(tenant)
    ShippingMethod.objects.create(kind="carrier", carrier="dhl")
    shipping.forget(tenant)
    assert [m.kind for m in shipping.methods(tenant)] == ["carrier"]


def test_methods_cannot_be_deleted_only_deactivated():
    from apps.orders.models import ShippingMethodDeleteForbidden

    m = ShippingMethod.objects.create(kind="pickup")
    with pytest.raises(ShippingMethodDeleteForbidden):
        m.delete()
    with pytest.raises(ShippingMethodDeleteForbidden):
        ShippingMethod.objects.all().delete()


def test_carrier_flat_and_free_from():
    m = ShippingMethod(kind="carrier", carrier="dhl", fee_cents=499, free_from_cents=5000)
    assert shipping.quote(m, 1000)["fee_cents"] == 499
    assert shipping.quote(m, 5000)["fee_cents"] == 0


def test_carrier_by_weight_tiers_never_zero_when_unknown_or_too_heavy():
    m = ShippingMethod(
        kind="carrier",
        carrier="dhl",
        pricing="weight",
        packaging_g=200,
        weight_tiers=[{"max_g": 5000, "fee_cents": 699}, {"max_g": 2000, "fee_cents": 499}],
    )
    assert shipping.quote(m, 1000, parcel=Parcel(known_g=1800))["fee_cents"] == 499
    assert shipping.quote(m, 1000, parcel=Parcel(known_g=1801))["fee_cents"] == 699
    assert not shipping.quote(m, 1000, parcel=Parcel(known_g=4900))["deliverable"]
    assert not shipping.quote(m, 1000)["deliverable"]  # профиль посылки неизвестен
    # позиция без веса: без веса по умолчанию — не 0 €, а недоступно; с ним — считается
    assert not shipping.quote(m, 1000, parcel=Parcel(known_g=500, unknown_qty=2))["deliverable"]
    m.default_item_g = 400
    assert shipping.quote(m, 1000, parcel=Parcel(known_g=500, unknown_qty=2))["fee_cents"] == 499


def test_limits_and_bulky_hide_courier_and_carrier_but_not_pickup():
    m = ShippingMethod(kind="carrier", carrier="dhl", fee_cents=499, max_weight_g=31500)
    assert not shipping.quote(m, 0, parcel=Parcel(known_g=32000))["deliverable"]
    # предел задан, а вес не определить (позиция без веса, нет веса по умолчанию) — скрыт
    assert not shipping.quote(m, 0, parcel=Parcel(unknown_qty=1))["deliverable"]
    m.max_length_cm = 120
    assert not shipping.quote(m, 0, parcel=Parcel(known_g=1000, longest_cm=150))["deliverable"]
    assert shipping.quote(m, 0, parcel=Parcel(known_g=1000, longest_cm=100))["deliverable"]
    bulky = Parcel(known_g=1000, bulky=True)
    assert not shipping.quote(m, 0, parcel=bulky)["deliverable"]
    spedition = ShippingMethod(kind="carrier", carrier="other", fee_cents=4900, bulky_ok=True)
    assert shipping.quote(spedition, 0, parcel=bulky)["fee_cents"] == 4900
    assert shipping.quote(ShippingMethod(kind="pickup"), 0, parcel=bulky)["deliverable"]


def test_labels_and_carrier_registry():
    assert shipping.label(ShippingMethod(kind="carrier", carrier="dhl")) == "Versand mit DHL"
    point = ShippingMethod(kind="carrier", carrier="hermes", service="pickup_point")
    assert shipping.label(point) == "Hermes an eine Abholstelle"
    assert shipping.label(ShippingMethod(kind="courier", name="Fahrradkurier")) == "Fahrradkurier"
    assert carriers.get("dhl").pickup_point == ("packstation", "postfiliale")
    assert carriers.get("hermes").pickup_point == ("paketshop",)
    assert carriers.tracking_url("dpd", "01 23/4") == (
        "https://tracking.dpd.de/status/de_DE/parcel/01%2023%2F4"
    )
    assert carriers.tracking_url("other", "123") == ""
