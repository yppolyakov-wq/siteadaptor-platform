"""Батч B (гостевой флоу отеля, концепт 2026-07-27): даты один раз (дата-полоса
вместо третьей формы), календарь = главный селектор (checkout-only хук),
fetch-своп buy-box (?buybox=1), тарифы с «Best price» и дельтой к базовому."""

import re
import uuid
from datetime import date, timedelta

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.stays import public_views, services
from apps.stays.models import RatePlan, StayUnit
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

D0 = date(2026, 10, 1)


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _unit(**kw):
    kw.setdefault("price_cents", 9000)
    return StayUnit.objects.create(name=f"FeWo {uuid.uuid4().hex[:6]}", **kw)


def _detail(unit, params=None):
    request = RequestFactory().get(f"/unterkunft/{unit.pk}/", params or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(disabled_modules=[])
    return public_views.unterkunft_unit(request, pk=unit.pk).content.decode()


def _dates(nights=3):
    return {"von": D0.isoformat(), "bis": (D0 + timedelta(days=nights)).isoformat()}


def test_datebar_replaces_third_form_when_dates_given():
    unit = _unit()
    body = _detail(unit, _dates())
    assert "Reisedaten ändern" in body  # компактная дата-полоса
    assert re.search(r'<div id="stay-dateselect"[^>]*\bhidden\b', body)  # селектор спрятан
    assert 'id="stay-buybox"' in body  # цель fetch-свопа


def test_no_dates_calendar_first_selector():
    unit = _unit()
    body = _detail(unit)
    assert "Wählen Sie Ihre Reisedaten aus" in body
    assert 'id="stay-cal"' in body  # календарь — главный селектор
    assert (
        "Zeitraum manuell eingeben" in body
    )  # ручной ввод — мелкий фолбэк (I18N-12: строка переведена на de)
    assert 'name="von"' in body  # контракт селектора цел (паритет-замок)
    assert not re.search(r'<div id="stay-dateselect"[^>]*\bhidden\b', body)  # виден


def test_buybox_fragment_mode():
    unit = _unit()
    body = _detail(unit, {**_dates(), "buybox": "1"})
    assert f"/unterkunft/{unit.pk}/buchen/" in body  # POST-форма во фрагменте
    assert "<html" not in body and "detail_gallery" not in body  # только фрагмент
    assert 'id="stay-buybox"' not in body  # обёртка живёт на детали, не во фрагменте


def test_rate_cards_best_price_and_delta():
    unit = _unit(price_cents=10000)
    RatePlan.objects.create(name="Basistarif", sort_order=1)
    RatePlan.objects.create(
        name="Mit Frühstück", surcharge_cents=1200, meal_plan=RatePlan.MEAL_BREAKFAST, sort_order=2
    )
    RatePlan.objects.create(
        name="Sparpreis",
        percent_adjust=-10,
        cancellation=RatePlan.CANCEL_NONREF,
        sort_order=3,
    )
    body = _detail(unit, _dates())
    assert "Bestpreis" in body  # метка на самом дешёвом (Sparpreis)
    assert re.search(r"\+\s*36[.,]00\s*€", body)  # дельта завтрака: 12 € × 3 ночи


def test_busy_calendar_day_carries_date_hook():
    unit = _unit()
    services.book_stay(
        unit, arrival=D0 + timedelta(days=5), departure=D0 + timedelta(days=8), name="G"
    )
    # даты в октябре → календарь открывается на октябрь; занятая ночь 06.10 —
    # НЕ кнопка, но несёт data-date (кандидат в выезд, checkout-only).
    body = _detail(unit, _dates())
    busy_day = (D0 + timedelta(days=5)).isoformat()
    assert re.search(rf'stay-cal-busy[^>]*data-date="{busy_day}"', body)


def test_calendar_starts_at_first_month_with_selectable_days():
    """HF-0 (#12): без дат календарь открывается на месяце, где есть ЧТО выбрать.

    Раньше показывался текущий месяц всегда — 31-го числа это один кликабельный
    день, и «выбор нескольких дат не работает» (жалоба владельца с телефона)."""
    from datetime import date as _date

    from django.utils import timezone

    unit = _unit(quantity=1)
    today = timezone.localdate()
    # Занимаем остаток текущего месяца — свободных дней в нём не остаётся.
    m = today.month
    next_first = _date(today.year + m // 12, m % 12 + 1, 1)
    services.book_stay(
        unit=unit,
        arrival=today,
        departure=next_first,
        name="Dauergast",
        email="dauer@example.com",
    )
    ctx_first, days = public_views._calendar_start(unit, None, today)
    assert ctx_first == next_first  # перелистнули вперёд сами
    assert sum(1 for d in days if d["is_free"]) >= 2  # и там реально есть выбор
    # С явной датой заезда поведение прежнее — месяц заезда (паритет).
    later = next_first.replace(day=15)
    assert public_views._calendar_start(unit, later, today)[0] == next_first


def test_fully_booked_month_says_so():
    """HF-0: полностью занятый месяц объясняется словами, а не пустой сеткой."""
    from datetime import date as _date

    from django.utils import timezone

    unit = _unit(quantity=1)
    today = timezone.localdate()
    m = today.month
    next_first = _date(today.year + m // 12, m % 12 + 1, 1)
    services.book_stay(
        unit=unit,
        arrival=today,
        departure=next_first,
        name="Dauergast",
        email="dauer2@example.com",
    )
    ctx = public_views._calendar_context(unit, today.replace(day=1), today)
    assert ctx["cal_free_count"] == 0


def test_card_amenities_default_and_owner_choice():
    """HF-2 (#5): пиктограммы удобств на карточке номера.

    Дефолт — первые удобства самого номера; выбор владельца ОГРАНИЧИВАЕТ набор,
    но никогда не дописывает то, чего в номере нет (иначе карточка врала бы)."""
    unit = _unit(amenities=["wifi", "tv", "balcony", "parking", "safe"])
    keys = [icon for _label, icon in unit.card_amenity_badges()]
    assert len(keys) == 4  # дефолтный лимит карточки

    chosen = [label for label, _icon in unit.card_amenity_badges(only=["wifi", "aircon"])]
    assert len(chosen) == 1  # aircon в номере нет — не показываем
    assert unit.card_amenity_badges(only=["aircon"]) == []


def test_normalize_card_amenities_validates_against_registry():
    from apps.tenants import siteconfig

    assert siteconfig.normalize_card_amenities(["tv", "wifi"]) == ["wifi", "tv"]  # порядок реестра
    assert siteconfig.normalize_card_amenities(["nope", 5, None]) == []  # мусор отброшен
    assert siteconfig.normalize_card_amenities("wifi") == []  # не список
    # Ключ не материализуется при пустом выборе — golden-паритет normalize.
    assert "stay_card_amenities" not in siteconfig.normalize({})
    assert siteconfig.normalize({"stay_card_amenities": ["wifi"]})["stay_card_amenities"] == [
        "wifi"
    ]
