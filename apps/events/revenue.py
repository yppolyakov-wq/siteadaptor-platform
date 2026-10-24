"""KA-H8: выручка билета для журнала (`finance.RevenueEntry`) — зеркало
`apps.booking.revenue` (KA-H7).

Было: брутто ДО скидки ваучера и жёсткие 19 %. Стало: к оплате (`payable_cents`;
подарочный сертификат уже проведён при продаже — иначе выручка задвоилась бы),
ставка — снимок билета (`Ticket.vat_rate`, DC-8), § 19 UStG → 0 %. Проживание
внутри билета v1 идёт той же записью (разбивка журнала по ставкам отложена).
"""

from __future__ import annotations

from decimal import Decimal

ZERO = Decimal("0")


def revenue_for(ticket, tenant=None) -> tuple[Decimal, Decimal]:
    from apps.booking.revenue import _tenant

    snapshot = getattr(ticket, "vat_rate", None)
    rate = Decimal("19.00") if snapshot is None else Decimal(str(snapshot))
    if getattr(_tenant(tenant), "small_business", False):
        rate = ZERO
    payable = getattr(ticket, "payable_cents", None)
    if payable is None:  # стабы/частичные объекты: брутто без скидки
        payable = getattr(ticket, "total_cents", 0) or 0
    return Decimal(payable) / 100, rate


def recorded_entry(ticket):
    from apps.finance.models import RevenueEntry

    return RevenueEntry.objects.filter(source="event", source_ref=str(ticket.id)).first()


def paid_on_site_later(ticket) -> bool:
    """KA-12 E1.7: билет «оплата на месте», денег ещё нет (ручной билет из кабинета).
    Это не выручка при подтверждении — она появится на входе (attended), когда
    `settle_on_delivery` отметит оплату. Vorkasse/счёт — настоящая дебиторка, их не трогаем."""
    from apps.core.money_contract import _CASH_METHODS

    state = getattr(ticket, "payment_state", "") or ""
    method = getattr(ticket, "payment_method", "") or ""
    return state in ("none", "unpaid", "") and method in _CASH_METHODS


def record_revenue(ticket, tenant=None) -> None:
    from apps.finance.services import record_revenue as record

    if paid_on_site_later(ticket):
        return
    amount, rate = revenue_for(ticket, tenant)
    record(
        source="event",
        source_ref=str(ticket.id),
        amount=amount,
        vat_rate=rate,
        customer=ticket.customer,
        note=ticket.reference_code,
    )


def record_reversal(
    ticket, ref: str | None = None, note: str = "", retained_cents: int = 0
) -> None:
    """Сторно = проведённая запись (сумма и ставка) МИНУС удержанное бизнесом
    (платная самоотмена гостя: Anzahlung остаётся — это выручка). Нет записи — нечего."""
    from apps.finance.services import record_reversal as reverse

    entry = recorded_entry(ticket)
    if entry is None:
        return
    amount = entry.amount - Decimal(max(0, int(retained_cents or 0))) / 100
    if amount <= 0:
        return
    reverse(
        source="event",
        source_ref=ref or f"{ticket.id}:reversal",
        amount=amount,
        vat_rate=entry.vat_rate,
        customer=ticket.customer,
        note=note or f"Storno {ticket.reference_code}",
    )
