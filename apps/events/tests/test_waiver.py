"""R8: отказ от ответственности (Waiver) + Gesundheits-Selbstauskunft с e-подписью."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.events import services
from apps.events.models import DEFAULT_WAIVER_TEXT, Event, Ticket, TicketWaiver

pytestmark = pytest.mark.django_db


def _event(**kw):
    defaults = {
        "title": "Retreat",
        "starts_at": timezone.now() + timedelta(days=10),
        "status": Event.STATUS_PUBLISHED,
        "capacity": 20,
    }
    defaults.update(kw)
    return Event.objects.create(**defaults)


def test_waiver_required_without_signature_raises_and_rolls_back():
    ev = _event(waiver_required=True)
    with pytest.raises(services.WaiverRequired):
        services.book_ticket(ev, name="A", email="a@test.de")
    assert not Ticket.objects.filter(customer__email="a@test.de").exists()


def test_waiver_signed_creates_record_with_snapshot_and_ip():
    ev = _event(waiver_required=True)
    ticket = services.book_ticket(
        ev,
        name="Mara Lind",
        email="m@test.de",
        waiver_signed_name="Mara Lind",
        health_confirmed=True,
        signed_ip="10.0.0.5",
    )
    waiver = TicketWaiver.objects.get(ticket=ticket)
    assert waiver.signed_name == "Mara Lind"
    assert waiver.health_confirmed is True
    assert waiver.signed_at is not None
    assert str(waiver.signed_ip) == "10.0.0.5"
    assert waiver.waiver_text_snapshot == DEFAULT_WAIVER_TEXT


def test_custom_waiver_text_snapshotted():
    ev = _event(waiver_required=True, waiver_text="Eigener Haftungstext.")
    ticket = services.book_ticket(ev, name="A", email="a@test.de", waiver_signed_name="A")
    assert ticket.waiver.waiver_text_snapshot == "Eigener Haftungstext."


def test_no_waiver_when_not_required():
    ev = _event(waiver_required=False)
    ticket = services.book_ticket(ev, name="A", email="a@test.de")
    assert not TicketWaiver.objects.filter(ticket=ticket).exists()


def test_effective_waiver_text_falls_back_to_default():
    assert _event().effective_waiver_text == DEFAULT_WAIVER_TEXT
    assert _event(waiver_text="X").effective_waiver_text == "X"


def test_event_form_saves_waiver_fields():
    from apps.events.forms import EventForm

    form = EventForm(
        data={
            "title": "Retreat",
            "starts_at": "2099-01-01T10:00",
            "capacity": 20,
            "price_eur": "0",
            "waiver_required": "on",
            "waiver_text": "Mein Haftungsausschluss.",
        }
    )
    assert form.is_valid(), form.errors
    ev = form.save()
    assert ev.waiver_required is True and ev.waiver_text == "Mein Haftungsausschluss."


def test_memo_pdf_notes_signed_waiver():
    from apps.events import memo
    from apps.tenants.tests.factories import TenantFactory

    ev = _event(waiver_required=True)
    ticket = services.book_ticket(ev, name="A", email="a@test.de", waiver_signed_name="Anna B")
    pdf = memo.build_memo_pdf(ticket, TenantFactory.build())
    assert pdf[:4] == b"%PDF"  # рендер не падает при наличии waiver
