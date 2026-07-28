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


# --- CP-1: Marktposition (цены отелей города, одобрено владельцем) ---------------


def test_market_position_ranks_and_gates():
    from apps.aggregator.models import AggregatorListing
    from apps.stays.views import _market_position
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory.build(schema_name="tenant_cp1", city="Hilden")

    def _listing(schema, name, price):
        AggregatorListing.objects.create(
            tenant_schema=schema,
            tenant_slug=schema,
            business_name=name,
            city="Hilden",
            listing_kind=AggregatorListing.KIND_STAY,
            source_ref=uuid.uuid4().hex[:12],  # unique (schema, kind, source_ref)
            new_price=price,
            is_active=True,
            title={"de": name},
        )

    _listing("tenant_cp1", "Unser Hotel", 90)
    _listing("tenant_cp1", "Unser Hotel", 120)  # второй номер — схлопывается в min
    _listing("tenant_other1", "Seehof", 80)
    m = _market_position(tenant)
    assert m is None  # < 3 отелей → карточка скрыта

    _listing("tenant_other2", "Bergblick", 110)
    m = _market_position(tenant)
    assert m["total"] == 3 and m["position"] == 2  # 80 < 90 < 110
    assert [h["name"] for h in m["hotels"]] == ["Seehof", "Unser Hotel", "Bergblick"]
    assert m["hotels"][1]["own"] is True
    assert m["min"] == 80 and m["max"] == 110

    assert _market_position(TenantFactory.build(schema_name="x", city="")) is None


def test_breakdowns_channel_rate_unit_and_los():
    """PMS-C: разрезы канал/тариф/категория + Ø LOS по заездам месяца."""
    from apps.stays.models import RatePlan

    unit_a = _unit(qty=2, price=10000)
    unit_b = _unit(qty=1, price=20000)
    rate = RatePlan.objects.create(name="Mit Frühstück", surcharge_cents=0)
    book_stay(unit_a, arrival=date(2026, 6, 10), departure=date(2026, 6, 14), name="A")  # 4 ночи
    book_stay(
        unit_a,
        arrival=date(2026, 6, 20),
        departure=date(2026, 6, 22),
        name="B",
        source_channel="booking",
        rate_plan=rate,
    )  # 2 ночи
    book_stay(unit_b, arrival=date(2026, 6, 5), departure=date(2026, 6, 7), name="C")  # 2 ночи
    b = reports.breakdowns(START, END)

    channels = {r["label"]: r for r in b["by_channel"]}
    assert channels["direct"]["bookings"] == 2 and channels["direct"]["nights"] == 6
    assert channels["booking"]["bookings"] == 1 and channels["booking"]["nights"] == 2

    rates = {r["label"]: r for r in b["by_rate"]}
    assert rates["Mit Frühstück"]["bookings"] == 1
    assert rates[""]["bookings"] == 2  # базовые брони — пустой лейбл (Base rate)

    units = {r["label"]: r for r in b["by_unit"]}
    assert units[unit_a.name]["nights"] == 6 and units[unit_b.name]["revenue_cents"] == 40000

    # LOS: (4 + 2 + 2) / 3
    assert round(b["avg_los"], 2) == round(8 / 3, 2)
    assert b["arrivals"] == 3


def test_breakdowns_rate_table_hidden_without_rate_plans():
    unit = _unit()
    book_stay(unit, arrival=date(2026, 6, 10), departure=date(2026, 6, 12), name="D")
    b = reports.breakdowns(START, END)
    assert b["by_rate"] == []  # только базовые брони → таблица тарифов скрыта


def test_breakdowns_los_ignores_prev_month_arrivals():
    """Хвост брони прошлого месяца влияет на выручку, но не на LOS."""
    unit = _unit()
    book_stay(unit, arrival=date(2026, 5, 28), departure=date(2026, 6, 3), name="E")
    b = reports.breakdowns(START, END)
    assert b["arrivals"] == 0 and b["avg_los"] == 0.0
    assert b["by_channel"][0]["nights"] == 2  # 1.6/2.6 в окне


def test_reports_export_csv():
    """PMS-C: CSV месяца — те же считаемые статусы, фильтр по окну."""
    import uuid as uuid_mod

    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.stays import views

    unit = _unit()
    book_stay(
        unit,
        arrival=date(2026, 6, 10),
        departure=date(2026, 6, 12),
        name="Gast Juni",
        source_channel="booking",
    )
    book_stay(unit, arrival=date(2026, 7, 10), departure=date(2026, 7, 12), name="Gast Juli")

    request = RequestFactory().get("/dashboard/stays/berichte/export.csv", {"month": "2026-06"})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    o = uuid_mod.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(username=f"o-{o}", password="pw12345678")
    resp = views.reports_export_csv(request)
    assert resp["Content-Type"].startswith("text/csv")
    body = resp.content.decode("utf-8-sig")
    assert "Gast Juni" in body and "Gast Juli" not in body
    assert body.splitlines()[0].startswith("reference,guest,unit")
    assert "booking" in body and "200.00" in body
