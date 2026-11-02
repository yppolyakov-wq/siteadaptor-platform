"""SEC-G3 (аудит 2026-11-01): ответы анкеты участника — данные здоровья (Art. 9 DSGVO).

Хранятся зашифрованными и удаляются через 30 дней после события."""

from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone

from apps.events.models import Event, Ticket, TicketParticipant
from apps.events.tests.test_b2_6_balance_reminder import _ticket

pytestmark = pytest.mark.django_db


def _raw(table, pk):
    with connection.cursor() as cur:
        cur.execute(f'SELECT answers::text FROM "{table}" WHERE id = %s', [pk])
        return cur.fetchone()[0]


def test_ticket_answers_are_encrypted_at_rest():
    ticket = _ticket("paid")
    Ticket.objects.filter(pk=ticket.pk).update(answers={"Allergien": "Nüsse"})
    ticket.answers = {"Allergien": "Nüsse"}
    ticket.save(update_fields=["answers"])
    raw = _raw(Ticket._meta.db_table, ticket.pk)
    assert "Nüsse" not in raw and "Allergien" not in raw
    ticket.refresh_from_db()
    assert ticket.answers == {"Allergien": "Nüsse"}


def test_participant_answers_are_encrypted_at_rest():
    ticket = _ticket("paid")
    part = TicketParticipant.objects.create(ticket=ticket, position=1, answers={"diet": "vegan"})
    assert "vegan" not in _raw(TicketParticipant._meta.db_table, part.pk)
    part.refresh_from_db()
    assert part.answers == {"diet": "vegan"}


def test_answers_are_purged_30_days_after_event():
    from apps.events.retention import purge_answers

    ticket = _ticket("paid")
    ticket.answers = {"Allergien": "Nüsse"}
    ticket.save(update_fields=["answers"])
    TicketParticipant.objects.create(ticket=ticket, position=1, answers={"diet": "vegan"})
    assert purge_answers() == 0  # событие ещё впереди
    Event.objects.filter(pk=ticket.event_id).update(
        starts_at=timezone.now() - timedelta(days=40), ends_at=None
    )
    assert purge_answers() >= 1
    ticket.refresh_from_db()
    assert ticket.answers == {}
    assert TicketParticipant.objects.get(ticket=ticket).answers == {}
