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
    assert "Enter dates manually" in body  # ручной ввод — мелкий фолбэк
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
