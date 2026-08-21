"""MX-3: правка состава доп-услуг из карточки брони/записи (кабинет).

Владелец: «опции можно добавить или удалить при оформлении И ДАЛЕЕ ПРИ
РЕДАКТИРОВАНИИ». До MX-3 состав допов не редактировался нигде (разведка OPT-2/3).
"""

import uuid
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.core import extras as extras_engine
from apps.core.models import Extra
from apps.stays import services, views
from apps.stays.models import StayBooking, StayUnit

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(data):
    request = RequestFactory().post("/dashboard/stays/x/action/", data)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    n = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{n}", email=f"o-{n}@test.de", password="pw12345678"
    )
    return request


def _booking(extras=None):
    unit = StayUnit.objects.create(
        name=f"Z {uuid.uuid4().hex[:6]}", price_cents=10000, quantity=1, max_guests=4
    )
    arrival = timezone.localdate() + timedelta(days=10)
    b = services.book_stay(
        unit,
        arrival=arrival,
        departure=arrival + timedelta(days=2),
        name="G",
        extras=extras,
        adults=1,
    )
    return unit, b


def _update(b, **extra_post):
    data = {
        "action": "update",
        "arrival": b.arrival.isoformat(),
        "departure": b.departure.isoformat(),
        "adults": str(b.adults),
        "children": str(b.children),
        "note": "",
        **extra_post,
    }
    return views.stay_action(_req(data), pk=b.pk)


def test_add_extra_via_edit_recomputes_total():
    unit, b = _booking()
    breakfast = Extra.objects.create(
        label="Frühstück", price_cents=1500, scope=Extra.SCOPE_STAYS, per_night=True
    )
    assert b.total_cents == 20000
    _update(b, extras_present="1", extra=[str(breakfast.pk)])
    b.refresh_from_db()
    assert extras_engine.total_cents(b.extras) == 3000  # 2 ночи × 15 €
    assert b.total_cents == 23000  # состав изменился → пересчёт принудительный


def test_remove_extra_via_edit():
    breakfast = Extra.objects.create(
        label="Frühstück", price_cents=1500, scope=Extra.SCOPE_STAYS, per_night=True
    )
    snap = extras_engine.snapshot([breakfast.pk], "stays", nights=2)
    unit, b = _booking(extras=snap)
    assert b.total_cents == 23000
    _update(b, extras_present="1")  # чекбоксы сняты
    b.refresh_from_db()
    assert b.extras == [] and b.total_cents == 20000


def test_form_without_sentinel_keeps_extras():
    """Инвариант W0: форма без блока допов ничего не стирает."""
    breakfast = Extra.objects.create(
        label="Frühstück", price_cents=1500, scope=Extra.SCOPE_STAYS, per_night=True
    )
    snap = extras_engine.snapshot([breakfast.pk], "stays", nights=2)
    unit, b = _booking(extras=snap)
    _update(b)  # без extras_present
    b.refresh_from_db()
    assert extras_engine.total_cents(b.extras) == 3000


def test_paid_booking_change_warns_delta():
    breakfast = Extra.objects.create(
        label="Frühstück", price_cents=1500, scope=Extra.SCOPE_STAYS, per_night=True
    )
    unit, b = _booking()
    b.payment_state = StayBooking.PAYMENT_PAID
    b.save(update_fields=["payment_state"])
    resp = _update(b, extras_present="1", extra=[str(breakfast.pk)])
    assert resp.status_code == 302
    b.refresh_from_db()
    assert b.total_cents == 23000  # пересчитан; дельту показывает warning-сообщение
