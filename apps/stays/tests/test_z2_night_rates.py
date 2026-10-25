"""KA-12 Zimmer Z-2: поночный слой цен и ограничений (`NightRate`).

Храним только переопределённые дни. Цена ночи: NightRate → SeasonRate → выходные →
база (затем тариф и occupancy, как прежде). Ограничения дня (стоп-продажа, мин.
ночей при заезде, запрет заезда/выезда) — только витрина, как G12; кабинет бронирует.
Пустой слой — все прежние цены байт-в-байт (паритет-замки stays целы)."""

import uuid
from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction

from apps.core.tests.dates import future_month_start
from apps.stays import pricing, restrictions, services
from apps.stays.models import NightRate, RatePlan, SeasonRate, StayUnit

pytestmark = pytest.mark.django_db

D0 = future_month_start(3)


def _unit(**kw):
    kw.setdefault("price_cents", 10000)
    kw.setdefault("quantity", 2)
    return StayUnit.objects.create(name=f"DZ {uuid.uuid4().hex[:6]}", **kw)


def _d(n):
    return D0 + timedelta(days=n)


def test_priority_night_over_season_over_base():
    unit = _unit()
    SeasonRate.objects.create(unit=unit, start_date=_d(0), end_date=_d(3), price_cents=15000)
    NightRate.objects.create(unit=unit, day=_d(1), price_cents=20000)
    NightRate.objects.create(unit=unit, day=_d(2), stop_sell=True)  # без цены → сезон
    assert pricing.quote_total_cents(unit, _d(0), _d(4)) == 15000 + 20000 + 15000 + 15000


def test_breakdown_equals_quote_and_marks_night():
    unit = _unit()
    NightRate.objects.create(unit=unit, day=_d(0), price_cents=12345)
    plan = RatePlan.objects.create(name="HP", surcharge_cents=1000, percent_adjust=10)
    rows = pricing.price_breakdown(unit, _d(0), _d(2), rate_plan=plan)
    assert sum(r["cents"] for r in rows) == pricing.quote_total_cents(
        unit, _d(0), _d(2), rate_plan=plan
    )
    assert pricing.night_snapshot(unit, _d(0), _d(2))[0][2] == "@night"


def test_empty_layer_is_unchanged():
    unit = _unit()
    assert pricing.quote_total_cents(unit, _d(0), _d(3)) == 30000


def test_quote_is_one_query_for_night_rates(django_assert_max_num_queries):
    unit = _unit()
    for i in range(5):
        NightRate.objects.create(unit=unit, day=_d(i), price_cents=11000 + i)
    unit = StayUnit.objects.get(pk=unit.pk)
    with django_assert_max_num_queries(2):  # сезоны + окно NightRate
        pricing.quote_total_cents(unit, _d(0), _d(7))


def test_stop_sell_blocks_storefront_only():
    unit = _unit()
    NightRate.objects.create(unit=unit, day=_d(1), stop_sell=True)
    assert restrictions.violation(unit, _d(0), _d(3), today=D0 - timedelta(days=5)) == (
        "stop_sell",
        None,
    )
    assert restrictions.violation(unit, _d(2), _d(4), today=D0 - timedelta(days=5)) is None
    # кабинет (walk-in) не ограничивается
    b = services.book_stay(unit, arrival=_d(0), departure=_d(3), name="Walk", email="w@t.de")
    assert b.pk


def test_stop_sell_rechecked_inside_booking_lock():
    """TOCTOU: владелец поставил стоп-продажу после показа — бронь витрины отклонена."""
    unit = _unit()
    NightRate.objects.create(unit=unit, day=_d(1), stop_sell=True)
    with pytest.raises(services.RestrictionViolated):
        services.book_stay(
            unit,
            arrival=_d(0),
            departure=_d(3),
            name="G",
            email="g@t.de",
            enforce_restrictions=True,
        )


def test_day_min_nights_and_checkin_checkout():
    unit = _unit()
    today = D0 - timedelta(days=5)
    NightRate.objects.create(unit=unit, day=_d(0), min_nights=3)
    NightRate.objects.create(unit=unit, day=_d(5), no_checkin=True)
    NightRate.objects.create(unit=unit, day=_d(9), no_checkout=True)
    assert restrictions.violation(unit, _d(0), _d(2), today=today) == ("rule_min_nights", 3)
    assert restrictions.violation(unit, _d(0), _d(3), today=today) is None
    assert restrictions.violation(unit, _d(5), _d(7), today=today) == ("no_checkin", None)
    assert restrictions.violation(unit, _d(7), _d(9), today=today) == ("no_checkout", None)


def test_neutral_row_is_rejected_by_constraint():
    unit = _unit()
    with pytest.raises(IntegrityError), transaction.atomic():
        NightRate.objects.create(unit=unit, day=_d(0))


def test_unique_unit_day():
    unit = _unit()
    NightRate.objects.create(unit=unit, day=_d(0), price_cents=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        NightRate.objects.create(unit=unit, day=_d(0), stop_sell=True)


def test_booking_snapshot_uses_night_price():
    unit = _unit()
    NightRate.objects.create(unit=unit, day=_d(0), price_cents=17000)
    b = services.book_stay(unit, arrival=_d(0), departure=_d(2), name="G", email="s@t.de")
    assert [row[1] for row in b.night_prices] == [17000, 10000]
    assert b.total_cents == 27000 - b.auto_discount_cents + b.kurtaxe_cents


def test_month_calendar_hides_stop_sell_day():
    from apps.stays import availability

    unit = _unit()
    NightRate.objects.create(unit=unit, day=_d(3), stop_sell=True)
    days = {
        d["date"]: d["is_free"]
        for d in availability.month_availability(unit, D0.year, D0.month, today=D0)
    }
    assert days[_d(3)] is False and days[_d(4)] is True


def test_feed_reflects_night_price_and_stop_sell(settings):
    from datetime import date as _date

    from django.utils import timezone

    from apps.stays import public_views
    from apps.stays.tests.test_public import _req

    settings.ROOT_URLCONF = "config.urls_tenant"
    unit = _unit()
    today = timezone.localdate()
    NightRate.objects.create(unit=unit, day=today + timedelta(days=2), price_cents=13300)
    NightRate.objects.create(unit=unit, day=today + timedelta(days=3), stop_sell=True)
    import json

    data = json.loads(public_views.stays_feed(_req(path="/unterkunft/feed.json")).content)
    room = next(r for r in data["rooms"] if r["id"] == str(unit.pk))
    by_day = {_date.fromisoformat(n["date"]): n for n in room["nights"]}
    assert by_day[today + timedelta(days=2)]["price"] == 133.0
    assert by_day[today + timedelta(days=3)]["available"] is False


def test_purge_keeps_recent_and_future():
    from apps.stays import tasks

    unit = _unit()
    today = D0
    old = NightRate.objects.create(unit=unit, day=today - timedelta(days=31), price_cents=1)
    recent = NightRate.objects.create(unit=unit, day=today - timedelta(days=5), price_cents=1)
    future = NightRate.objects.create(unit=unit, day=today + timedelta(days=5), price_cents=1)
    assert tasks.purge_due_night_rates(today=today) == 1
    left = set(NightRate.objects.values_list("pk", flat=True))
    assert old.pk not in left and {recent.pk, future.pk} <= left


def test_next_free_range_skips_stop_sell():
    from apps.stays import availability

    unit = _unit(quantity=1)
    NightRate.objects.create(unit=unit, day=_d(0), stop_sell=True)
    rng = availability.next_free_range(2, from_day=_d(0), max_days=5)
    assert rng is not None and rng[0] >= _d(1)


def test_hotel_search_respects_stop_sell(monkeypatch):
    from django.db import connection

    from apps.aggregator import hotel_search

    monkeypatch.setattr(
        hotel_search, "cache", type("C", (), {"get": lambda *a: None, "set": lambda *a: None})()
    )
    StayUnit.objects.update(is_active=False)
    unit = _unit()
    NightRate.objects.create(unit=unit, day=_d(1), stop_sell=True)
    ok, _cents = hotel_search.hotel_availability(connection.schema_name, _d(0), _d(3), 1)
    assert ok is False
    ok2, cents2 = hotel_search.hotel_availability(connection.schema_name, _d(2), _d(4), 1)
    assert ok2 is True and cents2 > 0


def test_forget_night_rates_drops_instance_cache():
    unit = _unit()
    assert pricing.quote_total_cents(unit, _d(0), _d(1)) == 10000
    NightRate.objects.create(unit=unit, day=_d(0), price_cents=5000)
    pricing.forget_night_rates(unit)
    assert pricing.quote_total_cents(unit, _d(0), _d(1)) == 5000
