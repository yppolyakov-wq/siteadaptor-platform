"""R12: гибкая политика отмены билета — окна возврата + самостоятельная отмена.

`cancellation_state(ticket)` зеркалит stays: flexible до `free_cancel_days` дней
до начала = free; non_refundable = отмена без возврата; attended/cancelled нельзя.
Самоотмена по подписанной ссылке освобождает место и (при free + онлайн-оплате)
возвращает деньги.
"""

from datetime import timedelta

import pytest
from django.test import RequestFactory
from django.utils import timezone

from apps.events import public_views, services
from apps.events.models import Event, Ticket
from apps.events.services import book_ticket
from apps.events.state_machine import TicketSM

pytestmark = pytest.mark.django_db


def _event(**kw):
    defaults = {
        "title": "Yoga-Retreat",
        "starts_at": timezone.now() + timedelta(days=30),
        "status": Event.STATUS_PUBLISHED,
        "price_cents": 9900,
        "capacity": 10,
    }
    defaults.update(kw)
    return Event.objects.create(**defaults)


# --- cancellation_state -------------------------------------------------------


def test_flexible_free_before_deadline():
    event = _event(cancellation=Event.CANCEL_FLEXIBLE, free_cancel_days=7)
    ticket = book_ticket(event, name="A", email="a@test.de")
    state = services.cancellation_state(ticket)
    assert state["can_cancel"] is True and state["free"] is True


def test_flexible_not_free_inside_deadline():
    event = _event(
        starts_at=timezone.now() + timedelta(days=3),
        cancellation=Event.CANCEL_FLEXIBLE,
        free_cancel_days=7,  # дедлайн уже прошёл (до начала 3 дня < 7)
    )
    ticket = book_ticket(event, name="A", email="a@test.de")
    state = services.cancellation_state(ticket)
    assert state["can_cancel"] is True and state["free"] is False


def test_non_refundable_cancellable_but_not_free():
    event = _event(cancellation=Event.CANCEL_NONREF)
    ticket = book_ticket(event, name="A", email="a@test.de")
    state = services.cancellation_state(ticket)
    assert state["can_cancel"] is True and state["free"] is False
    assert state["deadline"] is None


def test_cancelled_ticket_not_cancellable():
    event = _event()
    ticket = book_ticket(event, name="A", email="a@test.de")
    TicketSM().apply(ticket, Ticket.STATUS_CANCELLED)
    assert services.cancellation_state(ticket)["can_cancel"] is False


def test_attended_ticket_not_cancellable():
    event = _event()
    ticket = book_ticket(event, name="A", email="a@test.de", auto_confirm=True)
    TicketSM().apply(ticket, Ticket.STATUS_ATTENDED)
    assert services.cancellation_state(ticket)["can_cancel"] is False


def test_default_event_is_flexible():
    event = _event()
    assert event.cancellation == Event.CANCEL_FLEXIBLE
    assert event.is_refundable is True


# --- self-service cancel view -------------------------------------------------


def _req(method="get"):
    rf = RequestFactory()
    req = getattr(rf, method)("/")
    req.tenant = _Tenant()
    # messages framework на запросе
    from django.contrib.messages.storage.fallback import FallbackStorage

    req.session = {}
    req._messages = FallbackStorage(req)
    return req


class _Tenant:
    stripe_connect_id = ""

    def is_module_active(self, name):
        return True


def test_cancel_token_roundtrip():
    event = _event()
    ticket = book_ticket(event, name="A", email="a@test.de")
    token = public_views.cancel_token(ticket)
    from django.core import signing

    assert signing.loads(token, salt=public_views._CANCEL_SALT) == str(ticket.pk)


def test_cancel_view_post_cancels_ticket_and_frees_seat():
    event = _event(capacity=1, cancellation=Event.CANCEL_FLEXIBLE, free_cancel_days=7)
    ticket = book_ticket(event, name="A", email="a@test.de")
    assert event.is_sold_out is True
    token = public_views.cancel_token(ticket)
    public_views.veranstaltung_cancel(_req("post"), token)
    ticket.refresh_from_db()
    assert ticket.status == Ticket.STATUS_CANCELLED
    assert event.seats_sold == 0  # место освобождено


def test_cancel_view_bad_token_404():
    from django.http import Http404

    with pytest.raises(Http404):
        public_views.veranstaltung_cancel(_req("get"), "garbage-token")
