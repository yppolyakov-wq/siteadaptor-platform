"""R5: проживание на ретрите (events ⊕ stays) — выбор типа номера, привязка, анти-овербукинг."""

from datetime import timedelta

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.events import public_views, services, views
from apps.events.models import Event, Ticket
from apps.stays import pricing
from apps.stays.models import StayBooking, StayUnit
from apps.stays.services import StayUnavailable, book_stay
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


class _User:
    is_authenticated = True
    is_active = True


def _cab(method, data=None):
    request = getattr(RequestFactory(), method)("/dashboard/events/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = _User()
    return request


def _retreat(**kw):
    """Двухдневный ретрит с проживанием и одним типом номера."""
    start = timezone.now() + timedelta(days=20)
    defaults = {
        "title": "Wochenend-Retreat",
        "starts_at": start.replace(hour=16, minute=0, second=0, microsecond=0),
        "ends_at": (start + timedelta(days=2)).replace(
            hour=12, minute=0, second=0, microsecond=0
        ),
        "status": Event.STATUS_PUBLISHED,
        "capacity": 20,
        "price_cents": 0,
        "offers_accommodation": True,
    }
    defaults.update(kw)
    return Event.objects.create(**defaults)


def _unit(**kw):
    defaults = {"name": "Doppelzimmer", "price_cents": 7000, "quantity": 1, "max_guests": 2}
    defaults.update(kw)
    return StayUnit.objects.create(**defaults)


def test_accommodation_options_lists_units_with_price():
    ev = _retreat()
    unit = _unit(price_cents=7000)
    ev.accommodation_units.set([unit])
    opts = services.accommodation_options(ev)
    assert len(opts) == 1
    assert opts[0]["unit"] == unit
    assert opts[0]["nights"] == 2
    assert opts[0]["available"] is True
    assert opts[0]["price_cents"] == pricing.quote_total_cents(
        unit, ev.starts_at.date(), ev.ends_at.date()
    )


def test_no_options_when_accommodation_off():
    ev = _retreat(offers_accommodation=False)
    ev.accommodation_units.set([_unit()])
    assert services.accommodation_options(ev) == []


def test_book_with_room_creates_linked_stay_booking():
    ev = _retreat()
    unit = _unit(price_cents=7000)
    ev.accommodation_units.set([unit])
    ticket = services.book_ticket(
        ev, name="Mara", email="m@test.de", quantity=1, stay_unit_id=str(unit.id)
    )
    expected = pricing.quote_total_cents(unit, ev.starts_at.date(), ev.ends_at.date())
    assert ticket.stay_booking is not None
    assert ticket.accommodation_cents == expected
    assert ticket.total_cents == expected  # бесплатный билет + проживание
    sb = ticket.stay_booking
    assert sb.unit == unit
    assert sb.payment_state == StayBooking.PAYMENT_NONE  # оплата через билет
    assert sb.source_channel == "retreat"
    assert sb.arrival == ev.starts_at.date() and sb.departure == ev.ends_at.date()


def test_invalid_room_selection_ignored():
    ev = _retreat()
    unit = _unit()  # НЕ привязан к событию
    ticket = services.book_ticket(
        ev, name="X", email="x@test.de", quantity=1, stay_unit_id=str(unit.id)
    )
    assert ticket.stay_booking is None and ticket.accommodation_cents == 0


def test_anti_overbooking_blocks_when_room_taken():
    ev = _retreat()
    unit = _unit(quantity=1)
    ev.accommodation_units.set([unit])
    # занять единственный номер на даты ретрита
    book_stay(
        unit,
        arrival=ev.starts_at.date(),
        departure=ev.ends_at.date(),
        name="First",
        email="f@test.de",
    )
    with pytest.raises(StayUnavailable):
        services.book_ticket(ev, name="Second", email="s@test.de", stay_unit_id=str(unit.id))
    # билет тоже не создан (вся транзакция откатилась)
    assert not Ticket.objects.filter(customer__email="s@test.de").exists()


def test_cancel_ticket_frees_room():
    ev = _retreat()
    unit = _unit(quantity=1)
    ev.accommodation_units.set([unit])
    ticket = services.book_ticket(
        ev, name="A", email="a@test.de", stay_unit_id=str(unit.id), auto_confirm=True
    )
    sb_id = ticket.stay_booking_id
    views.ticket_action(_cab("post", {"target": Ticket.STATUS_CANCELLED}), pk=ev.pk, tid=ticket.pk)
    assert StayBooking.objects.get(pk=sb_id).status == StayBooking.STATUS_CANCELLED


def test_detail_renders_room_options():
    ev = _retreat()
    ev.accommodation_units.set([_unit(name="Einzelzimmer")])
    request = RequestFactory().get("/veranstaltung/")
    request.tenant = TenantFactory.build()
    body = public_views.veranstaltung_detail(request, ev.pk).content.decode()
    assert "Einzelzimmer" in body and "stay_unit" in body


def test_form_saves_accommodation_units():
    from apps.events.forms import EventForm

    unit = _unit()
    form = EventForm(
        data={
            "title": "Retreat",
            "starts_at": "2099-01-01T16:00",
            "ends_at": "2099-01-03T12:00",
            "capacity": 20,
            "price_eur": "0",
            "offers_accommodation": "on",
            "accommodation_units": [str(unit.id)],
        }
    )
    assert form.is_valid(), form.errors
    event = form.save()
    assert event.offers_accommodation is True
    assert list(event.accommodation_units.all()) == [unit]
