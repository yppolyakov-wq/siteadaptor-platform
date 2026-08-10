"""SM-3: кастом-статус билета (FB-3 Вариант B) и anti-oversell мест события.

Билет, переведённый владельцем в кастом-статус с ролью active
(blocks_capacity=True), обязан ПРОДОЛЖАТЬ занимать место: guard ёмкости,
guard тира и счётчики seats_sold/tier_sold_map считают его. До SM-3 эти
четыре места фильтровали литеральным `Ticket.ACTIVE_STATUSES` — кастом-статус
выпадал из сумм, и место продавалось второй раз.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core import status_registry
from apps.events.models import Event, Ticket
from apps.events.services import SoldOut, book_ticket

pytestmark = pytest.mark.django_db


def _event(**kw):
    defaults = {
        "title": "Konzert",
        "starts_at": timezone.now() + timedelta(days=7),
        "status": Event.STATUS_PUBLISHED,
        "price_cents": 5000,
        "capacity": 1,
    }
    defaults.update(kw)
    return Event.objects.create(**defaults)


@pytest.fixture
def _custom_tenant(monkeypatch):
    """Тенант с кастом-active статусом билета «Warte auf Zahlung»."""
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(
        site_config={
            "status_defs": {
                "ticket": [
                    {
                        "code": "warte_zahlung",
                        "role": "active",
                        "stage": "in_progress",
                        "blocks_capacity": True,
                    }
                ]
            }
        }
    )
    monkeypatch.setattr(status_registry, "_current_tenant", lambda: tenant)
    return tenant


def test_custom_active_ticket_blocks_event_capacity(_custom_tenant):
    event = _event(capacity=1)
    t = book_ticket(event, name="A", email="a@test.de", quantity=1)
    Ticket.objects.filter(pk=t.pk).update(status="warte_zahlung")

    with pytest.raises(SoldOut):
        book_ticket(event, name="B", email="b@test.de", quantity=1)

    # Контроль: терминальный статус место освобождает (guard живой, не залип).
    Ticket.objects.filter(pk=t.pk).update(status="cancelled")
    book_ticket(event, name="B", email="b@test.de", quantity=1)


def test_custom_active_ticket_counts_in_seats_sold(_custom_tenant):
    event = _event(capacity=10)
    t = book_ticket(event, name="A", email="a@test.de", quantity=2)
    Ticket.objects.filter(pk=t.pk).update(status="warte_zahlung")

    assert event.seats_sold == 2
    assert event.seats_left == 8


def test_custom_active_ticket_blocks_tier_capacity(_custom_tenant):
    event = _event(
        capacity=0,  # без общего лимита — проверяем именно тир
        tiers=[{"label": "Einzel", "price_cents": 12000, "capacity": 1}],
    )
    t = book_ticket(event, name="A", email="a@test.de", quantity=1, tier_label="Einzel")
    Ticket.objects.filter(pk=t.pk).update(status="warte_zahlung")

    with pytest.raises(SoldOut):
        book_ticket(event, name="B", email="b@test.de", quantity=1, tier_label="Einzel")
    assert event.tier_sold_map().get("Einzel") == 1


def test_custom_cancelled_ticket_not_verified_reviewer(monkeypatch):
    """SM-3: гость с билетом в КАСТОМ-cancel статусе — не «верифицированный
    покупатель» (до фикса has_ticket исключал только литеральный cancelled)."""
    from apps.events.reviews import has_ticket
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(
        site_config={
            "status_defs": {
                "ticket": [{"code": "abgesagt_kulanz", "role": "cancelled", "stage": "terminal"}]
            }
        }
    )
    monkeypatch.setattr(status_registry, "_current_tenant", lambda: tenant)

    event = _event(capacity=10)
    t = book_ticket(event, name="A", email="gast@test.de", quantity=1)
    assert has_ticket(event, "gast@test.de") is True
    Ticket.objects.filter(pk=t.pk).update(status="abgesagt_kulanz")
    assert has_ticket(event, "gast@test.de") is False
