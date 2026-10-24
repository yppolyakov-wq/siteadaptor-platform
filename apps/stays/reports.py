"""Отчёты по загрузке/выручке (G9) — Belegung %, ADR, RevPAR, Umsatz.

Чистые вычисления над `StayBooking`/`StayUnit` для периода ``[start, end)`` —
без БД-побочек в самой формуле (кабинет вызывает и форматирует). Определения как
в индустрии:
- Belegung (occupancy) = проданные ночи / доступные ночи;
- ADR (Average Daily Rate) = Zimmer-Umsatz / проданные ночи (за номеро-ночь);
- RevPAR = Zimmer-Umsatz / доступные ночи (= ADR × Belegung);
- Zimmer-Umsatz = итог брони − Kurtaxe − Extras (только проживание/тариф);
  выручка через границы периода пропорциональна доле ночей в окне.

Фиксы PMS-аудита 2026-07-27: (1) мульти-номерная бронь (G5) продаёт
``overlap × rooms`` ночей — раньше Belegung занижался, ADR завышался в rooms
раз; (2) блокировки (ремонт/своё проживание) выводят по одному юниту за ночь
из знаменателя доступных ночей; (3) статусы — через реестр (кастом-статусы
тенанта, занимающие ёмкость, больше не выпадают из отчёта).
"""

from collections import defaultdict
from datetime import timedelta

from apps.core import status_registry

from .models import StayBooking, StayUnit, UnitBlock


def _extras_total(booking) -> int:
    return sum(int(e.get("price_cents", 0)) for e in (booking.extras or []))


def _is_external(source_id_ref: str, reason: str) -> bool:
    """KA-12 E4.8: блок «внешняя продажа» — импорт iCal или «Import-Konflikt» Channel
    Manager. Это проданная на OTA ночь, а не номер вне продажи."""
    return bool(source_id_ref) or "Import-Konflikt" in (reason or "")


def occupancy_report(start, end) -> dict:
    """Метрики за период ``[start, end)`` (start/end — date). Всё в центах.

    KA-12 E4.8: ручные блоки (ремонт/своё) выводят юнит из доступных ночей; внешние
    (iCal/OTA) — проданные ночи, но не больше свободного остатка юнита в эту ночь
    (iCal поверх своей брони — овербукинг, задваивать нельзя). ADR — по своей выручке
    (выручка OTA неизвестна), RevPAR — своя выручка на доступную ночь."""
    days = max(0, (end - start).days)
    units = list(StayUnit.objects.filter(is_active=True))
    qty = {u.pk: u.quantity for u in units}
    available_nights = sum(qty.values()) * days
    manual = defaultdict(int)  # (unit, день) → заблокировано вручную
    external = defaultdict(int)
    for unit_id, b_start, b_end, ref, reason in UnitBlock.objects.filter(
        unit__in=units, start_date__lt=end, end_date__gte=start
    ).values_list("unit_id", "start_date", "end_date", "source_id_ref", "reason"):
        bucket = external if _is_external(ref, reason) else manual
        day = max(b_start, start)
        last = min(b_end, end - timedelta(days=1))
        while day <= last:
            bucket[(unit_id, day)] += 1
            day += timedelta(days=1)
    available_nights = max(0, available_nights - sum(manual.values()))
    own_nights = 0
    room_rev = 0
    total_rev = 0
    bookings = 0
    own_by_day = defaultdict(int)
    qs = StayBooking.objects.filter(
        status__in=status_registry.counted_statuses_for("stay"),
        arrival__lt=end,
        departure__gt=start,
    )
    for b in qs:
        lo = max(b.arrival, start)
        hi = min(b.departure, end)
        overlap = (hi - lo).days
        if overlap <= 0:
            continue
        own_nights += overlap * b.rooms  # G5: бронь на N номеров продаёт N ночей/ночь
        day = lo
        while day < hi:
            own_by_day[(b.unit_id, day)] += b.rooms
            day += timedelta(days=1)
        bookings += 1
        frac = overlap / max(1, b.nights)  # доля ночей брони, попавших в окно
        room = max(0, b.total_cents - b.kurtaxe_cents - _extras_total(b))
        room_rev += round(room * frac)
        total_rev += round(b.total_cents * frac)
    external_nights = 0
    for key, count in external.items():
        free = qty.get(key[0], 0) - own_by_day.get(key, 0) - manual.get(key, 0)
        external_nights += max(0, min(count, free))
    sold_nights = own_nights + external_nights
    return {
        "days": days,
        "available_nights": available_nights,
        "sold_nights": sold_nights,
        "own_sold_nights": own_nights,
        "external_nights": external_nights,
        "bookings": bookings,
        "occupancy": (sold_nights / available_nights) if available_nights else 0.0,
        "adr_cents": round(room_rev / own_nights) if own_nights else 0,
        "revpar_cents": round(room_rev / available_nights) if available_nights else 0,
        "room_revenue_cents": room_rev,
        "total_revenue_cents": total_rev,
    }


def _window_bookings(start, end):
    """Брони, пересекающие окно ``[start, end)`` — считаемые статусы реестра."""
    return StayBooking.objects.filter(
        status__in=status_registry.counted_statuses_for("stay"),
        arrival__lt=end,
        departure__gt=start,
    )


def breakdowns(start, end) -> dict:
    """PMS-C: разрезы периода — канал/тариф/категория + Ø длина проживания.

    Та же пропорциональная выручка, что в occupancy_report (доля ночей в окне);
    LOS — по броням с ЗАЕЗДОМ в окне (индустриальная семантика: длина
    прибывшего проживания, хвосты прошлых месяцев её не размывают)."""
    by_channel: dict = {}
    by_rate: dict = {}
    by_unit: dict = {}
    los_total = 0
    los_n = 0
    for b in _window_bookings(start, end).select_related("unit"):
        lo = max(b.arrival, start)
        hi = min(b.departure, end)
        overlap = (hi - lo).days
        if overlap <= 0:
            continue
        frac = overlap / max(1, b.nights)
        revenue = round(b.total_cents * frac)
        nights = overlap * b.rooms
        channel = (b.source_channel or "").strip() or "direct"
        rate = (b.rate_snapshot or {}).get("name") or ""
        for bucket, key in ((by_channel, channel), (by_rate, rate), (by_unit, b.unit.name)):
            row = bucket.setdefault(key, {"bookings": 0, "nights": 0, "revenue_cents": 0})
            row["bookings"] += 1
            row["nights"] += nights
            row["revenue_cents"] += revenue
        if start <= b.arrival < end:
            los_total += b.nights
            los_n += 1

    def _rows(bucket):
        return [
            {"label": k, **v}
            for k, v in sorted(bucket.items(), key=lambda kv: -kv[1]["revenue_cents"])
        ]

    # Тарифный разрез скрываем, пока тарифы не используются (все брони базовые).
    rate_rows = _rows(by_rate) if any(k for k in by_rate) else []
    return {
        "by_channel": _rows(by_channel),
        "by_rate": rate_rows,
        "by_unit": _rows(by_unit),
        "avg_los": (los_total / los_n) if los_n else 0.0,
        "arrivals": los_n,
    }
