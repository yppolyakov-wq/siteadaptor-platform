"""KA-12 Zimmer Z-6 (E1.15): Kurtaxe-Meldung за месяц для общины.

Суммы — только из СНИМКА брони (`StayBooking.kurtaxe_cents`): правка ставки после брони
отчёт прошлых месяцев не переписывает. Бронь через границу месяца делится по ночам; остаток
копеек уходит последнему месяцу брони, поэтому Σ по месяцам = снимок. Имён гостей в отчёте
нет (это сумма для общины, не список гостей; список — выгрузка Meldescheine).
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from apps.core import status_registry


@dataclass(frozen=True)
class Row:
    booking: object
    nights: int  # ночей брони в этом месяце
    adult_nights: int
    child_nights: int
    free_child_nights: int  # ночи детей без сбора
    kurtaxe_cents: int

    @property
    def kurtaxe_eur(self):
        return Decimal(self.kurtaxe_cents) / 100


def _share(booking, first: date, end: date) -> tuple[int, int]:
    """(ночей в [first, end), доля снимка Kurtaxe в центах)."""
    total = (booking.departure - booking.arrival).days
    start = max(booking.arrival, first)
    stop = min(booking.departure, end)
    nights = max(0, (stop - start).days)
    if not total or not nights:
        return nights, 0
    before = max(0, (min(booking.departure, first) - booking.arrival).days)
    # Накопительно по ночам: доля = floor(всё_до_конца) − floor(всё_до_начала) — остаток
    # копеек достаётся последнему месяцу, Σ месяцев = снимок.
    upto_end = (booking.kurtaxe_cents * (before + nights)) // total
    upto_start = (booking.kurtaxe_cents * before) // total
    if before + nights == total:
        upto_end = booking.kurtaxe_cents
    return nights, upto_end - upto_start


def month_report(first: date, end: date, *, tenant=None, settings=None) -> dict:
    """Строки и итоги Kurtaxe за [first, end)."""
    from .models import StayBooking, StaySettings

    if settings is None:
        settings = StaySettings.objects.first() or StaySettings()
    statuses = status_registry.counted_statuses_for("stay", tenant)
    qs = (
        StayBooking.objects.filter(status__in=statuses, arrival__lt=end, departure__gt=first)
        .select_related("unit")
        .order_by("arrival", "reference_code")
    )
    rows = []
    for b in qs:
        nights, cents = _share(b, first, end)
        if not nights:
            continue
        child_nights = (b.children or 0) * nights
        free = child_nights if (settings.kurtaxe_children_free or not b.kurtaxe_cents) else 0
        rows.append(
            Row(
                booking=b,
                nights=nights,
                adult_nights=(b.adults or 0) * nights,
                child_nights=child_nights,
                free_child_nights=free,
                kurtaxe_cents=cents,
            )
        )
    return {
        "rows": rows,
        "bookings": len(rows),
        "adult_nights": sum(r.adult_nights for r in rows),
        "child_nights": sum(r.child_nights for r in rows),
        "free_child_nights": sum(r.free_child_nights for r in rows),
        "kurtaxe_cents": sum(r.kurtaxe_cents for r in rows),
        "kurtaxe_eur": Decimal(sum(r.kurtaxe_cents for r in rows)) / 100,
        "first": first,
        "last": end - timedelta(days=1),
        "label": settings.kurtaxe_label or "Kurtaxe",
    }
