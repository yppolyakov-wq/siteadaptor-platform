"""A6b: кабинет событий — CRUD, действия FSM, ручная запись, CSV-ростер."""

from datetime import timedelta

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.events import views
from apps.events.models import Event, Ticket

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


class _User:
    is_authenticated = True
    is_active = True


def _req(method, data=None):
    request = getattr(RequestFactory(), method)("/dashboard/events/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = _User()
    return request


def _event(**kw):
    defaults = {
        "title": "Workshop",
        "starts_at": timezone.now() + timedelta(days=5),
        "status": Event.STATUS_PUBLISHED,
        "price_cents": 2000,
        "capacity": 10,
    }
    defaults.update(kw)
    return Event.objects.create(**defaults)


def test_create_event_converts_price_and_questions():
    resp = views.event_create(
        _req(
            "post",
            {
                "title": "Yoga",
                "starts_at": "2026-07-01T18:00",
                "price_eur": "25.00",
                "capacity": "12",
                "questions_text": "Allergien?\nLevel?",
            },
        )
    )
    assert resp.status_code == 302
    event = Event.objects.get(title="Yoga")
    assert event.price_cents == 2500
    assert event.questions == ["Allergien?", "Level?"]


def test_publish_action():
    event = _event(status=Event.STATUS_DRAFT)
    views.event_action(_req("post", {"target": "published"}), pk=event.pk)
    event.refresh_from_db()
    assert event.status == Event.STATUS_PUBLISHED


def test_manual_ticket_add_confirmed():
    event = _event()
    views.ticket_add(_req("post", {"name": "Kunde", "quantity": "2"}), pk=event.pk)
    ticket = Ticket.objects.get(event=event)
    assert ticket.quantity == 2
    assert ticket.status == Ticket.STATUS_CONFIRMED


def test_ticket_mark_paid_confirms_pending():
    event = _event()
    from apps.events.services import book_ticket

    ticket = book_ticket(event, name="K", email="k@test.de")  # pending
    views.ticket_action(_req("post", {"target": "paid"}), pk=event.pk, tid=ticket.pk)
    ticket.refresh_from_db()
    assert ticket.payment_state == Ticket.PAYMENT_PAID
    assert ticket.status == Ticket.STATUS_CONFIRMED


def test_roster_csv_lists_attendees_with_answers():
    event = _event(questions=["Allergien?"])
    from apps.events.services import book_ticket

    book_ticket(
        event, name="Anna", email="a@test.de", answers={"Allergien?": "Nüsse"}, auto_confirm=True
    )
    resp = views.roster_csv(_req("get"), pk=event.pk)
    body = resp.content.decode("utf-8-sig")
    assert "Anna" in body and "Allergien?" in body and "Nüsse" in body


# --- RT3: recurring-серии событий -------------------------------------------------
def test_create_series_generates_shifted_copies_with_shared_id():
    from apps.events.services import create_series

    src = _event(starts_at=timezone.now() + timedelta(days=2))
    created = create_series(src, interval="weekly", count=3)
    assert len(created) == 3
    src.refresh_from_db()
    assert src.series_id is not None
    assert all(c.series_id == src.series_id for c in created)
    # сдвиг по неделям
    assert created[0].starts_at - src.starts_at == timedelta(weeks=1)
    assert created[2].starts_at - src.starts_at == timedelta(weeks=3)
    # всего 4 события в серии (источник + 3)
    assert Event.objects.filter(series_id=src.series_id).count() == 4


def test_create_series_biweekly_and_monthly():
    from apps.events.services import _add_months, create_series

    src = _event(starts_at=timezone.now() + timedelta(days=1))
    bi = create_series(src, interval="biweekly", count=1)
    assert bi[0].starts_at - src.starts_at == timedelta(weeks=2)
    mo = create_series(src, interval="monthly", count=1)
    assert mo[0].starts_at == _add_months(src.starts_at, 1)


def test_add_months_handles_month_end():
    from datetime import datetime

    from apps.events.services import _add_months

    jan31 = datetime(2026, 1, 31, 18, 0)
    assert _add_months(jan31, 1).day == 28  # февраль 2026


def test_create_series_copies_m2m_not_tickets():
    from apps.events.models import Teacher
    from apps.events.services import book_ticket, create_series

    src = _event()
    t = Teacher.objects.create(name="Lea")
    src.teachers.add(t)
    book_ticket(src, name="K", email="k@test.de", auto_confirm=True)
    clone = create_series(src, interval="weekly", count=1)[0]
    assert list(clone.teachers.all()) == [t]  # M2M скопирован
    assert clone.tickets.count() == 0  # билеты НЕ скопированы


def test_event_series_view_creates_dates():
    src = _event()
    resp = views.event_series(_req("post", {"interval": "weekly", "count": "2"}), pk=src.pk)
    assert resp.status_code == 302
    src.refresh_from_db()
    assert Event.objects.filter(series_id=src.series_id).count() == 3  # источник + 2


# --- RT1: Check-in билета по QR --------------------------------------------------
def _confirmed_ticket(event=None):
    from apps.events.services import book_ticket

    event = event or _event()
    return book_ticket(event, name="Gast", email="g@test.de", auto_confirm=True)


def test_checkin_get_renders_ticket():
    ticket = _confirmed_ticket()
    body = views.checkin(_req("get"), code=ticket.reference_code).content.decode()
    assert ticket.reference_code in body and "Gast" in body


def test_checkin_post_marks_attended_and_timestamps():
    ticket = _confirmed_ticket()
    resp = views.checkin(_req("post"), code=ticket.reference_code)
    assert resp.status_code == 302
    ticket.refresh_from_db()
    assert ticket.status == Ticket.STATUS_ATTENDED and ticket.checked_in_at is not None


def test_checkin_is_idempotent():
    ticket = _confirmed_ticket()
    views.checkin(_req("post"), code=ticket.reference_code)
    ticket.refresh_from_db()
    first = ticket.checked_in_at
    views.checkin(_req("post"), code=ticket.reference_code)  # повторный скан
    ticket.refresh_from_db()
    assert ticket.checked_in_at == first  # не перезаписан


def test_checkin_lowercase_code_resolves():
    ticket = _confirmed_ticket()
    views.checkin(_req("post"), code=ticket.reference_code.lower())
    ticket.refresh_from_db()
    assert ticket.checked_in_at is not None


def test_cancelled_ticket_cannot_checkin():
    ticket = _confirmed_ticket()
    ticket.status = Ticket.STATUS_CANCELLED
    ticket.save(update_fields=["status"])
    views.checkin(_req("post"), code=ticket.reference_code)
    ticket.refresh_from_db()
    assert ticket.checked_in_at is None


def test_event_form_roundtrips_program_lines():
    from apps.events.forms import EventForm

    form = EventForm(
        data={
            "title": "Retreat",
            "starts_at": "2099-01-01T10:00",
            "capacity": 0,
            "price_eur": "0",
            "program_text": "Tag 1: Ankunft\nTag 2: Yoga\n\nTag 3: Abreise",
        }
    )
    assert form.is_valid(), form.errors
    event = form.save()
    assert event.program == ["Tag 1: Ankunft", "Tag 2: Yoga", "Tag 3: Abreise"]
    # повторная инициализация формой подставляет построчно
    assert EventForm(instance=event).fields["program_text"].initial == (
        "Tag 1: Ankunft\nTag 2: Yoga\nTag 3: Abreise"
    )
