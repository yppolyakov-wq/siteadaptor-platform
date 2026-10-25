"""KA-12 Zimmer Z-5a (Р-8): часы заезда/выезда — настройка StaySettings.

Замки: без строки настроек автоматика ведёт себя как прежде (14:00) и строку НЕ
создаёт (beat ежечасно идёт по всем схемам); заданный час сдвигает момент
авто-выезда; правят только owner/admin; мусор/«²»/«٣»/24 — без 500 и без записи."""

import datetime as dt
import uuid
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.core.models import Membership
from apps.core.tests.dates import future_month_start
from apps.stays import services, tasks, views
from apps.stays.models import StayBooking, StaySettings, StayUnit
from apps.stays.state_machine import StayBookingSM
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

D0 = future_month_start()


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _leaving_today():
    unit = StayUnit.objects.create(name=f"Z {uuid.uuid4().hex[:6]}", price_cents=8000)
    booking = services.book_stay(
        unit, arrival=D0 - timedelta(days=2), departure=D0, name="Gast Abreise"
    )
    StayBookingSM().apply(booking, "confirmed")
    return booking


def _at(hour, minute=0):
    return timezone.make_aware(dt.datetime.combine(D0, dt.time(hour, minute)))


def test_default_hours_without_row_and_no_row_created():
    assert StaySettings.hours() == (15, 14)
    booking = _leaving_today()
    StaySettings.objects.all().delete()  # book_stay мог прочитать load()
    assert tasks.auto_fulfil_departed(today=D0, now=_at(13, 59)) == 0
    assert tasks.auto_fulfil_departed(today=D0, now=_at(14, 0)) == 1
    assert StaySettings.objects.count() == 0  # beat только читает
    booking.refresh_from_db()
    assert booking.status == StayBooking.STATUS_FULFILLED
    assert booking.checked_out_at is None  # автоматика факт выезда не «подтверждает»


def test_owner_checkout_hour_moves_auto_checkout():
    settings_obj = StaySettings.load()
    settings_obj.checkout_hour = 11
    settings_obj.save()
    _leaving_today()
    assert tasks.auto_fulfil_departed(today=D0, now=_at(10, 59)) == 0
    assert tasks.auto_fulfil_departed(today=D0, now=_at(11, 0)) == 1


def test_next_day_closes_regardless_of_hour():
    settings_obj = StaySettings.load()
    settings_obj.checkout_hour = 23
    settings_obj.save()
    _leaving_today()
    nxt = timezone.make_aware(dt.datetime.combine(D0 + timedelta(days=1), dt.time(0, 5)))
    assert tasks.auto_fulfil_departed(today=D0, now=nxt) == 1


def _user(role):
    tag = uuid.uuid4().hex[:8]
    user = get_user_model().objects.create_user(
        username=f"u-{tag}", email=f"u-{tag}@test.de", password="pw12345678"
    )
    Membership.objects.get_or_create(user=user, defaults={"role": role})
    return user


def _post(data, role=Membership.ROLE_OWNER):
    request = RequestFactory().post("/dashboard/stays/units/", {"action": "stay_hours", **data})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = _user(role)
    request.tenant = TenantFactory.build(disabled_modules=[])
    response = views.units(request)
    return request, response


def test_owner_saves_hours():
    _post({"checkin_hour": "16", "checkout_hour": "10"})
    assert StaySettings.hours() == (16, 10)


def test_staff_cannot_change_hours():
    request, _ = _post({"checkin_hour": "16", "checkout_hour": "10"}, role=Membership.ROLE_STAFF)
    assert StaySettings.hours() == (15, 14)
    assert any("Inhaber" in str(m) for m in get_messages(request))


@pytest.mark.parametrize("bad", ["24", "x", "²", "٣", "-1", "", "1.5", "007"])
def test_garbage_hour_is_refused_without_500(bad):
    settings_obj = StaySettings.load()
    settings_obj.checkout_hour = 12
    settings_obj.save()
    request, response = _post({"checkin_hour": "15", "checkout_hour": bad})
    assert response.status_code == 302
    assert StaySettings.hours() == (15, 12)


def test_units_page_shows_hour_form_only_to_price_editors():
    def _body(role):
        request = RequestFactory().get("/dashboard/stays/units/?tab=einstellungen&sec=kurtaxe")
        SessionMiddleware(lambda r: None).process_request(request)
        MessageMiddleware(lambda r: None).process_request(request)
        request.user = _user(role)
        request.tenant = TenantFactory.build(disabled_modules=[])
        return views.units(request).content.decode()

    assert 'value="stay_hours"' in _body(Membership.ROLE_OWNER)
    assert 'value="stay_hours"' not in _body(Membership.ROLE_STAFF)
