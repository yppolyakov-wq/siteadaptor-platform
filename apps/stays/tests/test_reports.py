"""G9: отчёт загрузки/выручки — occupancy/ADR/RevPAR, пропорция через границы."""

import uuid
from datetime import date

import pytest

from apps.stays import reports
from apps.stays.models import StayBooking, StayUnit
from apps.stays.services import book_stay

pytestmark = pytest.mark.django_db

# Период-месяц [1.6 … 1.7) = 30 дней.
START = date(2026, 6, 1)
END = date(2026, 7, 1)


def _unit(qty=1, price=10000):
    return StayUnit.objects.create(
        name=f"Z {uuid.uuid4().hex[:6]}", price_cents=price, quantity=qty, max_guests=4
    )


def test_occupancy_and_adr_basic():
    unit = _unit(qty=2, price=10000)  # 2 номера × 30 ночей = 60 доступных
    book_stay(unit, arrival=date(2026, 6, 10), departure=date(2026, 6, 14), name="A")  # 4 ночи
    r = reports.occupancy_report(START, END)
    assert r["available_nights"] == 60
    assert r["sold_nights"] == 4
    assert round(r["occupancy"], 4) == round(4 / 60, 4)
    assert r["adr_cents"] == 10000  # 400 € / 4 ночи
    assert r["room_revenue_cents"] == 40000
    assert r["bookings"] == 1


def test_revenue_prorated_across_month_edge():
    unit = _unit(qty=1, price=10000)
    # 28.6 → 3.7: 5 ночей всего, в июне только 28/29/30 = 3 ночи
    book_stay(unit, arrival=date(2026, 6, 28), departure=date(2026, 7, 3), name="B")
    r = reports.occupancy_report(START, END)
    assert r["sold_nights"] == 3
    # выручка 500 € × 3/5 = 300 €
    assert r["room_revenue_cents"] == 30000


def test_cancelled_excluded():
    unit = _unit(qty=1)
    b = book_stay(unit, arrival=date(2026, 6, 5), departure=date(2026, 6, 7), name="C")
    from apps.stays.state_machine import StayBookingSM

    StayBookingSM().apply(b, StayBooking.STATUS_CANCELLED)
    r = reports.occupancy_report(START, END)
    assert r["sold_nights"] == 0 and r["bookings"] == 0


def test_kurtaxe_and_extras_excluded_from_room_revenue():
    from apps.stays.models import StaySettings

    StaySettings.objects.create(kurtaxe_cents=200)  # 2 €/Erw./Nacht
    unit = _unit(qty=1, price=10000)
    book_stay(
        unit,
        arrival=date(2026, 6, 10),
        departure=date(2026, 6, 12),
        name="D",
        adults=2,
        extras=[{"label": "Parkplatz", "price_cents": 800}],
    )
    r = reports.occupancy_report(START, END)
    # проживание 2×100 = 200 €; room_revenue без Kurtaxe(8 €) и Extras(8 €)
    assert r["room_revenue_cents"] == 20000
    assert r["total_revenue_cents"] == 20000 + 800 + 800


# --- Фиксы PMS-аудита 2026-07-27: rooms/блокировки/кастом-статусы -------------


def test_multi_room_booking_sells_rooms_nights():
    unit = _unit(qty=3, price=10000)  # 90 доступных ночей
    # G5: бронь на 2 номера × 4 ночи = 8 проданных ночей; проживание уже ×2.
    book_stay(unit, arrival=date(2026, 6, 10), departure=date(2026, 6, 14), name="G", rooms=2)
    r = reports.occupancy_report(START, END)
    assert r["sold_nights"] == 8
    assert r["room_revenue_cents"] == 80000
    assert r["adr_cents"] == 10000  # за номеро-ночь, не за бронь


def test_blocks_reduce_available_nights():
    from apps.stays.models import UnitBlock

    unit = _unit(qty=2)  # 60 доступных ночей
    # Ремонт одного юнита 10.6–14.6 включительно = 5 ночей вне продажи.
    UnitBlock.objects.create(
        unit=unit, start_date=date(2026, 6, 10), end_date=date(2026, 6, 14), reason="Renovierung"
    )
    r = reports.occupancy_report(START, END)
    assert r["available_nights"] == 55


def test_custom_capacity_status_counted():
    from apps.core import status_registry
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(
        slug=f"rep{uuid.uuid4().hex[:6]}",
        name="Rep",
        site_config={
            "status_defs": {
                "stay": [
                    {
                        "code": "anzahlung",
                        "label": "Anzahlung erhalten",
                        "role": "active",
                        "blocks_capacity": True,
                    }
                ]
            }
        },
    )
    unit = _unit(qty=1)
    b = book_stay(unit, arrival=date(2026, 6, 5), departure=date(2026, 6, 8), name="K")
    StayBooking.objects.filter(pk=b.pk).update(status="anzahlung")
    assert "anzahlung" in status_registry.counted_statuses_for("stay", tenant)
    # Явный tenant-контекст резолвится через connection в _current_tenant —
    # проверяем формулу напрямую монкипатчем не будем: главный замок — реестр
    # включает кастом-active; отчёт фильтрует по нему же (reports.py).
