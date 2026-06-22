"""#7: универсальный движок Extras — scope-фильтр, снимок, интеграция в stays."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core import extras as extras_engine
from apps.core.models import Extra

pytestmark = pytest.mark.django_db


def test_active_for_filters_by_scope():
    Extra.objects.create(label="Frühstück", price_cents=1200, scope="stays", per_night=True)
    Extra.objects.create(label="Geschenk", price_cents=500, scope="all")
    Extra.objects.create(label="Nur Termin", price_cents=300, scope="booking")
    Extra.objects.create(label="Aus", price_cents=100, scope="stays", is_active=False)
    labels = [e.label for e in extras_engine.active_for("stays")]
    assert "Frühstück" in labels and "Geschenk" in labels  # stays + all
    assert "Nur Termin" not in labels and "Aus" not in labels  # чужой scope / неактивный


def test_snapshot_multiplies_per_night_and_ignores_foreign():
    e1 = Extra.objects.create(label="Frühstück", price_cents=1200, scope="stays", per_night=True)
    e2 = Extra.objects.create(label="Check-out", price_cents=2000, scope="stays", per_night=False)
    foreign = Extra.objects.create(label="Termin-Extra", price_cents=999, scope="booking")
    snap = extras_engine.snapshot([e1.pk, e2.pk, foreign.pk, "junk"], "stays", nights=3)
    # per_night × 3 ночи; разовый — без множителя; чужой scope/мусор отброшены
    assert {"label": "Frühstück", "price_cents": 3600} in snap
    assert {"label": "Check-out", "price_cents": 2000} in snap
    assert len(snap) == 2 and extras_engine.total_cents(snap) == 5600


def test_book_stay_adds_extras_to_total():
    from apps.stays.models import StayUnit
    from apps.stays.services import book_stay

    unit = StayUnit.objects.create(name="Zimmer", price_cents=8000, max_guests=2, is_active=True)
    e = Extra.objects.create(label="Frühstück", price_cents=1000, scope="stays", per_night=True)
    today = timezone.localdate()
    snap = extras_engine.snapshot([e.pk], "stays", nights=2)  # 2 ночи × 10 € = 20 €
    booking = book_stay(
        unit,
        arrival=today + timedelta(days=3),
        departure=today + timedelta(days=5),
        name="Gast",
        email="g@example.de",
        extras=snap,
    )
    assert booking.extras == snap
    assert booking.total_cents == 16000 + 2000  # 2 ночи × 80 € + завтрак 2×10 €


def test_book_termin_adds_extras_to_total():
    from apps.booking.models import Resource
    from apps.booking.services import book

    res = Resource.objects.create(name="Stuhl 1", is_active=True)
    e = Extra.objects.create(label="Kopfmassage", price_cents=900, scope="booking")
    snap = extras_engine.snapshot([e.pk], "booking")  # без множителя ночей
    start = timezone.now() + timedelta(days=1)
    booking = book(
        res,
        start=start,
        end=start + timedelta(minutes=30),
        name="Gast",
        email="g@example.de",
        price_cents=4000,  # услуга 40 €
        extras=snap,
    )
    assert booking.extras == snap
    assert booking.total_cents == 4900  # 40 € + 9 € Extra


def test_book_ticket_adds_extras_to_total():
    from apps.events.models import Event
    from apps.events.services import book_ticket

    event = Event.objects.create(
        title="Yoga-Retreat",
        starts_at=timezone.now() + timedelta(days=10),
        price_cents=5000,
        status=Event.STATUS_PUBLISHED,
    )
    e = Extra.objects.create(label="Mittagessen", price_cents=1500, scope="events")
    snap = extras_engine.snapshot([e.pk], "events")
    ticket = book_ticket(event, name="Gast", email="g@example.de", quantity=2, extras=snap)
    assert ticket.extras == snap
    assert ticket.total_cents == 5000 * 2 + 1500  # 2 места × 50 € + обед 15 € (разово)
