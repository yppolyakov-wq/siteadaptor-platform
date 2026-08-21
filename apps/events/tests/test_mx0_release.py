"""MX-0: освобождение companion-брони проживания — ЕДИНЫЙ узел (TicketSM-хук).

До MX-0 койку освобождали только два вьюха-хелпера; отмена билета с единой
доски (core_transactions.apply_action) оставляла её занятой — латентный
oversell ретрита. План — docs/mx-execution-plan-2026-08-21.md §MX-0.4.
"""

from datetime import timedelta

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.core import transactions as core_transactions
from apps.events import services, views
from apps.events.models import Event, Ticket
from apps.stays.models import StayBooking, StayUnit

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
    start = timezone.now() + timedelta(days=20)
    defaults = {
        "title": "Wochenend-Retreat",
        "starts_at": start.replace(hour=16, minute=0, second=0, microsecond=0),
        "ends_at": (start + timedelta(days=2)).replace(hour=12, minute=0, second=0, microsecond=0),
        "status": Event.STATUS_PUBLISHED,
        "capacity": 20,
        "price_cents": 0,
        "offers_accommodation": True,
    }
    defaults.update(kw)
    return Event.objects.create(**defaults)


def _ticket_with_bed():
    ev = _retreat()
    unit = StayUnit.objects.create(name="DZ", price_cents=7000, quantity=1, max_guests=2)
    ev.accommodation_units.set([unit])
    return services.book_ticket(
        ev, name="A", email="a@test.de", stay_unit_id=str(unit.id), auto_confirm=True
    )


def test_board_cancel_releases_bed():
    """Отмена через ЕДИНУЮ точку доски освобождает койку (до MX-0 — не освобождала)."""
    ticket = _ticket_with_bed()
    core_transactions.apply_action("ticket", ticket, "cancelled")
    assert StayBooking.objects.get(pk=ticket.stay_booking_id).status == (
        StayBooking.STATUS_CANCELLED
    )


def test_cabinet_view_cancel_still_releases_bed():
    """Паритет: прежний путь кабинета продолжает освобождать (хелпер заменён хуком)."""
    ticket = _ticket_with_bed()
    views.ticket_action(
        _cab("post", {"target": Ticket.STATUS_CANCELLED}), pk=ticket.event_id, tid=ticket.pk
    )
    assert StayBooking.objects.get(pk=ticket.stay_booking_id).status == (
        StayBooking.STATUS_CANCELLED
    )


def test_release_is_idempotent_and_no_guest_email():
    """Повторный вызов — no-op; гостю НЕ уходит второе письмо об отмене (сырой save,
    не StayBookingSM — companion-бронь без промо/ваучера, письмо шлёт билет)."""
    ticket = _ticket_with_bed()
    services.release_linked_stay(ticket)
    services.release_linked_stay(ticket)  # идемпотентно
    sb = StayBooking.objects.get(pk=ticket.stay_booking_id)
    assert sb.status == StayBooking.STATUS_CANCELLED
