"""KA-12 E4.1b: ресурс без правил работает в часы бизнеса (правила ресурса сильнее),
«Aus Öffnungszeiten übernehmen» и `within_hours` для проверки переноса (E4.3)."""

from datetime import datetime, time, timedelta
from types import SimpleNamespace

import pytest
from django.db import connection
from django.utils import timezone

from apps.booking import availability, views
from apps.booking.models import AvailabilityRule
from apps.booking.tests.test_cabinet import _req, _resource, _tenant_urlconf  # noqa: F401

pytestmark = pytest.mark.django_db

HOURS = {str(d): ["09:00", "12:00"] for d in range(7)}


@pytest.fixture
def hours(monkeypatch):
    shop = SimpleNamespace(schema_name=connection.schema_name, opening_hours_structured=HOURS)
    monkeypatch.setattr(connection, "tenant", shop, raising=False)
    return shop


def _day():
    return timezone.localdate() + timedelta(days=3)


def _at(day, h, m=0):
    return datetime.combine(day, time(h, m), tzinfo=timezone.get_current_timezone())


def test_resource_without_rules_uses_business_hours(hours):
    slots = availability.free_slots(_resource(), _day())
    assert [s.time() for s, _e in slots][:2] == [time(9), time(9, 30)]
    assert slots[-1][1].time() == time(12)


def test_resource_rules_win_over_business_hours(hours):
    r = _resource()
    AvailabilityRule.objects.create(
        resource=r, weekday=_day().weekday(), start_time="14:00", end_time="15:00", slot_minutes=60
    )
    assert [s.time() for s, _e in availability.free_slots(r, _day())] == [time(14)]


def test_no_rules_no_hours_no_slots(monkeypatch):
    monkeypatch.setattr(connection, "tenant", SimpleNamespace(), raising=False)
    assert availability.free_slots(_resource(), _day()) == []


def test_within_hours(hours):
    r, d = _resource(), _day()
    assert availability.within_hours(r, _at(d, 9), _at(d, 10))
    assert not availability.within_hours(r, _at(d, 11, 30), _at(d, 12, 30))
    assert not availability.within_hours(r, _at(d, 7), _at(d, 8))


def test_within_hours_unknown_does_not_block(monkeypatch):
    monkeypatch.setattr(connection, "tenant", SimpleNamespace(), raising=False)
    d = _day()
    assert availability.within_hours(_resource(), _at(d, 3), _at(d, 4))


def test_rules_from_hours_button_creates_missing_days(hours):
    r = _resource()
    AvailabilityRule.objects.create(
        resource=r, weekday=0, start_time="14:00", end_time="15:00", slot_minutes=60
    )
    req = _req(
        "post", "/dashboard/booking/resources/", {"action": "rules_from_hours", "resource": r.pk}
    )
    req.tenant = hours
    views.resources(req)
    rules = {x.weekday: (x.start_time, x.end_time) for x in r.rules.all()}
    assert len(rules) == 7 and rules[0] == (time(14), time(15)) and rules[3] == (time(9), time(12))
