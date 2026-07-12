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


# --- Phase 3b: хук apply() — эффекты ТОЛЬКО для кастом-статуса -----------------


def test_apply_hook_fires_for_custom_dst_only(monkeypatch):
    """apply() зовёт apply_custom_effects ТОЛЬКО для кастом-статуса (builtin=False);
    встроенный dst → no-op (эффекты уже в on_transition)."""
    import uuid
    from datetime import datetime, timedelta

    from django.utils import timezone

    from apps.booking import services
    from apps.booking.models import Resource
    from apps.core import fsm, status_registry
    from apps.core.status_registry import StatusDescriptor

    resource = Resource.objects.create(name=f"Tisch {uuid.uuid4().hex[:6]}")
    start = timezone.make_aware(datetime(2026, 7, 1, 12, 0))
    booking = services.book(resource, start=start, end=start + timedelta(hours=1), name="Gast")

    calls = []
    monkeypatch.setattr(
        status_effects, "apply_custom_effects", lambda k, i, s, d: calls.append((k, d.code))
    )
    custom = StatusDescriptor(code="wip", role="active", stage="in_progress", builtin=False)
    orig = status_registry.resolve
    monkeypatch.setattr(
        status_registry, "resolve", lambda k, s, t=None: custom if s == "wip" else orig(k, s, t)
    )

    class SM(fsm.StateMachine):
        kind = "booking"
        transitions = [
            fsm.Transition("pending", "wip", "x"),
            fsm.Transition("wip", "confirmed", "y"),
        ]

    SM().apply(booking, "wip")  # кастом dst → хук сработал
    assert calls == [("booking", "wip")]
    calls.clear()
    SM().apply(booking, "confirmed")  # встроенный dst → no-op
    assert calls == []


# --- Phase 3b-2: кастом-active статус держит ёмкость (anti-oversell) -----------


def test_custom_active_status_blocks_stay_capacity(monkeypatch):
    """FB-3 Вариант B: бронь в кастом-active статусе занимает номер (range_available=False),
    как built-in confirmed. Threading active_statuses_for в oversell-запросы."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.core import status_registry
    from apps.stays import availability, services
    from apps.stays.models import StayBooking, StayUnit
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(
        site_config={
            "status_defs": {
                "stay": [
                    {
                        "code": "beim_lieferanten",
                        "role": "active",
                        "stage": "in_progress",
                        "blocks_capacity": True,
                    }
                ]
            }
        }
    )
    monkeypatch.setattr(status_registry, "_current_tenant", lambda: tenant)

    unit = StayUnit.objects.create(name="Z1", price_cents=8000, quantity=1)
    arrival = timezone.localdate() + timedelta(days=10)
    dep = arrival + timedelta(days=2)
    booking = services.book_stay(unit, arrival=arrival, departure=dep, name="G")
    # переведём в кастом-active статус напрямую (легальный переход даст Phase 4)
    StayBooking.objects.filter(pk=booking.pk).update(status="beim_lieferanten")
    assert availability.range_available(unit, arrival, dep) is False  # номер занят кастом-active
    # контроль: снимем занятость (терминальный кастом не блокирует) → свободно
    StayBooking.objects.filter(pk=booking.pk).update(status="cancelled")
    assert availability.range_available(unit, arrival, dep) is True


# --- Phase 4: кастом-переходы через apply() (end-to-end) -----------------------


def test_custom_transition_reachable_via_apply(monkeypatch):
    """Phase 4: кастом-статус ДОСТИЖИМ через apply() (граф тенанта поверх FSM); держит
    ёмкость; allowed_targets включает кастом-ребро; нелегальный переход → IllegalTransition."""
    import uuid
    from datetime import datetime, timedelta

    import pytest as _pt
    from django.utils import timezone

    from apps.booking import services
    from apps.booking.models import Resource
    from apps.booking.state_machine import BookingSM
    from apps.core import status_registry
    from apps.core.fsm import IllegalTransition
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(
        site_config={
            "status_defs": {
                "booking": [
                    {
                        "code": "beim_lieferanten",
                        "role": "active",
                        "stage": "in_progress",
                        "blocks_capacity": True,
                    }
                ]
            },
            "status_edges": {
                "booking": [
                    {"src": "confirmed", "dst": "beim_lieferanten"},
                    {"src": "beim_lieferanten", "dst": "fulfilled"},
                ]
            },
        }
    )
    monkeypatch.setattr(status_registry, "_current_tenant", lambda: tenant)

    resource = Resource.objects.create(name=f"R {uuid.uuid4().hex[:6]}")
    start = timezone.make_aware(datetime(2026, 8, 1, 12, 0))
    end = start + timedelta(hours=1)
    b = services.book(resource, start=start, end=end, name="G")
    BookingSM().apply(b, "confirmed")  # built-in
    BookingSM().apply(b, "beim_lieferanten")  # кастом-ребро confirmed→custom легален
    b.refresh_from_db()
    assert b.status == "beim_lieferanten"
    # держит слот (кастом-active в oversell-запросе)
    assert services.overlapping(resource, start, end).filter(pk=b.pk).exists()
    # allowed_targets из кастом-статуса включает кастом-ребро → fulfilled
    assert "fulfilled" in BookingSM().allowed_targets("beim_lieferanten")
    # нелегальный переход (нет built-in и нет кастом-ребра) → IllegalTransition
    with _pt.raises(IllegalTransition):
        BookingSM().apply(b, "no_show")
    # кастом → built-in fulfilled (легально, on_transition встроенного fulfilled)
    BookingSM().apply(b, "fulfilled")
    b.refresh_from_db()
    assert b.status == "fulfilled"
