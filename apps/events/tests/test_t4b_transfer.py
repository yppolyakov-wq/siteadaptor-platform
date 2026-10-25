"""KA-12 T-4b (EV-3): перенос билета на другую дату той же серии/тура.

Было: гость просит другой термин — владелец отменял билет (возврат денег, сторно
выручки) и продавал новый. Стало: одна кнопка «Umbuchen» в карточке билета; деньги,
тариф и оплата остаются на билете, места цели проверяются под блокировкой."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.events import views
from apps.events.models import Event, Ticket
from apps.events.services import (
    TransferRefused,
    book_ticket,
    transfer_targets,
    transfer_ticket,
)
from apps.events.tests.test_logistics import _cab
from apps.notifications.models import Notification
from apps.stays.models import StayBooking, StayUnit

pytestmark = pytest.mark.django_db


def _series(n=2, **kw):
    sid = uuid.uuid4()
    out = []
    for i in range(n):
        data = {
            "title": "Kochkurs",
            "starts_at": timezone.now() + timedelta(days=10 + 7 * i),
            "status": Event.STATUS_PUBLISHED,
            "price_cents": 5000,
            "capacity": 10,
            "series_id": sid,
        }
        data.update(kw)
        out.append(Event.objects.create(**data))
    return out


def _ticket(event, **kw):
    return book_ticket(event, name="Anna", email="anna@t.de", auto_confirm=True, **kw)


def test_targets_are_same_series_future_and_published():
    a, b, c = _series(3)
    Event.objects.create(title="Fremd", starts_at=b.starts_at, status=Event.STATUS_PUBLISHED)
    past = Event.objects.create(
        title="Alt",
        starts_at=timezone.now() - timedelta(days=1),
        status=Event.STATUS_PUBLISHED,
        series_id=a.series_id,
    )
    c.status = Event.STATUS_DRAFT
    c.save(update_fields=["status"])
    targets = list(transfer_targets(_ticket(a)))
    assert targets == [b] and past not in targets


def test_transfer_moves_ticket_keeps_money_and_resets_reminders():
    a, b = _series()
    t = _ticket(a)
    t.payment_state = Ticket.PAYMENT_PAID
    t.reminder_sent_at = timezone.now()
    t.save()
    result = transfer_ticket(t, b.pk)
    t.refresh_from_db()
    assert t.event_id == b.pk and t.price_cents == 5000
    assert t.payment_state == Ticket.PAYMENT_PAID and t.reminder_sent_at is None
    assert result["price_diff_cents"] == 0
    assert a.seats_sold == 0 and b.seats_sold == 1


def test_full_target_refused_with_free_seats():
    a, b = _series(capacity=2)
    _ticket(b, quantity=2)
    with pytest.raises(TransferRefused) as exc:
        transfer_ticket(_ticket(a), b.pk)
    assert exc.value.reason == "full" and exc.value.available == 0


def test_tier_capacity_on_target_is_checked():
    tiers = [{"label": "Früh", "price_cents": 4000, "capacity": 1}]
    a, b = _series(tiers=tiers)
    _ticket(b, tier_label="Früh")
    with pytest.raises(TransferRefused) as exc:
        transfer_ticket(_ticket(a, tier_label="Früh"), b.pk)
    assert exc.value.reason == "full"


def test_price_difference_reported():
    a, b = _series()
    b.price_cents = 6500
    b.save(update_fields=["price_cents"])
    result = transfer_ticket(_ticket(a, quantity=2), b.pk)
    assert result["price_diff_cents"] == 3000


@pytest.mark.parametrize("reason", ["status", "extras", "accommodation", "target"])
def test_refusals(reason):
    a, b = _series()
    t = _ticket(a)
    target = b.pk
    if reason == "status":
        t.status = Ticket.STATUS_CANCELLED
        t.save(update_fields=["status"])
    elif reason == "extras":
        t.extras = [{"label": "Schürze", "price_cents": 500}]
        t.save(update_fields=["extras"])
    elif reason == "accommodation":
        unit = StayUnit.objects.create(name="Zimmer", price_cents=1000)
        stay = StayBooking.objects.create(
            unit=unit,
            customer=t.customer,
            reference_code="S-T4BX1",
            arrival=a.starts_at.date(),
            departure=a.starts_at.date() + timedelta(days=1),
            price_cents=1000,
            total_cents=1000,
        )
        Ticket.objects.filter(pk=t.pk).update(stay_booking=stay)
    else:
        target = Event.objects.create(
            title="Fremd", starts_at=b.starts_at, status=Event.STATUS_PUBLISHED
        ).pk
    with pytest.raises(TransferRefused) as exc:
        transfer_ticket(t, target)
    assert exc.value.reason == reason
    t.refresh_from_db()
    assert t.event_id == a.pk


def test_email_sent_per_target_date(django_capture_on_commit_callbacks):
    a, b, c = _series(3)
    t = _ticket(a)
    with django_capture_on_commit_callbacks(execute=True):
        transfer_ticket(t, b.pk)
    with django_capture_on_commit_callbacks(execute=True):
        transfer_ticket(t, c.pk)
    keys = set(
        Notification.objects.filter(type="ticket_moved").values_list("dedupe_key", flat=True)
    )
    assert len(keys) == 2


def _post(ticket, **data):
    return views.ticket_action(
        _cab("post", {"action": "transfer", **data}), pk=ticket.event_id, tid=ticket.pk
    )


def test_view_moves_and_garbage_target_is_refused():
    a, b = _series()
    t = _ticket(a)
    resp = _post(t, target_event="nonsense")
    t.refresh_from_db()
    assert resp.status_code == 302 and t.event_id == a.pk
    _post(t, target_event=str(b.pk))
    t.refresh_from_db()
    assert t.event_id == b.pk


def test_installment_waiver_and_missing_tier_refused():
    from apps.events.models import InstallmentPlan

    a, b = _series()
    t = _ticket(a)
    InstallmentPlan.objects.create(ticket=t, total_cents=5000, count=2)
    with pytest.raises(TransferRefused) as exc:
        transfer_ticket(t, b.pk)
    assert exc.value.reason == "installment"

    a, b = _series()
    b.waiver_required = True
    b.save(update_fields=["waiver_required"])
    with pytest.raises(TransferRefused) as exc:
        transfer_ticket(_ticket(a), b.pk)
    assert exc.value.reason == "waiver"

    a, b = _series()
    b.tiers = [{"label": "Standard", "price_cents": 5000}]
    b.save(update_fields=["tiers"])
    with pytest.raises(TransferRefused) as exc:
        transfer_ticket(_ticket(a), b.pk)
    assert exc.value.reason == "tier"


def test_target_cancelled_after_listing_is_refused_under_lock():
    a, b = _series()
    t = _ticket(a)
    Event.objects.filter(pk=b.pk).update(status=Event.STATUS_CANCELLED)
    with pytest.raises(TransferRefused) as exc:
        transfer_ticket(t, b.pk)
    assert exc.value.reason == "target"


def test_back_and_forth_mails_every_time(django_capture_on_commit_callbacks):
    a, b = _series()
    t = _ticket(a)
    for target in (b, a, b):
        with django_capture_on_commit_callbacks(execute=True):
            transfer_ticket(t, target.pk)
    assert Notification.objects.filter(type="ticket_moved").count() == 3
