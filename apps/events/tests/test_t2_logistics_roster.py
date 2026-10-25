"""KA-12 Tickets T-2: лист ожидания по числу мест · правка/удаление поставщика ·
чек-лист из другого заезда · полный roster."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.events import services, views
from apps.events.logistics import SupplierBooking, TourTask
from apps.events.models import Event, EventWaitlistEntry
from apps.events.tests.test_logistics import _booking, _cab
from apps.finance.expenses import ExpenseEntry

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _event(**kw):
    defaults = {
        "title": "Tour",
        "starts_at": timezone.now() + timedelta(days=30),
        "status": Event.STATUS_PUBLISHED,
        "capacity": 3,
    }
    defaults.update(kw)
    return Event.objects.create(**defaults)


# --- лист ожидания ----------------------------------------------------------------


def test_waitlist_skips_group_that_does_not_fit():
    event = _event(capacity=3)
    services.book_ticket(event, name="A", email="a@t.de", quantity=2, auto_confirm=True)
    services.join_waitlist(event, email="gruppe@t.de", party_size=4)
    services.join_waitlist(event, email="single@t.de", party_size=1)
    assert services.notify_event_waitlist(event) == 1
    notified = set(EventWaitlistEntry.objects.filter(notified=True).values_list("email", flat=True))
    assert notified == {"single@t.de"}


def test_waitlist_does_not_promise_more_seats_than_free():
    event = _event(capacity=3)
    services.book_ticket(event, name="A", email="a@t.de", quantity=1, auto_confirm=True)
    for i in range(3):
        services.join_waitlist(event, email=f"w{i}@t.de", party_size=1)
    assert services.notify_event_waitlist(event) == 2  # свободно 2 места


# --- логистика --------------------------------------------------------------------


def _post(event, data):
    return views.event_logistics(_cab("post", data), pk=event.pk)


def test_edit_booking_updates_fields_and_paid_expense():
    event = _event()
    b = _booking(event, status=SupplierBooking.STATUS_PAID)
    from apps.events.tour_finance import sync_expense

    sync_expense(b)
    _post(
        event,
        {
            "action": "edit_booking",
            "id": b.pk,
            "kind": "transport",
            "supplier_name": "Bus",
            "cost_eur": "500,00",
            "date": "2026-11-30",
            "qty": "2",
        },
    )
    b.refresh_from_db()
    assert (b.kind, b.supplier_name, b.cost_cents, b.qty) == ("transport", "Bus", 50000, 2)
    assert str(b.date) == "2026-11-30"
    assert ExpenseEntry.objects.get(event=event).amount == 500


def test_garbage_fields_do_not_500():
    event = _event()
    resp = _post(
        event,
        {
            "action": "add_booking",
            "date": "kaputt",
            "amount_original": "1e99",
            "supplier": "abc",
            "kind": "unbekannt",
        },
    )
    assert resp.status_code == 302
    b = SupplierBooking.objects.get(event=event)
    assert b.date is None and b.amount_original is None and b.kind == "other"
    resp = _post(event, {"action": "add_task", "title": "X", "due_date": "31.02."})
    assert resp.status_code == 302 and TourTask.objects.get(event=event).due_date is None


def test_delete_unpaid_booking_but_not_paid():
    event = _event()
    open_b = _booking(event)
    paid_b = _booking(event, status=SupplierBooking.STATUS_PAID)
    _post(event, {"action": "delete_booking", "id": open_b.pk})
    _post(event, {"action": "delete_booking", "id": paid_b.pk})
    assert list(SupplierBooking.objects.filter(event=event)) == [paid_b]


def test_copy_tasks_keeps_offset_and_skips_duplicates():
    old = _event(starts_at=timezone.now() + timedelta(days=10))
    TourTask.objects.create(
        event=old, title="Permits", due_date=old.starts_at.date() - timedelta(days=5)
    )
    TourTask.objects.create(event=old, title="Briefing")
    new = _event(starts_at=old.starts_at + timedelta(days=40))
    TourTask.objects.create(event=new, title="Briefing")
    _post(new, {"action": "copy_tasks", "source": str(old.pk)})
    tasks = {t.title: t.due_date for t in new.prep_tasks.all()}
    assert set(tasks) == {"Permits", "Briefing"}
    assert tasks["Permits"] == new.starts_at.date() - timedelta(days=5)


# --- roster -----------------------------------------------------------------------


def test_roster_has_tier_amount_open_and_checkin():
    event = _event(price_cents=2500)
    t = services.book_ticket(event, name="Gast", email="g@t.de", quantity=2, auto_confirm=True)
    t.checked_in_at = timezone.now()
    t.save(update_fields=["checked_in_at"])
    request = _cab("get")
    from apps.core.models import Membership

    Membership.objects.create(user=request.user, role=Membership.ROLE_OWNER)
    text = views.roster_csv(request, pk=event.pk).content.decode("utf-8-sig")
    header, row = text.splitlines()[:2]
    for col in ("Tarif", "Betrag", "Offen", "Extras", "Check-in"):
        assert col in header
    assert "50.00" in row
