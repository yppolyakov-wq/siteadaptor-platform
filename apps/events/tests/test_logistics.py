"""MT-4/5/6: логистика по точкам, расходы/маржа заезда, чек-лист подготовки.

Главные замки: закупочная цена не утекает участнику; расход появляется ровно
один раз и исчезает при отмене оплаты; маржа честно учитывает неоплаченное.
"""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.events import views
from apps.events.logistics import SupplierBooking, TourTask
from apps.events.models import Event
from apps.events.tour_finance import event_margin, sync_expense
from apps.finance.expenses import ExpenseEntry
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _event():
    return Event.objects.create(
        title="Manali – Leh · Juni", starts_at=timezone.now() + timezone.timedelta(days=30)
    )


def _cab(method="get", data=None):
    request = getattr(RequestFactory(), method)("/dashboard/events/logistik/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(name="Himalaya Riders", enabled_modules=["events"])
    suffix = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"g-{suffix}", email=f"g-{suffix}@test.de", password="pw12345678"
    )
    return request


def _booking(event, **kwargs):
    kwargs.setdefault("kind", SupplierBooking.KIND_HOTEL)
    kwargs.setdefault("supplier_name", "Hotel Ibex")
    kwargs.setdefault("cost_cents", 42000)
    kwargs.setdefault("day", 4)
    kwargs.setdefault("stop", "Jispa")
    return SupplierBooking.objects.create(event=event, **kwargs)


class TestPurchasePricePrivacy:
    def test_participant_view_never_carries_cost(self):
        """Инвариант волны: закупочная цена не уходит участнику ни при каком флаге."""
        booking = _booking(_event(), visible_to_participants=True, cost_cents=99900)
        view = booking.participant_view()
        assert "999" not in str(view)
        assert "cost" not in view and "cost_cents" not in view
        assert view["supplier"] == "Hotel Ibex"
        assert view["confirmed"] is False

    def test_participant_view_reports_confirmation(self):
        booking = _booking(_event(), status=SupplierBooking.STATUS_CONFIRMED)
        assert booking.participant_view()["confirmed"] is True


class TestExpenseSync:
    def test_paid_booking_creates_expense_once(self):
        event = _event()
        booking = _booking(event, status=SupplierBooking.STATUS_PAID)
        sync_expense(booking)
        sync_expense(booking)  # повтор не двоит
        assert ExpenseEntry.objects.count() == 1
        entry = ExpenseEntry.objects.get()
        assert entry.amount == booking.cost_eur
        assert entry.event_id == event.pk
        assert entry.category == ExpenseEntry.CATEGORY_ACCOMMODATION

    def test_unpaid_booking_has_no_expense(self):
        booking = _booking(_event(), status=SupplierBooking.STATUS_CONFIRMED)
        sync_expense(booking)
        assert ExpenseEntry.objects.count() == 0

    def test_expense_disappears_when_payment_is_undone(self):
        booking = _booking(_event(), status=SupplierBooking.STATUS_PAID)
        sync_expense(booking)
        booking.status = SupplierBooking.STATUS_CONFIRMED
        booking.save(update_fields=["status"])
        sync_expense(booking)
        assert ExpenseEntry.objects.count() == 0

    def test_category_follows_kind(self):
        booking = _booking(
            _event(), kind=SupplierBooking.KIND_PERMIT, status=SupplierBooking.STATUS_PAID
        )
        sync_expense(booking)
        assert ExpenseEntry.objects.get().category == ExpenseEntry.CATEGORY_FEES


class TestMargin:
    def test_margin_counts_paid_and_planned_separately(self):
        event = _event()
        paid = _booking(event, cost_cents=30000, status=SupplierBooking.STATUS_PAID)
        sync_expense(paid)
        _booking(event, cost_cents=20000, status=SupplierBooking.STATUS_TO_BOOK)
        summary = event_margin(event)
        assert summary["spent"] == paid.cost_eur
        assert float(summary["planned"]) == 200.0
        # выручки нет → маржа отрицательная ровно на оплаченное
        assert float(summary["margin"]) == -300.0
        assert float(summary["margin_after_planned"]) == -500.0

    def test_open_items_counted(self):
        event = _event()
        _booking(event, status=SupplierBooking.STATUS_TO_BOOK)
        _booking(event, status=SupplierBooking.STATUS_REQUESTED)
        _booking(event, status=SupplierBooking.STATUS_PAID)
        assert event_margin(event)["open_items"] == 2

    def test_cancelled_booking_is_not_planned_spending(self):
        event = _event()
        _booking(event, cost_cents=50000, status=SupplierBooking.STATUS_CANCELLED)
        assert float(event_margin(event)["planned"]) == 0.0


class TestCabinet:
    def test_add_booking_stores_cost_in_cents(self):
        event = _event()
        views.event_logistics(
            _cab(
                "post",
                data={
                    "action": "add_booking",
                    "kind": "hotel",
                    "supplier_name": "Hotel Ibex",
                    "day": "4",
                    "stop": "Jispa",
                    "cost_eur": "420,50",
                    "currency": "inr",
                    "amount_original": "38000",
                },
            ),
            pk=event.pk,
        )
        booking = SupplierBooking.objects.get()
        assert booking.cost_cents == 42050  # немецкая запятая понята
        assert booking.currency == "INR"
        assert float(booking.amount_original) == 38000.0

    def test_status_change_syncs_expense(self):
        event = _event()
        booking = _booking(event)
        views.event_logistics(
            _cab(
                "post", data={"action": "booking_status", "id": str(booking.pk), "status": "paid"}
            ),
            pk=event.pk,
        )
        assert ExpenseEntry.objects.count() == 1

    def test_visibility_toggle(self):
        event = _event()
        booking = _booking(event)
        views.event_logistics(
            _cab("post", data={"action": "booking_visibility", "id": str(booking.pk)}), pk=event.pk
        )
        booking.refresh_from_db()
        assert booking.visible_to_participants is True

    def test_page_renders_costs_for_guide(self):
        event = _event()
        _booking(event, cost_cents=42000)
        body = views.event_logistics(_cab(), pk=event.pk).content.decode()
        assert "Hotel Ibex" in body


class TestChecklist:
    def test_add_and_toggle_task(self):
        event = _event()
        views.event_logistics(
            _cab("post", data={"action": "add_task", "title": "Inner Line Permits"}), pk=event.pk
        )
        task = TourTask.objects.get()
        assert not task.is_done
        views.event_logistics(
            _cab("post", data={"action": "toggle_task", "id": str(task.pk)}), pk=event.pk
        )
        task.refresh_from_db()
        assert task.is_done

    def test_overdue_only_when_open_and_past(self):
        event = _event()
        yesterday = timezone.localdate() - timezone.timedelta(days=1)
        task = TourTask.objects.create(event=event, title="TÜV", due_date=yesterday)
        assert task.is_overdue() is True
        task.done_at = timezone.now()
        assert task.is_overdue() is False
        assert TourTask.objects.create(event=event, title="Ohne Frist").is_overdue() is False
