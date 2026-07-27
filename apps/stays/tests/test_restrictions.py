"""G12: правила продаж («Verkaufsregeln») — резолвер, витринный гейт, кабинет.

Ключевые замки: ограничения действуют ТОЛЬКО на витрине (unterkunft_book/_quote);
кабинетная ручная бронь (stay_create) правила игнорирует — walk-in главнее."""

import uuid
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.stays import public_views, restrictions, views
from apps.stays.models import StayBooking, StaySettings, StayUnit
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

TODAY = date(2026, 9, 1)  # вторник (weekday=1)


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _unit(**kw):
    kw.setdefault("price_cents", 9000)
    return StayUnit.objects.create(name=f"Zimmer {uuid.uuid4().hex[:6]}", **kw)


def _settings(**kw):
    obj = StaySettings.load()
    for k, v in kw.items():
        setattr(obj, k, v)
    obj.save()
    return obj


def _rule(**kw):
    base = {
        "start": "",
        "end": "",
        "unit": "",
        "min_nights": 0,
        "max_nights": 0,
        "no_checkin": [],
        "no_checkout": [],
    }
    base.update(kw)
    return base


def _v(unit, arr_off, dep_off):
    return restrictions.violation(
        unit,
        TODAY + timedelta(days=arr_off),
        TODAY + timedelta(days=dep_off),
        today=TODAY,
    )


# --- резолвер -----------------------------------------------------------------


def test_booking_window_and_lead():
    unit = _unit()
    _settings(max_advance_days=30, min_advance_days=3)
    assert _v(unit, 40, 43) == ("window", 30)  # глубже окна
    assert _v(unit, 1, 4) == ("lead", 3)  # раньше мин. срока
    assert _v(unit, 5, 8) is None  # внутри окна


def test_seasonal_min_stay_matches_by_arrival():
    unit = _unit()
    season = _rule(start="2026-09-10", end="2026-09-20", min_nights=3)
    _settings(restriction_rules=[season])
    assert _v(unit, 10, 12) == ("rule_min_nights", 3)  # заезд в сезоне, 2 ночи
    assert _v(unit, 10, 13) is None  # 3 ночи — ок
    assert _v(unit, 2, 4) is None  # заезд ВНЕ периода — правило не применяется


def test_max_nights_and_strictest_of_two_rules():
    unit = _unit()
    _settings(restriction_rules=[_rule(min_nights=3, max_nights=14), _rule(min_nights=5)])
    assert _v(unit, 5, 8) == ("rule_min_nights", 5)  # строже из двух минимумов
    assert _v(unit, 5, 25) == ("rule_max_nights", 14)
    assert _v(unit, 5, 12) is None


def test_no_checkin_no_checkout_weekdays():
    unit = _unit()
    # TODAY=вт(1); заезд сб — TODAY+4 (weekday 5); выезд вс — weekday 6.
    _settings(restriction_rules=[_rule(no_checkin=[5])])
    assert _v(unit, 4, 7) == ("no_checkin", None)  # заезд в субботу запрещён
    assert _v(unit, 5, 8) is None  # заезд вс — можно
    _settings(restriction_rules=[_rule(no_checkout=[6])])
    assert _v(unit, 2, 4) is None  # выезд сб (TODAY+4) — можно
    assert _v(unit, 2, 5) == ("no_checkout", None)  # выезд вс (TODAY+5) запрещён


def test_unit_scope():
    a, b = _unit(), _unit()
    _settings(restriction_rules=[_rule(unit=str(a.pk), min_nights=5)])
    assert _v(a, 5, 7) == ("rule_min_nights", 5)
    assert _v(b, 5, 7) is None  # правило скоупнуто на a


def test_clean_rules_drops_empty_and_garbage():
    obj = _settings(
        restriction_rules=[
            _rule(),  # пустое (ничего не ограничивает) — выбрасывается
            {"min_nights": "x"},  # мусор
            "not-a-dict",
            _rule(min_nights=2, no_checkin=[9, 3]),  # 9 — вне диапазона
        ]
    )
    cleaned = obj.clean_restriction_rules()
    assert len(cleaned) == 1
    assert cleaned[0]["min_nights"] == 2 and cleaned[0]["no_checkin"] == [3]


# --- витринный гейт -----------------------------------------------------------


def _req(method="get", path="/unterkunft/", data=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.7"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(disabled_modules=[])
    return request


def test_quote_carries_restriction_code_and_n():
    unit = _unit()
    _settings(restriction_rules=[_rule(min_nights=4)])
    day = TODAY + timedelta(days=400)  # далеко — но окно не задано
    nights, total, available, reason, reason_n = public_views._quote(
        unit, day, day + timedelta(days=2), 2
    )
    assert not available and reason == "rule_min_nights" and reason_n == 4


def test_unterkunft_book_blocked_but_cabinet_walkin_allowed():
    unit = _unit()
    _settings(restriction_rules=[_rule(min_nights=4)])
    von = TODAY + timedelta(days=300)
    bis = von + timedelta(days=2)
    resp = public_views.unterkunft_book(
        _req(
            "post",
            path=f"/unterkunft/{unit.pk}/buchen/",
            data={
                "von": von.isoformat(),
                "bis": bis.isoformat(),
                "erw": "2",
                "name": "Gast",
            },
        ),
        pk=unit.pk,
    )
    assert resp.status_code == 302
    assert not StayBooking.objects.exists()  # витрина отфутболила

    # Кабинет (walk-in) — те же даты проходят: правила НЕ гейтят владельца.
    owner = uuid.uuid4().hex[:8]
    request = RequestFactory().post(
        "/dashboard/stays/neu/",
        {
            "unit": str(unit.pk),
            "arrival": von.isoformat(),
            "departure": bis.isoformat(),
            "name": "Telefonbuchung",
        },
    )
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
    )
    views.stay_create(request)
    assert StayBooking.objects.count() == 1


def test_detail_shows_restriction_reason():
    unit = _unit()
    _settings(restriction_rules=[_rule(min_nights=4)])
    von = TODAY + timedelta(days=300)
    body = public_views.unterkunft_unit(
        _req(
            path=f"/unterkunft/{unit.pk}/",
            data={"von": von.isoformat(), "bis": (von + timedelta(days=2)).isoformat()},
        ),
        pk=unit.pk,
    ).content.decode()
    assert "at least 4 nights" in body  # причина в buybox-фолбэке


def test_max_date_respects_booking_window():
    unit = _unit()
    _settings(max_advance_days=30)
    body = public_views.unterkunft_unit(
        _req(path=f"/unterkunft/{unit.pk}/"), pk=unit.pk
    ).content.decode()
    from django.utils import timezone

    cap = (timezone.localdate() + timedelta(days=30)).isoformat()
    assert f'max="{cap}"' in body  # date-инпуты ограничены окном


# --- кабинет: actions ---------------------------------------------------------


def _owner_req(data):
    request = RequestFactory().post("/dashboard/stays/units/", data)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
    )
    return request


def test_units_actions_add_delete_and_window():
    unit = _unit()
    views.units(
        _owner_req(
            {
                "action": "restriction_add",
                "start": "2026-12-20",
                "end": "2027-01-05",
                "unit": str(unit.pk),
                "min_nights": "3",
                "no_checkin": ["4", "5"],
            }
        )
    )
    rules = StaySettings.load().clean_restriction_rules()
    assert len(rules) == 1
    assert rules[0]["min_nights"] == 3 and rules[0]["no_checkin"] == [4, 5]
    assert rules[0]["unit"] == str(unit.pk)

    views.units(_owner_req({"action": "restriction_add", "min_nights": "0"}))  # пустое
    assert len(StaySettings.load().clean_restriction_rules()) == 1  # не добавилось

    views.units(
        _owner_req({"action": "booking_window", "max_advance_days": "60", "min_advance_days": "2"})
    )
    obj = StaySettings.load()
    assert obj.max_advance_days == 60 and obj.min_advance_days == 2

    views.units(_owner_req({"action": "restriction_delete", "index": "0"}))
    assert StaySettings.load().clean_restriction_rules() == []
