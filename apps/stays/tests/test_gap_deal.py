"""Lücken-Deal (план gap-deal-plan-2026-07-28): скидка на короткие промежутки
между бронями — детектор, интеграция в G4-кандидаты, кабинет, автопредложение."""

import uuid
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.stays import pricing, services, views
from apps.stays.models import StaySettings, StayUnit

pytestmark = pytest.mark.django_db

D0 = date(2026, 9, 1)


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _unit(**kwargs):
    kwargs.setdefault("price_cents", 10000)
    kwargs.setdefault("max_guests", 4)
    return StayUnit.objects.create(name=f"Z {uuid.uuid4().hex[:6]}", **kwargs)


def _settings(nights=3, percent=25):
    s = StaySettings.load()
    s.gap_max_nights = nights
    s.gap_discount_percent = percent
    s.save(update_fields=["gap_max_nights", "gap_discount_percent"])
    return s


def _req(method="get", data=None):
    request = getattr(RequestFactory(), method)("/dashboard/stays/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    o = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(username=f"o-{o}", password="pw12345678")
    return request


def test_gap_discount_detects_bounded_short_gap():
    unit = _unit()
    s = _settings(nights=3, percent=25)
    services.book_stay(
        unit, arrival=D0 + timedelta(days=1), departure=D0 + timedelta(days=3), name="L"
    )
    services.book_stay(
        unit, arrival=D0 + timedelta(days=6), departure=D0 + timedelta(days=9), name="R"
    )

    # Люка = ночи 3,4,5 (3 ночи, зажата с обеих сторон) → скидка.
    assert pricing.gap_discount(unit, D0 + timedelta(days=3), D0 + timedelta(days=6), s) == (
        25,
        "Lücken-Deal −25%",
    )
    # Часть люки — тоже внутри неё → скидка.
    assert pricing.gap_discount(unit, D0 + timedelta(days=3), D0 + timedelta(days=5), s)[0] == 25
    # Запрошенный диапазон занят (пересекает бронь) → нет.
    assert pricing.gap_discount(unit, D0 + timedelta(days=2), D0 + timedelta(days=4), s)[0] == 0


def test_gap_discount_rejects_long_or_unbounded():
    unit = _unit()
    s = _settings(nights=3)
    # Люка 4 ночи (границы заняты) → длиннее лимита → нет.
    services.book_stay(
        unit, arrival=D0 + timedelta(days=1), departure=D0 + timedelta(days=3), name="L"
    )
    services.book_stay(
        unit, arrival=D0 + timedelta(days=7), departure=D0 + timedelta(days=9), name="R"
    )
    assert pricing.gap_discount(unit, D0 + timedelta(days=3), D0 + timedelta(days=6), s)[0] == 0
    # Выключено (gap_max_nights=0) → всегда нет.
    off = _settings(nights=0)
    assert pricing.gap_discount(unit, D0 + timedelta(days=3), D0 + timedelta(days=6), off)[0] == 0


def test_gap_discount_today_edge_is_not_a_boundary():
    unit = _unit()
    s = _settings(nights=3)
    today = timezone.localdate()
    # Справа бронь есть, слева — только «сегодня»: люкой не считается.
    services.book_stay(
        unit, arrival=today + timedelta(days=3), departure=today + timedelta(days=5), name="R"
    )
    assert (
        pricing.gap_discount(unit, today + timedelta(days=1), today + timedelta(days=3), s)[0] == 0
    )


def test_gap_joins_auto_discount_candidates_and_books():
    unit = _unit()
    _settings(nights=3, percent=30)
    services.book_stay(
        unit, arrival=D0 + timedelta(days=1), departure=D0 + timedelta(days=3), name="L"
    )
    services.book_stay(
        unit, arrival=D0 + timedelta(days=6), departure=D0 + timedelta(days=9), name="R"
    )

    # Без unit/departure — поведение байт-в-байт прежнее (0, нет правил G4).
    assert pricing.auto_discount(30000, 3, D0 + timedelta(days=3)) == (0, "")
    # С unit/departure — gap-кандидат побеждает.
    cents, label = pricing.auto_discount(
        30000, 3, D0 + timedelta(days=3), unit=unit, departure=D0 + timedelta(days=6)
    )
    assert cents == 9000 and label == "Lücken-Deal −30%"

    booking = services.book_stay(
        unit, arrival=D0 + timedelta(days=3), departure=D0 + timedelta(days=6), name="Gap Gast"
    )
    assert booking.auto_discount_label == "Lücken-Deal −30%"
    assert booking.total_cents == 30000 - 9000  # 3 × 100 € − 30 %


def test_units_action_and_calendar_hint():
    unit = _unit()
    # Включение через кабинет (one-click с календаря шлёт те же поля).
    resp = views.units(
        _req(
            "post",
            {
                "action": "gap_deal",
                "enabled": "1",
                "gap_max_nights": "3",
                "gap_discount_percent": "25",
            },
        )
    )
    assert resp.status_code == 302
    s = StaySettings.load()
    assert (s.gap_max_nights, s.gap_discount_percent) == (3, 25)
    # Выключение: enabled нет → gap_max_nights=0.
    views.units(_req("post", {"action": "gap_deal", "gap_discount_percent": "25"}))
    assert StaySettings.load().gap_max_nights == 0

    # Автопредложение на календаре: фича выключена + короткая люка есть.
    services.book_stay(
        unit, arrival=D0 + timedelta(days=1), departure=D0 + timedelta(days=3), name="L"
    )
    services.book_stay(
        unit, arrival=D0 + timedelta(days=5), departure=D0 + timedelta(days=7), name="R"
    )
    body = views.calendar(_req(data={"von": D0.isoformat()})).content.decode()
    assert "Lücken-Rabatt aktivieren" in body
    # Включили → подсказка исчезает.
    _settings(nights=3)
    body = views.calendar(_req(data={"von": D0.isoformat()})).content.decode()
    assert "Lücken-Rabatt aktivieren" not in body


def test_wizard_offer_checkbox_enables_gap_deal():
    from apps.core import setup_steps
    from apps.tenants.tests.factories import TenantFactory

    request = _req(
        "post",
        {"offer_name": "Doppelzimmer", "offer_price": "90", "gap_deal": "1"},
    )
    request.tenant = TenantFactory.build(
        business_type="hotel", disabled_modules=["events", "booking"]
    )
    setup_steps.create_offer(request)
    assert StayUnit.objects.filter(name="Doppelzimmer").exists()
    s = StaySettings.load()
    assert (s.gap_max_nights, s.gap_discount_percent) == (3, 25)


def test_gap_deal_banner_returns_to_calendar():
    """Ревью 2026-07-28: баннер Lücken-Deal живёт на Belegungsplan — после
    включения владелец должен вернуться туда, а не в настройки номеров."""
    back = "/dashboard/stays/?von=2026-09-01"
    resp = views.units(_req("post", {"action": "gap_deal", "enabled": "1", "next": back}))
    assert resp.status_code == 302 and resp.url == back
    # open-redirect guard: чужой хост игнорируется, работает обычный маршрут
    resp2 = views.units(
        _req("post", {"action": "gap_deal", "enabled": "1", "next": "//evil.example"})
    )
    assert resp2.url.endswith("?tab=einstellungen&sec=preise")
