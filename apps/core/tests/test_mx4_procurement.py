"""MX-4: закупка от проданных опций — SupplierBooking вне туров.

План mx-execution-plan §MX-4: qty из проданного, дедуп открытой заявки,
generic-ссылка расхода; «Bezahlt» пишет расход и вне заезда.
"""

import pytest

from apps.core import zusatz
from apps.core.models import Extra
from apps.events.logistics import SupplierBooking
from apps.events.tour_finance import sync_expense
from apps.finance.expenses import ExpenseEntry
from apps.inventory.models import Lieferant

pytestmark = pytest.mark.django_db


def _purchase_option(**kw):
    supplier = Lieferant.objects.create(name="Moto-Verleih Manali")
    kw.setdefault("label", "Royal Enfield 411 mieten")
    kw.setdefault("price_cents", 50000)
    kw.setdefault("scope", Extra.SCOPE_EVENTS)
    kw.setdefault("tracker", Extra.TRACKER_PURCHASE)
    return Extra.objects.create(supplier=supplier, **kw)


def test_order_from_option_creates_standalone_booking():
    opt = _purchase_option()
    sb, created = zusatz.order_from_option(opt, qty=6)
    assert created and sb.event_id is None
    assert sb.ref_kind == "extra" and sb.ref_id == str(opt.pk)
    assert sb.qty == 6 and sb.supplier == opt.supplier
    assert sb.status == SupplierBooking.STATUS_TO_BOOK


def test_order_from_option_dedupes_open_booking():
    opt = _purchase_option()
    first, created1 = zusatz.order_from_option(opt, qty=6)
    second, created2 = zusatz.order_from_option(opt, qty=8)
    assert created1 and not created2 and first.pk == second.pk
    # закрытая заявка дедуп не держит — новая потребность = новая заявка
    first.status = SupplierBooking.STATUS_PAID
    first.save(update_fields=["status"])
    third, created3 = zusatz.order_from_option(opt, qty=2)
    assert created3 and third.pk != first.pk


def test_paid_standalone_booking_writes_expense_with_ref():
    """Расход поставщика больше не требует заезда (было: event FK обязателен)."""
    opt = _purchase_option()
    sb, _created = zusatz.order_from_option(opt, qty=4)
    sb.cost_cents = 80000
    sb.status = SupplierBooking.STATUS_PAID
    sb.save(update_fields=["cost_cents", "status"])
    sync_expense(sb)
    e = ExpenseEntry.objects.get(source=ExpenseEntry.SOURCE_SUPPLIER)
    assert e.event_id is None
    assert e.ref_kind == "extra" and e.ref_id == str(opt.pk)
    # откат статуса снимает расход (паритет с логистикой туров)
    sb.status = SupplierBooking.STATUS_CONFIRMED
    sb.save(update_fields=["status"])
    sync_expense(sb)
    assert not ExpenseEntry.objects.filter(source=ExpenseEntry.SOURCE_SUPPLIER).exists()
