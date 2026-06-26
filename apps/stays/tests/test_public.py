"""Track E / E3: публичная витрина /unterkunft/ — выбор дат, цена, бронь,
гейтинг модуля, ре-валидация занятости."""

import uuid
from datetime import date, timedelta

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory

from apps.notifications.models import Notification
from apps.stays import public_views, services
from apps.stays.models import StayBooking, StayUnit
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

D0 = date(2026, 10, 1)  # в будущем относительно «сегодня» сессии


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(**kwargs):
    kwargs.setdefault("disabled_modules", [])  # stays активен
    return TenantFactory.build(**kwargs)


def _req(method="get", path="/unterkunft/", data=None, tenant=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant if tenant is not None else _tenant()
    return request


def _unit(**kwargs):
    kwargs.setdefault("price_cents", 9000)
    return StayUnit.objects.create(name=f"FeWo {uuid.uuid4().hex[:6]}", **kwargs)


def _iso(off):
    return (D0 + timedelta(days=off)).isoformat()


# --- гейтинг ----------------------------------------------------------------------


# --- гейтинг ----------------------------------------------------------------------


def test_gating_404_when_module_inactive():
    request = _req(tenant=_tenant(disabled_modules=["stays"]))
    with pytest.raises(Http404):
        public_views.unterkunft_index(request)


def test_home_stay_rooms_section_shows_book_action():
    """M20U-5: карточки номеров на главной несут действие брони (stays → «Jetzt buchen»)."""
    from apps.promotions import public_views as promo_views

    unit = _unit()
    request = _req("get", "/")
    request.tenant.site_config = {"sections": [{"key": "stay_rooms", "enabled": True}]}
    body = promo_views.storefront_home(request).content.decode()
    assert unit.name in body
    assert "Jetzt buchen" in body and "data-purchase-action" in body


# --- витрина: цена + бронь --------------------------------------------------------


def test_detail_shows_price_and_book_form():
    unit = _unit(price_cents=9000)
    request = _req(
        "get", f"/unterkunft/{unit.pk}/", {"von": _iso(0), "bis": _iso(3), "gaeste": "2"}
    )
    body = public_views.unterkunft_unit(request, pk=unit.pk).content.decode()
    # доступный диапазон → отрисована форма брони (action стабилен, не зависит от локали)
    assert f"/unterkunft/{unit.pk}/buchen/" in body
    assert "270" in body  # итог 3 × 90 € (разделитель — по локали, de → запятая)
    # M20U-4: мобильная липкая панель брони (цена + действие) + якорь
    assert "data-buybar" in body and "Jetzt buchen" in body
    assert 'id="buchen"' in body
    # наследует единый каркас detail.html
    assert "max-w-5xl" in body and "lg:grid-cols-2" in body


def test_detail_shows_pangv_price_breakdown():
    """A5/PAngV: на странице номера — разбивка Gesamtpreis (Nachtpreis × Nächte) + MwSt."""
    unit = _unit(price_cents=9000)
    request = _req(
        "get", f"/unterkunft/{unit.pk}/", {"von": _iso(0), "bis": _iso(3), "gaeste": "2"}
    )
    body = public_views.unterkunft_unit(request, pk=unit.pk).content.decode()
    assert "90,00 € ×" in body  # Nachtpreis × …
    assert "= 270,00 €" in body  # Übernachtung-подытог (3 × 90)
    assert "incl. VAT" in body or "MwSt" in body  # PAngV-Hinweis «inkl. MwSt.»


def test_detail_shows_business_rating_badge():
    """A5: на странице номера — рейтинг бизнеса (★ среднее + число отзывов)."""
    from django.db import connection

    from apps.aggregator.models import BusinessRating

    BusinessRating.objects.update_or_create(
        tenant_schema=connection.schema_name,
        defaults={"avg_rating": "4.50", "review_count": 12},
    )
    unit = _unit()
    request = _req("get", f"/unterkunft/{unit.pk}/")
    body = public_views.unterkunft_unit(request, pk=unit.pk).content.decode()
    assert "4,5" in body  # среднее (de-локаль, запятая)
    assert "12" in body and "★" in body  # число отзывов + звезда


def test_detail_min_nights_message():
    unit = _unit(min_nights=3)
    request = _req("get", f"/unterkunft/{unit.pk}/", {"von": _iso(0), "bis": _iso(1)})
    body = public_views.unterkunft_unit(request, pk=unit.pk).content.decode()
    # ниже минимума ночей → формы брони нет (показано сообщение)
    assert f"/unterkunft/{unit.pk}/buchen/" not in body


def test_book_creates_pending_and_email():
    unit = _unit()
    request = _req(
        "post",
        f"/unterkunft/{unit.pk}/buchen/",
        {"von": _iso(0), "bis": _iso(3), "gaeste": "2", "name": "Gast", "email": "g@t.de"},
    )
    resp = public_views.unterkunft_book(request, pk=unit.pk)
    assert resp.status_code == 302
    booking = StayBooking.objects.get(unit=unit)
    assert booking.status == "pending" and booking.nights == 3
    assert resp.url == f"/s/{booking.reference_code}/"
    assert Notification.objects.filter(dedupe_key=f"stay:{booking.id}:created:customer").exists()


def test_book_rejects_occupied_range():
    unit = _unit()
    services.book_stay(unit, arrival=D0, departure=D0 + timedelta(days=3), name="A")
    request = _req(
        "post",
        f"/unterkunft/{unit.pk}/buchen/",
        {"von": _iso(1), "bis": _iso(2), "name": "B", "email": "b@t.de"},
    )
    public_views.unterkunft_book(request, pk=unit.pk)
    assert StayBooking.objects.filter(unit=unit).count() == 1  # второй не создан


def test_book_requires_name():
    unit = _unit()
    request = _req(
        "post", f"/unterkunft/{unit.pk}/buchen/", {"von": _iso(0), "bis": _iso(2), "name": ""}
    )
    public_views.unterkunft_book(request, pk=unit.pk)
    assert not StayBooking.objects.filter(unit=unit).exists()


def test_single_unit_index_redirects_to_detail():
    unit = _unit()
    resp = public_views.unterkunft_index(_req())
    assert resp.status_code == 302 and str(unit.pk) in resp.url


def test_rooms_index_grid_from_config():
    """M20U-7 (per-page): сетка номеров берётся из stay_index_layout."""
    _unit()
    _unit()  # >1 юнит → обзорная сетка (без редиректа)
    req = _req()
    req.tenant.site_config = {"stay_index_layout": {"preset": "cols4"}}
    body = public_views.unterkunft_index(req).content.decode()
    assert "lg:grid-cols-4" in body


# --- H2: поиск по датам на /unterkunft/ -------------------------------------------


def test_index_search_lists_available_with_total_price():
    free = _unit(price_cents=9000)
    busy = _unit(price_cents=8000)
    services.book_stay(busy, arrival=D0, departure=D0 + timedelta(days=3), name="A")
    request = _req("get", "/unterkunft/", {"von": _iso(0), "bis": _iso(3), "gaeste": "2"})
    body = public_views.unterkunft_index(request).content.decode()
    # свободный юнит — со ссылкой-диалплинком (даты прокинуты) и итогом 3×90 = 270
    assert f"/unterkunft/{free.pk}/?von={_iso(0)}" in body
    assert "270" in body


def test_index_search_single_unit_does_not_redirect():
    # с датами даже один юнит остаётся на странице результатов (не редирект)
    _unit()
    resp = public_views.unterkunft_index(
        _req("get", "/unterkunft/", {"von": _iso(0), "bis": _iso(3)})
    )
    assert resp.status_code == 200


def test_ical_export_returns_calendar():
    unit = _unit()
    services.book_stay(unit, arrival=D0, departure=D0 + timedelta(days=3), name="A")
    token = public_views.ical_token(unit)
    resp = public_views.unterkunft_ical(_req(path=f"/stays/ical/{token}.ics"), token=token)
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/calendar")
    assert b"BEGIN:VCALENDAR" in resp.content


def test_ical_export_rejects_bad_token():
    request = _req(path="/stays/ical/bogus.ics")
    with pytest.raises(Http404):
        public_views.unterkunft_ical(request, token="bogus")


# --- A5/C2: визуальный календарь наличия ------------------------------------


def _cal(unit, year, month, tenant=None):
    req = _req(
        "get",
        f"/unterkunft/{unit.pk}/kalender/",
        {"year": str(year), "month": str(month)},
        tenant,
    )
    return public_views.unterkunft_unit_calendar(req, pk=unit.pk).content.decode()


def test_calendar_renders_month_grid():
    unit = _unit()
    body = _cal(unit, 2026, 10)  # будущий месяц (D0)
    assert 'id="stay-cal"' in body
    assert "grid-cols-7" in body  # сетка недели
    assert 'data-date="2026-10-15"' in body  # свободный день месяца отрисован/кликабелен


def test_calendar_gate_404_without_stays():
    unit = _unit()
    req = _req(
        "get",
        f"/unterkunft/{unit.pk}/kalender/",
        tenant=_tenant(disabled_modules=["stays"]),
    )
    with pytest.raises(Http404):
        public_views.unterkunft_unit_calendar(req, pk=unit.pk)


def test_calendar_marks_booked_and_free_days():
    unit = _unit(quantity=1)
    # бронь 1–4 окт → ночи 1,2,3 заняты; 4 (выезд) и 5 свободны
    services.book_stay(unit, arrival=D0, departure=D0 + timedelta(days=3), name="A", adults=2)
    body = _cal(unit, 2026, 10)
    assert 'data-date="2026-10-05"' in body  # свободный день — кликабелен
    assert 'data-date="2026-10-02"' not in body  # занятая ночь — не кликабельна


def test_calendar_month_navigation_links():
    unit = _unit()
    body = _cal(unit, 2026, 10)
    assert "month=11" in body  # переход на следующий месяц
    assert "month=9" in body  # и на предыдущий


def test_calendar_clamps_past_month_to_current():
    unit = _unit()
    body = _cal(unit, 2000, 1)  # запрос месяца в прошлом → кламп к текущему
    # на текущем месяце кнопки «назад» нет (не уходим в прошлое)
    assert "Previous month" not in body


def test_detail_embeds_availability_calendar():
    """A5/C3: страница номера встраивает календарь + логику выбора диапазона."""
    unit = _unit()
    req = _req("get", f"/unterkunft/{unit.pk}/", {"von": _iso(0), "bis": _iso(3), "gaeste": "2"})
    body = public_views.unterkunft_unit(req, pk=unit.pk).content.decode()
    assert 'id="stay-cal"' in body  # календарь встроен
    assert "stay-cal-day" in body  # кликабельные свободные ночи
    assert "__stayCalSelectBound" in body  # выбор диапазона кликом
    assert 'data-date="2026-10-' in body  # начальный месяц = месяц заезда (D0)
