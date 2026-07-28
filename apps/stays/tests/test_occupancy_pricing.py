"""PMS-D: ручные occupancy-правила цены («занятость ≥ X % → ±Y % на ночь»).

План docs/pms-d-occupancy-pricing-plan-2026-07-28.md: включает ТОЛЬКО витрина;
стойка/reprice — базовая цена; без правил всё байт-в-байт как раньше."""

import uuid
from datetime import date, timedelta

import pytest

from apps.stays import availability, pricing, services
from apps.stays.models import StayBooking, StaySettings, StayUnit

pytestmark = pytest.mark.django_db

D0 = date(2026, 9, 1)


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _unit(**kwargs):
    kwargs.setdefault("price_cents", 10000)
    kwargs.setdefault("quantity", 2)
    kwargs.setdefault("max_guests", 4)
    return StayUnit.objects.create(name=f"Z {uuid.uuid4().hex[:6]}", **kwargs)


def _rules(rules):
    settings = StaySettings.load()
    settings.occupancy_rules = rules
    settings.save(update_fields=["occupancy_rules"])
    return settings


def test_clean_occupancy_rules_caps_and_garbage():
    settings = _rules(
        [
            {"occupancy": 80, "percent": 10},
            {"occupancy": 0, "percent": 10},  # порог вне 1..100
            {"occupancy": 50, "percent": 0},  # нулевой процент — мусор
            {"occupancy": 90, "percent": 99},  # процент вне −50..+50
            "kaputt",
            {"occupancy": 30, "percent": -15},
        ]
    )
    assert settings.clean_occupancy_rules() == [
        {"occupancy": 80, "percent": 10},
        {"occupancy": 30, "percent": -15},
    ]
    settings = _rules([{"occupancy": i + 1, "percent": 5} for i in range(20)])
    assert len(settings.clean_occupancy_rules()) == 10  # кап 10 правил


def test_occupancy_adjust_picks_strictest_rule():
    rules = [{"occupancy": 50, "percent": 5}, {"occupancy": 80, "percent": 15}]
    assert pricing.occupancy_adjust(10000, 90, rules) == 11500  # ≥80 → строже
    assert pricing.occupancy_adjust(10000, 60, rules) == 10500
    assert pricing.occupancy_adjust(10000, 40, rules) == 10000
    assert pricing.occupancy_adjust(10000, None, rules) == 10000
    assert pricing.occupancy_adjust(10000, 90, [{"occupancy": 50, "percent": -15}]) == 8500


def test_quote_without_kwargs_is_unchanged_even_with_rules():
    """Характеризационный замок: правила заведены, но вызов без kwargs (стойка,
    reprice, events, агрегатор) даёт прежний базовый итог."""
    unit = _unit()
    _rules([{"occupancy": 1, "percent": 50}])
    assert pricing.quote_total_cents(unit, D0, D0 + timedelta(days=2)) == 20000


def test_occupancy_by_day_counts_bookings_and_blocks():
    from apps.stays.models import UnitBlock

    unit = _unit(quantity=2)
    services.book_stay(unit, arrival=D0, departure=D0 + timedelta(days=1), name="A")
    UnitBlock.objects.create(
        unit=unit, start_date=D0 + timedelta(days=1), end_date=D0 + timedelta(days=1)
    )
    occ = availability.occupancy_by_day(unit, D0, D0 + timedelta(days=3))
    assert occ[D0] == 50  # 1 бронь из 2
    assert occ[D0 + timedelta(days=1)] == 50  # блок выводит номер из продажи
    assert occ[D0 + timedelta(days=2)] == 0


def test_storefront_quote_and_booking_use_dynamic_price_desk_does_not():
    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.stays import views
    from apps.stays.public_views import _quote

    unit = _unit(quantity=2)
    _rules([{"occupancy": 50, "percent": 10}])
    # Первая бронь поднимает занятость обеих ночей до 50 %.
    services.book_stay(unit, arrival=D0, departure=D0 + timedelta(days=2), name="Erste")

    # Витринный квот: 2 ночи × 10000 × 1.10.
    nights, total, available, reason, _n = _quote(unit, D0, D0 + timedelta(days=2), guests=2)
    assert available and total == 22000

    # Витринная бронь (dynamic_pricing=True) фиксирует ту же цену.
    b = services.book_stay(
        unit,
        arrival=D0,
        departure=D0 + timedelta(days=2),
        name="Zweite",
        dynamic_pricing=True,
    )
    assert b.total_cents == 22000

    # Стойка (walk-in вьюха) — базовая цена без надбавки.
    request = RequestFactory().post(
        "/dashboard/stays/new/",
        {
            "unit": str(unit.pk),
            "arrival": (D0 + timedelta(days=10)).isoformat(),
            "departure": (D0 + timedelta(days=12)).isoformat(),
            "name": "Desk Gast",
            "erw": "1",
        },
    )
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    o = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(username=f"o-{o}", password="pw12345678")
    services.book_stay(  # поднимаем занятость целевых ночей до 50 %
        unit,
        arrival=D0 + timedelta(days=10),
        departure=D0 + timedelta(days=12),
        name="Dritte",
    )
    assert views.stay_create(request).status_code == 302
    desk = StayBooking.objects.get(customer__name="Desk Gast")
    assert desk.total_cents == 20000  # база, без +10 %


def test_units_page_occupancy_rule_add_delete():
    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.stays import views

    def _req(method="get", data=None):
        request = getattr(RequestFactory(), method)("/dashboard/stays/units/", data or {})
        SessionMiddleware(lambda r: None).process_request(request)
        MessageMiddleware(lambda r: None).process_request(request)
        o = uuid.uuid4().hex[:8]
        request.user = get_user_model().objects.create_user(
            username=f"o-{o}", password="pw12345678"
        )
        return request

    _unit()
    resp = views.units(
        _req("post", {"action": "occupancy_add", "occupancy": "80", "percent": "12"})
    )
    assert resp.status_code == 302
    assert StaySettings.load().clean_occupancy_rules() == [{"occupancy": 80, "percent": 12}]

    body = views.units(_req()).content.decode()
    assert "Dynamic prices" in body and "80" in body

    resp = views.units(_req("post", {"action": "occupancy_delete", "index": "0"}))
    assert resp.status_code == 302
    assert StaySettings.load().clean_occupancy_rules() == []
