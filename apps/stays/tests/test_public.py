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
