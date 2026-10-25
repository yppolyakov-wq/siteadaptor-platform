"""KA-12 Tickets T-3: ранняя цена до даты (тир с `until`)."""

from datetime import date, timedelta

import pytest
from django.utils import timezone

from apps.events import details, services
from apps.events.models import Event

pytestmark = pytest.mark.django_db


def _event(tiers):
    return Event.objects.create(
        title="Workshop",
        starts_at=timezone.now() + timedelta(days=40),
        status=Event.STATUS_PUBLISHED,
        price_cents=9900,
        capacity=20,
        tiers=details.normalize_tiers(tiers),
    )


def _iso(days):
    return (timezone.localdate() + timedelta(days=days)).isoformat()


def test_parse_until_formats_and_garbage():
    assert details.parse_until("bis 30.11.2026") == "2026-11-30"
    assert details.parse_until("2026-11-30") == "2026-11-30"
    assert details.parse_until("until 30.11.2026") == "2026-11-30"
    assert details.parse_until("до 1.2.27") == "2027-02-01"
    assert details.parse_until("31.02.2026") == ""
    assert details.parse_until("bald") == ""
    assert details.parse_until("") == ""


def test_text_roundtrip_keeps_until():
    tiers = details.normalize_tiers(["Frühbucher | 79 | | bis 30.11.2026", "Standard | 99"])
    assert tiers[0]["until"] == "2026-11-30" and "until" not in tiers[1]
    again = details.normalize_tiers(details.tiers_to_text(tiers).splitlines())
    assert again == tiers


def test_old_tiers_unchanged_byte_for_byte():
    tiers = details.normalize_tiers(["Standard | 99 | 10"])
    assert tiers == [{"label": "Standard", "price_cents": 9900, "capacity": 10}]


def test_open_early_bird_sells_and_sets_from_price():
    event = _event(
        [
            {"label": "Früh", "price_cents": 7900, "until": _iso(5)},
            {"label": "Standard", "price_cents": 9900},
        ]
    )
    assert event.from_price_cents == 7900
    ticket = services.book_ticket(event, name="A", email="a@t.de", tier_label="Früh")
    assert ticket.price_cents == 7900


def test_expired_early_bird_is_not_sold():
    event = _event(
        [
            {"label": "Früh", "price_cents": 7900, "until": _iso(-1)},
            {"label": "Standard", "price_cents": 9900},
        ]
    )
    assert event.from_price_cents == 9900
    display = {t["label"]: t for t in event.tiers_display}
    assert display["Früh"]["closed"] and display["Standard"]["is_default"]
    with pytest.raises(services.TierClosed):
        services.book_ticket(event, name="A", email="a@t.de", tier_label="Früh")
    assert not event.is_sold_out


def test_only_expired_tiers_means_sold_out():
    event = _event([{"label": "Früh", "price_cents": 7900, "until": _iso(-1)}])
    assert event.is_sold_out


def test_until_is_inclusive_today():
    assert details.tier_open({"until": date.today().isoformat()}, today=date.today())
