"""R1: лист ожидания события + структурированная анкета участника."""

import uuid
from datetime import timedelta

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.events import public_views, registration, services, views
from apps.events.models import Event, EventWaitlistEntry, Ticket
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


class _User:
    is_authenticated = True
    is_active = True


def _public_req(method="post", data=None, tenant=None):
    request = getattr(RequestFactory(), method)("/veranstaltung/", data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.7"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant or TenantFactory.build()
    return request


def _cabinet_req(method, data=None):
    request = getattr(RequestFactory(), method)("/dashboard/events/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = _User()
    return request


def _event(**kw):
    defaults = {
        "title": "Retreat",
        "starts_at": timezone.now() + timedelta(days=10),
        "status": Event.STATUS_PUBLISHED,
        "price_cents": 0,
        "capacity": 2,
    }
    defaults.update(kw)
    return Event.objects.create(**defaults)


# --- registration presets --------------------------------------------------
def test_registration_active_filters_and_orders():
    """active(): отбрасывает мусор/дубли, сохраняет порядок каталога."""
    out = registration.active(["diet", "junk", "country", "diet"])
    keys = [f["key"] for f in out]
    assert keys == ["country", "diet"]  # порядок каталога, без мусора/дублей


def test_book_stores_preset_answers():
    event = _event(registration_fields=["country", "diet"], questions=["Anmerkung?"])
    public_views.veranstaltung_book(
        _public_req(
            "post",
            {
                "name": "Anna",
                "email": "a@test.de",
                "q0": "Hallo",
                "reg_country": "Österreich",
                "reg_diet": "Vegan",
            },
        ),
        pk=event.pk,
    )
    ticket = Ticket.objects.get(event=event)
    assert ticket.answers["country"] == "Österreich"
    assert ticket.answers["diet"] == "Vegan"
    assert ticket.answers["Anmerkung?"] == "Hallo"  # свободный вопрос не сломан


def test_roster_csv_includes_preset_columns():
    event = _event(registration_fields=["diet"])
    services.book_ticket(
        event, name="Anna", email="a@test.de", answers={"diet": "Vegan"}, auto_confirm=True
    )
    body = views.roster_csv(_cabinet_req("get"), pk=event.pk).content.decode("utf-8-sig")
    assert "Ernährung" in body and "Vegan" in body  # колонка по label + значение


def test_form_roundtrips_registration_fields():
    from apps.events.forms import EventForm

    form = EventForm(
        data={
            "title": "Retreat",
            "starts_at": "2099-01-01T10:00",
            "capacity": 0,
            "price_eur": "0",
            "registration_fields": ["diet", "country"],
        }
    )
    assert form.is_valid(), form.errors
    event = form.save()
    assert event.registration_fields == ["country", "diet"]  # порядок каталога


# --- waitlist --------------------------------------------------------------
def test_join_waitlist_creates_entry():
    event = _event(capacity=1)
    resp = public_views.veranstaltung_waitlist(
        _public_req("post", {"name": "Sven", "email": "S@Test.de", "quantity": "2"}), pk=event.pk
    )
    assert resp.status_code == 302
    entry = EventWaitlistEntry.objects.get(event=event)
    assert entry.email == "s@test.de" and entry.party_size == 2 and entry.name == "Sven"


def test_join_waitlist_honeypot_blocks():
    event = _event()
    public_views.veranstaltung_waitlist(
        _public_req("post", {"email": "b@test.de", "website": "spam"}), pk=event.pk
    )
    assert EventWaitlistEntry.objects.filter(event=event).count() == 0


def test_join_waitlist_idempotent_by_email():
    event = _event()
    services.join_waitlist(event, email="x@test.de", name="A")
    services.join_waitlist(event, email="x@test.de", name="B")
    assert EventWaitlistEntry.objects.filter(event=event).count() == 1


def test_notify_event_waitlist_sends_when_seat_free():
    """Свободное место → письмо листу ожидания, помечает notified (одно на запись)."""
    event = _event(capacity=2)
    services.book_ticket(event, name="A", email="a@test.de", quantity=1, auto_confirm=True)
    services.join_waitlist(event, email="wl@test.de")
    sent = services.notify_event_waitlist(event)
    assert sent == 1
    assert EventWaitlistEntry.objects.get(event=event).notified is True
    # повторный вызов не шлёт дубль
    assert services.notify_event_waitlist(event) == 0


def test_notify_event_waitlist_skips_when_sold_out():
    event = _event(capacity=1)
    services.book_ticket(event, name="A", email="a@test.de", quantity=1, auto_confirm=True)
    services.join_waitlist(event, email="wl@test.de")
    assert services.notify_event_waitlist(event) == 0  # мест нет → не уведомляем
    assert EventWaitlistEntry.objects.get(event=event).notified is False


def test_cancel_ticket_notifies_waitlist():
    """Отмена билета освобождает место → авто-уведомление листа ожидания."""
    event = _event(capacity=1)
    ticket = services.book_ticket(event, name="A", email="a@test.de", auto_confirm=True)
    services.join_waitlist(event, email="wl@test.de")
    views.ticket_action(
        _cabinet_req("post", {"target": Ticket.STATUS_CANCELLED}), pk=event.pk, tid=ticket.pk
    )
    assert EventWaitlistEntry.objects.get(event=event).notified is True


def test_sold_out_detail_shows_waitlist_form():
    event = _event(capacity=1)
    services.book_ticket(event, name="A", email="a@test.de", auto_confirm=True)
    body = public_views.veranstaltung_detail(_public_req("get"), event.pk).content.decode()
    assert "warteliste" in body.lower()  # форма листа ожидания на распроданном
