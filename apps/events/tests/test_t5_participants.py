"""KA-12 T-5 (EV-2): данные каждого участника групповой брони.

Было: билет на 4 места нёс одно имя покупателя — организатор собирал имена и
анкеты по телефону. Стало: строка на место (имя + анкета события); покупатель
заполняет по подписанной ссылке, владелец правит в кабинете; check-in и roster
видят участников; DSGVO-удаление клиента стирает их."""

from datetime import timedelta

import pytest
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory
from django.utils import timezone

from apps.crm import dsgvo
from apps.events import participants, public_views, views
from apps.events.models import Event, Ticket, TicketParticipant
from apps.events.services import book_ticket
from apps.events.tests.test_logistics import _cab

pytestmark = pytest.mark.django_db


class _Tenant:
    stripe_connect_id = ""
    site_config = {}

    def is_module_active(self, name):
        return True


def _event(**kw):
    data = {
        "title": "Retreat",
        "starts_at": timezone.now() + timedelta(days=20),
        "status": Event.STATUS_PUBLISHED,
        "price_cents": 10000,
        "capacity": 20,
        "registration_fields": ["diet"],
    }
    data.update(kw)
    return Event.objects.create(**data)


def _ticket(event, quantity=3):
    return book_ticket(event, name="Anna", email="anna@t.de", quantity=quantity, auto_confirm=True)


def _guest_post(token, data):
    req = RequestFactory().post("/", data)
    req.tenant = _Tenant()
    req.session = {}
    req._messages = FallbackStorage(req)
    return public_views.veranstaltung_participants(req, token)


def test_slots_one_per_seat_buyer_prefilled():
    t = _ticket(_event())
    slots = participants.slots(t)
    assert [s["position"] for s in slots] == [1, 2, 3]
    assert slots[0]["name"] == "Anna" and slots[1]["name"] == ""
    assert [f["key"] for f in slots[0]["fields"]] == ["diet"]


def test_guest_link_saves_names_and_answers():
    t = _ticket(_event())
    resp = _guest_post(
        participants.token(t),
        {"p1_name": "Anna", "p2_name": "Ben", "p2_reg_diet": "Vegan", "p3_name": ""},
    )
    assert resp.status_code == 302
    rows = list(TicketParticipant.objects.filter(ticket=t))
    assert [(r.position, r.name) for r in rows] == [(1, "Anna"), (2, "Ben")]
    assert rows[1].answers == {"diet": "Vegan"}


def test_forged_token_404_and_started_event_read_only():
    from django.http import Http404

    with pytest.raises(Http404):
        _guest_post("forged", {})
    t = _ticket(_event())
    Event.objects.filter(pk=t.event_id).update(starts_at=timezone.now() - timedelta(hours=1))
    _guest_post(participants.token(t), {"p2_name": "Spät"})
    assert not TicketParticipant.objects.filter(ticket=t).exists()


def test_cabinet_name_change_and_seats_beyond_quantity_dropped():
    t = _ticket(_event(), quantity=2)
    TicketParticipant.objects.create(ticket=t, position=3, name="Alt")
    views.ticket_action(
        _cab("post", {"action": "participants", "p1_name": "Anna Neu", "p2_name": "Carl"}),
        pk=t.event_id,
        tid=t.pk,
    )
    assert participants.names(t) == ["Anna Neu", "Carl"]


def test_link_shown_for_groups_and_mailed():
    t = _ticket(_event(registration_fields=[]), quantity=1)
    assert not participants.wanted(t)
    assert participants.wanted(_ticket(_event(registration_fields=[]), quantity=2))


def test_roster_has_participant_rows():
    event = _event()
    t = _ticket(event)
    TicketParticipant.objects.create(ticket=t, position=2, name="Ben", answers={"diet": "Vegan"})
    req = _cab("get")
    from unittest import mock

    with mock.patch("apps.core.permissions.has_perm", return_value=True):
        body = views.roster_csv(req, pk=event.pk).content.decode("utf-8-sig")
    lines = body.strip().splitlines()
    assert body.count("\ufeff") == 0  # один BOM в начале снят decode'ом, в строках — нет
    assert any(
        line.startswith(f"{t.reference_code} #2;Ben") and line.endswith("Vegan") for line in lines
    )


def test_dsgvo_erasure_deletes_participants_and_export_has_them():
    t = _ticket(_event())
    t.status = Ticket.STATUS_CANCELLED
    t.save(update_fields=["status"])
    TicketParticipant.objects.create(ticket=t, position=2, name="Ben", answers={"diet": "Vegan"})
    exported = dsgvo.export_customer(t.customer)
    assert "Ben" in str(exported)
    dsgvo.erase_customer(t.customer)
    assert not TicketParticipant.objects.filter(ticket=t).exists()


def test_closed_page_shows_no_health_data():
    t = _ticket(_event(registration_fields=["medical"]))
    TicketParticipant.objects.create(
        ticket=t, position=2, name="Ben", answers={"medical": "Asthma"}
    )
    t.status = Ticket.STATUS_CANCELLED
    t.save(update_fields=["status"])
    req = RequestFactory().get("/")
    req.tenant = _Tenant()
    req.session = {}
    req._messages = FallbackStorage(req)
    html = public_views.veranstaltung_participants(req, participants.token(t)).content.decode()
    assert "Asthma" not in html and "Ben" not in html


def test_guest_save_refused_under_lock_after_cancel():
    t = _ticket(_event())
    Ticket.objects.filter(pk=t.pk).update(status=Ticket.STATUS_CANCELLED)
    assert participants.save(t, {"p2_name": "Ben"}, source="guest") is None
    assert not TicketParticipant.objects.filter(ticket=t).exists()


def test_absent_fields_do_not_wipe_and_hidden_contact_is_kept():
    t = _ticket(_event(registration_fields=["emergency_contact"]))
    TicketParticipant.objects.create(
        ticket=t, position=2, name="Ben", answers={"emergency_contact": "Mama 0170"}
    )
    participants.save(t, {"p1_name": "Anna"}, source="cabinet")  # место 2 в форме не было
    participants.save(t, {"p2_name": "Ben B."}, source="cabinet", hide_contacts=True)
    row = TicketParticipant.objects.get(ticket=t, position=2)
    assert row.name == "Ben B." and row.answers == {"emergency_contact": "Mama 0170"}
    assert all(
        f["key"] != "emergency_contact"
        for f in participants.slots(t, hide_contacts=True)[0]["fields"]
    )


def test_rows_beyond_quantity_are_not_read():
    t = _ticket(_event(), quantity=2)
    TicketParticipant.objects.create(ticket=t, position=1, name="Anna")
    TicketParticipant.objects.create(ticket=t, position=3, name="Geist")
    assert participants.names(t) == ["Anna"]
