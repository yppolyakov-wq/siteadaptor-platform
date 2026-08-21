"""MX-2: адресные опции + сводный учёт доп-продаж.

План docs/mx2-options-trackers-plan-2026-08-21.md. Замки: адресная опция видна
только у своей сущности и не проходит в снимок чужой; scope-wide поведение
прежнее; Zusatzverkäufe собирает строки по id и прячет отменённые сделки.
"""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core import extras as extras_engine
from apps.core import zusatz
from apps.core.models import Extra
from apps.stays import services as stay_services
from apps.stays.models import StayBooking, StayUnit
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _unit(**kw):
    kw.setdefault("price_cents", 10000)
    kw.setdefault("quantity", 2)
    return StayUnit.objects.create(name=f"Z {uuid.uuid4().hex[:6]}", **kw)


def test_scope_wide_behaviour_unchanged():
    e = Extra.objects.create(label="Parkplatz", price_cents=800, scope=Extra.SCOPE_STAYS)
    assert extras_engine.active_for("stays") == [e]
    assert extras_engine.active_for("stays", entity_kind="stay", entity_id="123") == [e]


def test_addressed_extra_visible_only_for_its_entity():
    unit_a, unit_b = _unit(), _unit()
    bike = Extra.objects.create(
        label="Fahrrad",
        price_cents=2400,
        scope=Extra.SCOPE_STAYS,
        entity_kind="stay",
        entity_id=str(unit_a.pk),
    )
    got_a = extras_engine.active_for("stays", entity_kind="stay", entity_id=str(unit_a.pk))
    got_b = extras_engine.active_for("stays", entity_kind="stay", entity_id=str(unit_b.pk))
    assert bike in got_a and bike not in got_b
    # без адресата (walk-in список / чужая поверхность) — не видна
    assert bike not in extras_engine.active_for("stays")


def test_snapshot_rejects_foreign_entity_option():
    """Подмена формы: id чужой адресной опции не проходит в снимок."""
    unit_a, unit_b = _unit(), _unit()
    bike = Extra.objects.create(
        label="Fahrrad",
        price_cents=2400,
        scope=Extra.SCOPE_STAYS,
        entity_kind="stay",
        entity_id=str(unit_a.pk),
    )
    snap = extras_engine.snapshot([bike.pk], "stays", entity_kind="stay", entity_id=str(unit_b.pk))
    assert snap == []
    snap_ok = extras_engine.snapshot(
        [bike.pk], "stays", entity_kind="stay", entity_id=str(unit_a.pk)
    )
    assert len(snap_ok) == 1 and snap_ok[0]["id"] == str(bike.pk)


def test_zusatz_rows_and_cancelled_hidden():
    tenant = TenantFactory()
    unit = _unit()
    breakfast = Extra.objects.create(
        label="Frühstück", price_cents=1500, scope=Extra.SCOPE_STAYS, per_night=True
    )
    arrival = timezone.localdate() + timedelta(days=3)
    snap = extras_engine.snapshot([breakfast.pk], "stays", nights=2)
    b1 = stay_services.book_stay(
        unit, arrival=arrival, departure=arrival + timedelta(days=2), name="A", extras=snap
    )
    b2 = stay_services.book_stay(
        unit, arrival=arrival, departure=arrival + timedelta(days=2), name="B", extras=snap
    )
    b2.status = StayBooking.STATUS_CANCELLED
    b2.save(update_fields=["status"])

    rows = zusatz.sold_options(tenant, arrival, arrival)
    assert len(rows) == 1 and rows[0]["deal_ref"] == b1.reference_code
    assert rows[0]["option_id"] == str(breakfast.pk)
    assert rows[0]["amount_eur"] == 30.0

    agg = zusatz.summary(rows)
    assert agg[0]["label"] == "Frühstück" and agg[0]["count"] == 1


def test_zusatz_gate():
    assert zusatz.has_any_options() is False
    Extra.objects.create(label="X", price_cents=100)
    assert zusatz.has_any_options() is True
