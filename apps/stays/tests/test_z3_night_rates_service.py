"""KA-12 Zimmer Z-3: массовая правка поночного слоя (`apps/stays/night_rates.py`).

План строится из текущего состояния и содержит только изменённые ячейки; запись —
одна транзакция под блокировкой категорий; «nicht ändern» ≠ «zurücksetzen»;
нейтральная строка удаляется; ±% не уходит в 0; двойной POST ±% не поднимает
цену дважды; брони не меняются (снимок Z-1)."""

import uuid
from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.core.tests.dates import future_month_start
from apps.stays import night_rates as nr
from apps.stays import pricing, services
from apps.stays.models import NightRate, SeasonRate, StayUnit

pytestmark = pytest.mark.django_db

D0 = future_month_start(3)
ALL = range(7)


def _unit(**kw):
    kw.setdefault("price_cents", 10000)
    kw.setdefault("quantity", 2)
    return StayUnit.objects.create(name=f"DZ {uuid.uuid4().hex[:6]}", **kw)


def _d(n):
    return D0 + timedelta(days=n)


def _days(n, weekdays=ALL):
    return nr.select_days(_d(0), _d(n - 1), weekdays)


def _apply(units, days, action):
    units = list(StayUnit.objects.filter(pk__in=[u.pk for u in units]))
    plan = nr.build_plan(units, days, action)
    return nr.apply_plan(
        [u.pk for u in units],
        days,
        action,
        expected_fingerprint=plan.fingerprint(action),
        actor=None,
    )


def _row(unit, day):
    return NightRate.objects.filter(unit=unit, day=day).first()


def test_set_price_only_selected_weekdays_and_units():
    a, b, other = _unit(), _unit(), _unit()
    days = nr.select_days(_d(0), _d(13), [4, 5])  # Fr, Sa
    _apply([a, b], days, nr.Action(price_mode="set", price_cents=12900))
    assert NightRate.objects.filter(unit__in=[a, b]).count() == 2 * len(days)
    assert all(r.day.weekday() in (4, 5) for r in NightRate.objects.all())
    assert not NightRate.objects.filter(unit=other).exists()
    assert pricing.quote_total_cents(a, days[0], days[0] + timedelta(days=1)) == 12900


def test_keep_is_not_reset():
    unit = _unit()
    NightRate.objects.create(unit=unit, day=_d(0), price_cents=15000)
    _apply([unit], [_d(0)], nr.Action(stop_sell=True))
    row = _row(unit, _d(0))
    assert row.price_cents == 15000 and row.stop_sell is True
    _apply([unit], [_d(0)], nr.Action(price_mode="reset"))
    row = _row(unit, _d(0))
    assert row.price_cents is None and row.stop_sell is True


def test_neutral_rows_are_deleted():
    unit = _unit()
    NightRate.objects.create(unit=unit, day=_d(0), price_cents=15000)
    NightRate.objects.create(unit=unit, day=_d(1), stop_sell=True)
    NightRate.objects.create(unit=unit, day=_d(2), min_nights=3)
    _apply([unit], [_d(0)], nr.Action(price_mode="reset"))
    _apply([unit], [_d(1)], nr.Action(stop_sell=False))
    _apply([unit], [_d(2)], nr.Action(min_nights=0))
    assert not NightRate.objects.filter(unit=unit).exists()


def test_percent_from_season_day_and_weekend():
    unit = _unit(price_cents=8999, weekend_price_cents=12000)
    SeasonRate.objects.create(unit=unit, start_date=_d(0), end_date=_d(0), price_cents=20000)
    NightRate.objects.create(unit=unit, day=_d(1), price_cents=5000)
    days = _days(7)
    _apply([unit], days, nr.Action(price_mode="percent", percent=10))
    prices = {r.day: r.price_cents for r in NightRate.objects.filter(unit=unit)}
    assert prices[_d(0)] == 22000  # сезон
    assert prices[_d(1)] == 5500  # своя цена дня
    for day in days[2:]:
        base = 12000 if day.weekday() in (4, 5) else 8999
        expected = round(base * 1.1 + 1e-9) if base != 8999 else 9899  # ROUND_HALF_UP
        assert prices[day] == expected


def test_negative_percent_never_reaches_zero_and_writes_nothing():
    unit = _unit(price_cents=4)  # 4 × 0,1 = 0,4 → 0 ct
    action = nr.Action(price_mode="percent", percent=-90)
    plan = nr.build_plan([unit], [_d(0)], action)
    assert plan.rejected
    with pytest.raises(nr.PlanRejected):
        nr.apply_plan(
            [unit.pk], [_d(0)], action, expected_fingerprint=plan.fingerprint(action), actor=None
        )
    assert not NightRate.objects.exists()


def test_unchanged_cells_untouched():
    unit = _unit()
    NightRate.objects.create(unit=unit, day=_d(0), price_cents=12000)
    before = _row(unit, _d(0)).updated_at
    plan = nr.build_plan([unit], [_d(0), _d(1)], nr.Action(price_mode="set", price_cents=12000))
    assert [c.day for c in plan.changes] == [_d(1)]
    _apply([unit], [_d(0), _d(1)], nr.Action(price_mode="set", price_cents=12000))
    assert _row(unit, _d(0)).updated_at == before


def test_set_is_idempotent():
    unit = _unit()
    action = nr.Action(price_mode="set", price_cents=13000)
    _apply([unit], _days(3), action)
    assert nr.build_plan([unit], _days(3), action).changes == ()
    assert _apply([unit], _days(3), action) == nr.ApplyResult(0, 0, 0, 3)


def test_double_post_percent_is_stale():
    unit = _unit()
    action = nr.Action(price_mode="percent", percent=10)
    fp = nr.build_plan([unit], [_d(0)], action).fingerprint(action)
    nr.apply_plan([unit.pk], [_d(0)], action, expected_fingerprint=fp, actor=None)
    with pytest.raises(nr.StalePlan):
        nr.apply_plan([unit.pk], [_d(0)], action, expected_fingerprint=fp, actor=None)
    assert _row(unit, _d(0)).price_cents == 11000


def test_missing_fingerprint_refused():
    unit = _unit()
    with pytest.raises(nr.StalePlan):
        nr.apply_plan(
            [unit.pk], [_d(0)], nr.Action(stop_sell=True), expected_fingerprint="", actor=None
        )


def test_past_days_refused_under_lock():
    unit = _unit()
    yesterday = timezone.localdate() - timedelta(days=1)
    with pytest.raises(nr.StalePlan):
        nr.apply_plan(
            [unit.pk], [yesterday], nr.Action(stop_sell=True), expected_fingerprint="x", actor=None
        )


def test_validate_scope():
    today = timezone.localdate()
    ok = dict(
        n_units=1,
        n_requested=1,
        garbage=False,
        von=today,
        bis=today,
        weekdays=list(ALL),
        today=today,
    )
    assert nr.validate_scope(**ok) == []
    assert nr.validate_scope(**{**ok, "von": today - timedelta(days=1)})
    assert nr.validate_scope(**{**ok, "bis": today - timedelta(days=1), "von": today})
    assert nr.validate_scope(**{**ok, "bis": today + timedelta(days=nr.MAX_HORIZON_DAYS + 1)})
    assert nr.validate_scope(**{**ok, "weekdays": []})
    assert nr.validate_scope(**{**ok, "garbage": True})
    assert nr.validate_scope(**{**ok, "n_units": 0})  # чужой/несуществующий id
    assert nr.validate_scope(**{**ok, "n_requested": nr.MAX_UNITS + 1, "n_units": nr.MAX_UNITS + 1})
    big = {
        **ok,
        "n_units": 40,
        "n_requested": 40,
        "bis": today + timedelta(days=700),
        "weekdays": list(ALL),
    }
    assert nr.validate_scope(**big)  # 40 × 701 > MAX_CELLS


@pytest.mark.parametrize(
    "data,price_cents,ok",
    [
        ({"price_mode": "set", "price": "12,50"}, 1250, True),
        ({"price_mode": "set", "price": "1.234,56"}, 123456, True),
        ({"price_mode": "set", "price": "12,505"}, None, False),
        ({"price_mode": "set", "price": "0"}, None, False),
        ({"price_mode": "set", "price": "-5"}, None, False),
        ({"price_mode": "set", "price": "NaN"}, None, False),
        ({"price_mode": "percent", "percent": "0"}, None, False),
        ({"price_mode": "percent", "percent": "Infinity"}, None, False),
        ({"price_mode": "percent", "percent": "1e999"}, None, False),
        ({"price_mode": "percent", "percent": "10,5"}, None, False),
        ({"min_mode": "set", "min_nights": "366"}, None, False),
        ({}, None, False),
    ],
)
def test_parse_action(data, price_cents, ok):
    action, errors = nr.parse_action(data)
    assert (action is not None) is ok and bool(errors) is not ok
    if ok:
        assert action.price_cents == price_cents


def test_parse_action_tristate_and_percent():
    action, _ = nr.parse_action({"price_mode": "percent", "percent": "+15", "stop_sell": "off"})
    assert action.percent == 15 and action.stop_sell is False and action.no_checkin is None


def test_locks_units_ordered_by_id():
    a, b = _unit(), _unit()
    with CaptureQueriesContext(connection) as ctx:
        _apply([a, b], [_d(0)], nr.Action(stop_sell=True))
    lock = [q["sql"] for q in ctx.captured_queries if "FOR UPDATE" in q["sql"]]
    assert lock and 'FROM "stays_stayunit"' in lock[0] and "ORDER BY" in lock[0]


def test_query_budget_independent_of_days():
    a, b = _unit(), _unit()

    def count(n):
        NightRate.objects.all().delete()
        with CaptureQueriesContext(connection) as ctx:
            _apply([a, b], _days(n), nr.Action(price_mode="set", price_cents=11111))
        return len(ctx.captured_queries)

    assert count(14) == count(31)


def test_same_instance_sees_new_price():
    unit = _unit()
    assert pricing.quote_total_cents(unit, _d(0), _d(1)) == 10000
    action = nr.Action(price_mode="set", price_cents=7000)
    fp = nr.build_plan([unit], [_d(0)], action).fingerprint(action)
    nr.apply_plan([unit.pk], [_d(0)], action, expected_fingerprint=fp, actor=None)
    unit = StayUnit.objects.get(pk=unit.pk)
    assert pricing.quote_total_cents(unit, _d(0), _d(1)) == 7000


def test_existing_booking_unchanged():
    unit = _unit()
    b = services.book_stay(unit, arrival=_d(0), departure=_d(2), name="G", email="z3@t.de")
    total, snap = b.total_cents, list(b.night_prices)
    _apply([unit], _days(2), nr.Action(price_mode="set", price_cents=30000))
    b.refresh_from_db()
    assert b.total_cents == total and b.night_prices == snap


def test_audit_written_without_pii(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "apps.audit.services.audit_event", lambda **kw: calls.append(kw), raising=True
    )
    unit = _unit()
    _apply([unit], _days(3), nr.Action(price_mode="set", price_cents=9000))
    assert len(calls) == 1
    ctx = calls[0]["context"]
    assert set(ctx) == {
        "unit_ids",
        "units",
        "von",
        "bis",
        "nights",
        "created",
        "updated",
        "deleted",
        "action",
    }
    assert ctx["created"] == 3 and ctx["nights"] == 3


def test_no_stayunit_save(monkeypatch):
    from django.db.models.signals import post_save

    seen = []

    def _recv(sender, **kw):
        seen.append(sender)

    post_save.connect(_recv, sender=StayUnit)
    try:
        unit = _unit()
        seen.clear()
        _apply([unit], _days(3), nr.Action(price_mode="set", price_cents=9000))
    finally:
        post_save.disconnect(_recv, sender=StayUnit)
    assert seen == []


def test_nightrate_access_stays_in_allowed_modules():
    """Замок: чтение/запись NightRate только в pricing/restrictions/night_rates/tasks."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[3] / "apps"
    allowed = {"pricing.py", "restrictions.py", "night_rates.py", "tasks.py"}
    offenders = []
    for path in root.rglob("*.py"):
        if "tests" in path.parts or "migrations" in path.parts:
            continue
        if "NightRate.objects" in path.read_text() and path.name not in allowed:
            offenders.append(str(path))
    assert offenders == []


def test_move_stay_locks_units_in_id_order():
    """DB-ревью Z-3: move_stay лочит юниты по id — как массовая правка (без дедлока)."""
    a, b = _unit(), _unit()
    booking = services.book_stay(a, arrival=_d(0), departure=_d(2), name="G", email="mv@t.de")
    with CaptureQueriesContext(connection) as ctx:
        services.move_stay(booking, arrival=_d(0), departure=_d(2), unit=b)
    lock = [
        q["sql"]
        for q in ctx.captured_queries
        if "FOR UPDATE" in q["sql"] and "stays_stayunit" in q["sql"]
    ]
    assert lock and "ORDER BY" in lock[0]


def test_failed_audit_does_not_roll_back_price_change(monkeypatch):
    """Silent-failure ревью: сбой INSERT аудита в своём savepoint, правка цен цела."""
    from django.db.transaction import mark_for_rollback_on_error

    def broken_audit(**kw):
        try:
            with mark_for_rollback_on_error():
                with connection.cursor() as cur:
                    cur.execute("SELECT 1/0")
        except Exception:  # noqa: BLE001 — как audit_event: не пробрасывает
            pass

    monkeypatch.setattr("apps.audit.services.audit_event", broken_audit)
    unit = _unit()
    _apply([unit], _days(2), nr.Action(price_mode="set", price_cents=9100))
    assert NightRate.objects.filter(unit=unit, price_cents=9100).count() == 2


def test_small_int_rejects_unicode_digits():
    assert nr.small_int("²") is None and nr.small_int("12") == 12 and nr.small_int("1234") is None
    assert nr.parse_weekdays(["²", "3", "9"]) == [3]
    action, errors = nr.parse_action({"min_mode": "set", "min_nights": "²"})
    assert action is None and errors


def test_scope_without_matching_weekday_is_error():
    today = timezone.localdate()
    monday = today + timedelta(days=(7 - today.weekday()) % 7 or 7)
    errors = nr.validate_scope(
        n_units=1, n_requested=1, garbage=False, von=monday, bis=monday, weekdays=[1], today=today
    )
    assert errors
