"""R11: вместимость per-tier — анти-овердрафт по ценовому тиру билета.

Каждый тир может нести свой `capacity` (JSON `Event.tiers`); 0 = без отдельного
лимита (как раньше). Тир-лимит проверяется в `book_ticket` под той же блокировкой
строки Event, что и общий `Event.capacity`.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.events import details
from apps.events.models import Event, Ticket
from apps.events.services import SoldOut, book_ticket

pytestmark = pytest.mark.django_db


def _event(**kw):
    defaults = {
        "title": "Yoga-Retreat",
        "starts_at": timezone.now() + timedelta(days=7),
        "status": Event.STATUS_PUBLISHED,
        "price_cents": 9900,
        "capacity": 0,  # без общего лимита — проверяем именно тир
    }
    defaults.update(kw)
    return Event.objects.create(**defaults)


# --- парс/сериализация схемы тира --------------------------------------------


def test_normalize_tiers_parses_capacity_column():
    tiers = details.normalize_tiers(["Frühbucher | 79 | 10", "Standard | 99"])
    assert tiers == [
        {"label": "Frühbucher", "price_cents": 7900, "capacity": 10},
        {"label": "Standard", "price_cents": 9900, "capacity": 0},
    ]


def test_normalize_tiers_from_dict_capacity():
    tiers = details.normalize_tiers([{"label": "Einzel", "price_cents": 12000, "capacity": 2}])
    assert tiers[0]["capacity"] == 2


def test_normalize_tiers_bad_capacity_is_zero():
    tiers = details.normalize_tiers(["Standard | 99 | abc"])
    assert tiers[0]["capacity"] == 0


def test_tiers_to_text_roundtrip_with_capacity():
    text = details.tiers_to_text([{"label": "Mehrbett", "price_cents": 5000, "capacity": 4}])
    assert text == "Mehrbett | 50.00 | 4"
    # без лимита — без третьего столбца
    assert details.tiers_to_text([{"label": "Std", "price_cents": 5000}]) == "Std | 50.00"


# --- анти-овердрафт по тиру ---------------------------------------------------


def test_book_respects_tier_capacity():
    event = _event(tiers=[{"label": "Einzel", "price_cents": 12000, "capacity": 2}])
    book_ticket(event, name="A", email="a@test.de", quantity=2, tier_label="Einzel")
    with pytest.raises(SoldOut) as exc:
        book_ticket(event, name="B", email="b@test.de", quantity=1, tier_label="Einzel")
    assert exc.value.available == 0


def test_tier_capacity_independent_per_tier():
    event = _event(
        tiers=[
            {"label": "Einzel", "price_cents": 12000, "capacity": 1},
            {"label": "Mehrbett", "price_cents": 5000, "capacity": 0},  # безлимит
        ]
    )
    book_ticket(event, name="A", email="a@test.de", quantity=1, tier_label="Einzel")
    # Einzel исчерпан…
    with pytest.raises(SoldOut):
        book_ticket(event, name="B", email="b@test.de", quantity=1, tier_label="Einzel")
    # …а безлимитный Mehrbett по-прежнему продаётся
    book_ticket(event, name="C", email="c@test.de", quantity=9, tier_label="Mehrbett")
    assert event.tier_seats_left("Einzel") == 0
    assert event.tier_seats_left("Mehrbett") is None


def test_cancelled_ticket_frees_tier_seat():
    event = _event(tiers=[{"label": "Einzel", "price_cents": 12000, "capacity": 1}])
    ticket = book_ticket(event, name="A", email="a@test.de", quantity=1, tier_label="Einzel")
    from apps.events.state_machine import TicketSM

    TicketSM().apply(ticket, Ticket.STATUS_CANCELLED)
    # место освободилось — снова влезает
    book_ticket(event, name="B", email="b@test.de", quantity=1, tier_label="Einzel")
    assert event.tier_seats_left("Einzel") == 0


def test_tier_capacity_also_bounded_by_event_capacity():
    # общий лимит строже тира → срабатывает общий анти-овердрафт
    event = _event(capacity=1, tiers=[{"label": "Std", "price_cents": 9900, "capacity": 10}])
    book_ticket(event, name="A", email="a@test.de", quantity=1, tier_label="Std")
    with pytest.raises(SoldOut):
        book_ticket(event, name="B", email="b@test.de", quantity=1, tier_label="Std")


# --- витрина: tiers_display / is_sold_out ------------------------------------


def test_tiers_display_marks_sold_out_and_default():
    event = _event(
        tiers=[
            {"label": "Einzel", "price_cents": 12000, "capacity": 1},
            {"label": "Mehrbett", "price_cents": 5000, "capacity": 4},
        ]
    )
    book_ticket(event, name="A", email="a@test.de", quantity=1, tier_label="Einzel")
    disp = {t["label"]: t for t in event.tiers_display}
    assert disp["Einzel"]["sold_out"] is True
    assert disp["Einzel"]["is_default"] is False
    assert disp["Mehrbett"]["sold_out"] is False
    # первый доступный тир — дефолтный для предвыбора
    assert disp["Mehrbett"]["is_default"] is True
    assert disp["Mehrbett"]["seats_left"] == 4


def test_event_sold_out_when_all_tiers_full():
    event = _event(
        tiers=[
            {"label": "Einzel", "price_cents": 12000, "capacity": 1},
            {"label": "Mehrbett", "price_cents": 5000, "capacity": 1},
        ]
    )
    assert event.is_sold_out is False
    book_ticket(event, name="A", email="a@test.de", quantity=1, tier_label="Einzel")
    book_ticket(event, name="B", email="b@test.de", quantity=1, tier_label="Mehrbett")
    assert event.is_sold_out is True


def test_unlimited_tier_keeps_event_bookable():
    # хоть один безлимитный тир — событие не «sold out» по тирам
    event = _event(
        tiers=[
            {"label": "Einzel", "price_cents": 12000, "capacity": 1},
            {"label": "Standard", "price_cents": 9900},  # без лимита
        ]
    )
    book_ticket(event, name="A", email="a@test.de", quantity=1, tier_label="Einzel")
    assert event.is_sold_out is False
