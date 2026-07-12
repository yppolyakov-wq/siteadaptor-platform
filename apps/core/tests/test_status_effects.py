"""FB-3 Вариант B Phase 2: резолверы эффектов статусов (для кастом-статусов).

Резолверы зеркалят встроенные on_transition (те же source/source_ref/amount/vat) →
идемпотентность finance защищает от двойного списания. apply_custom_effects — ролевой
диспетчер (revenue при done-флаге; restore+unredeem+reversal при роли cancelled).
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.core import status_effects
from apps.core.status_registry import StatusDescriptor

pytestmark = pytest.mark.django_db


def _entries(source, ref):
    from apps.finance.models import RevenueEntry

    return RevenueEntry.objects.filter(source=source, source_ref=ref)


# --- revenue per kind (стаб: резолвер читает только атрибуты) ------------------


def test_revenue_order_idempotent():
    o = SimpleNamespace(
        id="o1", total=Decimal("8.00"), currency="EUR", customer=None, reference_code="R1"
    )
    status_effects.record_revenue_for("order", o)
    e = _entries("order", "o1")
    assert e.count() == 1 and e.first().amount == Decimal("8.00")
    status_effects.record_revenue_for("order", o)  # повтор → без дубля (source_ref)
    assert _entries("order", "o1").count() == 1


@pytest.mark.parametrize(
    ("kind", "source", "vat"),
    [("booking", "booking", "19.00"), ("stay", "stay", "7.00"), ("ticket", "event", "19.00")],
)
def test_revenue_cents_kinds_with_vat(kind, source, vat):
    inst = SimpleNamespace(id=f"{kind}1", total_cents=5000, customer=None, reference_code="R")
    status_effects.record_revenue_for(kind, inst)
    e = _entries(source, f"{kind}1").first()
    assert e is not None and e.amount == Decimal("50.00") and e.vat_rate == Decimal(vat)


def test_revenue_booking_zero_skipped():
    inst = SimpleNamespace(id="b0", total_cents=0, customer=None, reference_code="R")
    status_effects.record_revenue_for("booking", inst)
    assert _entries("booking", "b0").count() == 0


def test_revenue_reservation_price_times_qty():
    promo = SimpleNamespace(new_price=Decimal("4.00"), currency="EUR")
    inst = SimpleNamespace(
        id="res1", promotion=promo, quantity=3, customer=None, reference_code="R"
    )
    status_effects.record_revenue_for("reservation", inst)
    assert _entries("reservation", "res1").first().amount == Decimal("12.00")


def test_job_revenue_is_noop():
    status_effects.record_revenue_for("job", SimpleNamespace(id="j1"))
    from apps.finance.models import RevenueEntry

    assert not RevenueEntry.objects.filter(source__in=("job",)).exists()


# --- reversal (order нетится точным встроенным ref) ---------------------------


def test_reversal_order_nets_to_zero():
    o = SimpleNamespace(
        id="rv1", total=Decimal("8.00"), currency="EUR", customer=None, reference_code="R"
    )
    status_effects.record_revenue_for("order", o)
    status_effects.record_reversal_for("order", o)
    from apps.finance.models import RevenueEntry

    net = sum(
        e.amount for e in RevenueEntry.objects.filter(source="order", source_ref__startswith="rv1")
    )
    assert net == Decimal("0.00")
    assert _entries("order", "rv1:return").first().amount == Decimal("-8.00")


# --- restore_stock (order — реальный заказ) -----------------------------------


def test_restore_stock_order_increments_and_ledgers():
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders.services import create_order

    p = ProductFactory(base_price=Decimal("5.00"), stock_quantity=20)
    order = create_order(items=[(p, 3)], name="X", email="x@t.de")
    p.refresh_from_db()
    before = p.stock_quantity
    status_effects.restore_stock_for("order", order)
    p.refresh_from_db()
    assert p.stock_quantity == before + 3  # вернулись 3 шт


# --- диспетчер apply_custom_effects (monkeypatch резолверов) ------------------


@pytest.fixture
def _capture(monkeypatch):
    calls = []
    monkeypatch.setattr(status_effects, "record_revenue_for", lambda k, i: calls.append(("rev", k)))
    monkeypatch.setattr(
        status_effects, "restore_stock_for", lambda k, i: calls.append(("stock", k))
    )
    monkeypatch.setattr(status_effects, "unredeem_for", lambda i: calls.append("unredeem"))
    monkeypatch.setattr(
        status_effects, "record_reversal_for", lambda k, i: calls.append(("reversal", k))
    )
    return calls


def _desc(role, revenue=False):
    return StatusDescriptor(
        code="c", role=role, stage="done", revenue_recognized=revenue, builtin=False
    )


def test_dispatch_done_records_revenue(_capture):
    status_effects.apply_custom_effects("order", object(), None, _desc("done", revenue=True))
    assert _capture == [("rev", "order")]


def test_dispatch_active_fires_nothing(_capture):
    status_effects.apply_custom_effects("order", object(), None, _desc("active"))
    assert _capture == []


def test_dispatch_cancel_restores_and_unredeems(_capture):
    status_effects.apply_custom_effects("booking", object(), _desc("active"), _desc("cancelled"))
    assert _capture == [("stock", "booking"), "unredeem"]


def test_dispatch_cancel_after_revenue_reverses(_capture):
    src = _desc("done", revenue=True)
    status_effects.apply_custom_effects("order", object(), src, _desc("cancelled"))
    assert _capture == [("stock", "order"), "unredeem", ("reversal", "order")]
