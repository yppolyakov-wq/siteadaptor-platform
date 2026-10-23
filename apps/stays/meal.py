"""KA-H6 (аудит KA-5d, Z2): питание тарифа облагается 19 %, а не как проживание.

Aufteilungsgebot (§ 12 Abs. 2 Nr. 11 S. 2 UStG): льготные 7 % — только сама
Beherbergung; завтрак/полупансион — 19 %. Надбавка тарифа за питание
(`RatePlan.surcharge_cents`, снимок в `rate_snapshot`) прибавлялась к цене ночи и
уходила в счёт и журнал по ставке проживания.

Граница v1: отделяется только питание, заданное НАДБАВКОЙ за ночь. Если оно зашито
в процент тарифа или в базовую цену, его не отделить (форма тарифа предупреждает).
Правило «20 %-Pauschale» для пакетов (BMF) не реализуем — вопрос юристу.
"""

from __future__ import annotations

from decimal import Decimal

MEAL_VAT_RATE = Decimal("19.00")
ZERO = Decimal("0")


def lodging_cents(booking) -> int:
    """Проживание брутто (итог − допы − Kurtaxe + скидка ваучера), как в vat/счёте."""
    from apps.core import extras as extras_engine

    return max(
        0,
        int(booking.total_cents or 0)
        - int(booking.kurtaxe_cents or 0)
        - extras_engine.total_cents(booking.extras)
        + int(booking.discount_cents or 0),
    )


def meal_cents(booking) -> int:
    """Доля питания внутри проживания, центы (0 — питания нет / не отделимо)."""
    snap = getattr(booking, "rate_snapshot", None) or {}
    if not isinstance(snap, dict) or snap.get("meal_plan") in (None, "", "none"):
        return 0
    surcharge = int(snap.get("surcharge_cents") or 0)
    if surcharge <= 0:
        return 0
    nights = max(1, (booking.departure - booking.arrival).days)
    rooms = max(1, int(getattr(booking, "rooms", 1) or 1))
    raw = surcharge * nights * rooms
    lodging = lodging_cents(booking)
    # Авто-скидка (G4/Lücken) уменьшила проживание вместе с питанием — та же доля.
    before_discount = lodging + int(getattr(booking, "auto_discount_cents", 0) or 0)
    if before_discount > 0 and before_discount != lodging:
        raw = round(raw * lodging / before_discount)
    return max(0, min(raw, lodging))


def safe_meal_cents(booking) -> int:
    """meal_cents для любых объектов (стабы/частичные снимки) — 0 при нехватке полей."""
    try:
        return meal_cents(booking)
    except (AttributeError, TypeError, ValueError):
        return 0


def revenue_parts(booking, tenant=None) -> list[tuple[str, Decimal, Decimal]]:
    """KA-H6: части выручки брони для журнала: [(суффикс source_ref, сумма €, ставка)].

    Проживание и прочее — по снимку ставки брони (7 % по умолчанию), питание —
    отдельной записью «:meal» по 19 %; § 19 UStG → 0 %. Смешанные ставки допов
    v1 остаются в основной записи (разбивка журнала по ставкам отложена с VAT)."""
    from apps.booking.revenue import _tenant

    small = bool(getattr(_tenant(tenant), "small_business", False))
    snapshot = getattr(booking, "vat_rate", None)
    rate = Decimal("7.00") if snapshot is None else Decimal(str(snapshot))
    meal = safe_meal_cents(booking)
    main = int(booking.total_cents or 0) - meal
    parts = [("", Decimal(main) / 100, ZERO if small else rate)]
    if meal:
        parts.append((":meal", Decimal(meal) / 100, ZERO if small else MEAL_VAT_RATE))
    return parts


def record_revenue(booking, tenant=None) -> None:
    from apps.finance.models import RevenueEntry
    from apps.finance.services import record_revenue as record

    # Бронь до KA-H6 уже проведена одной записью на ВЕСЬ итог — повтор хука не
    # должен дописать «:meal» сверху (питание посчиталось бы дважды).
    legacy = RevenueEntry.objects.filter(source="stay", source_ref=str(booking.id)).first()
    if legacy is not None:
        return
    for suffix, amount, rate in revenue_parts(booking, tenant):
        record(
            source="stay",
            source_ref=f"{booking.id}{suffix}",
            amount=amount,
            vat_rate=rate,
            customer=booking.customer,
            note=booking.reference_code,
        )


def record_reversal(booking, ref: str, note: str) -> None:
    """Сторно = РОВНО проведённые записи (основная + «:meal»), каждая своей суммой."""
    from apps.finance.models import RevenueEntry
    from apps.finance.services import record_reversal as reverse

    for suffix in ("", ":meal"):
        entry = RevenueEntry.objects.filter(
            source="stay", source_ref=f"{booking.id}{suffix}"
        ).first()
        if entry is None:
            continue
        reverse(
            source="stay",
            source_ref=f"{ref}{suffix}",
            amount=entry.amount,
            customer=booking.customer,
            note=note,
        )
