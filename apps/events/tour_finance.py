"""Экономика заезда (MT-5): выручка билетов − расходы = маржа.

Выручку платформа уже пишет сама (`TicketSM` → `finance.RevenueEntry` с
`source="event"`), поэтому здесь только вторая половина: расход из книги
логистики и сводка. Расход заводится ОДИН раз на запись логистики — по
идемпотентному ключу `(source, source_ref)`, как у выручки.
"""

from decimal import Decimal

from django.db.models import Sum

#: Категория расхода по виду закупки — чтобы отчёт группировался осмысленно.
_CATEGORY_BY_KIND = {
    "hotel": "accommodation",
    "transport": "transport",
    "excursion": "fees",
    "permit": "fees",
    "guide": "staff",
}


def record_expense(booking) -> object | None:
    """Записать оплату поставщику в расходы. Повтор не создаёт дубль.

    Вызывается при переводе записи логистики в «Bezahlt»: до оплаты это план,
    а не расход.
    """
    from apps.finance.expenses import ExpenseEntry

    if booking.status != booking.STATUS_PAID or not booking.cost_cents:
        return None
    entry, _created = ExpenseEntry.objects.get_or_create(
        source=ExpenseEntry.SOURCE_SUPPLIER,
        source_ref=str(booking.pk),
        defaults={
            "amount": booking.cost_eur,
            "original_currency": booking.currency,
            "original_amount": booking.amount_original,
            "category": _CATEGORY_BY_KIND.get(booking.kind, ExpenseEntry.CATEGORY_OTHER),
            "date": booking.date or booking.created_at.date(),
            "event": booking.event,
            # MX-4: generic-ссылка расхода — маржа считается и вне туров.
            "ref_kind": booking.ref_kind or ("event" if booking.event_id else ""),
            "ref_id": booking.ref_id or (str(booking.event_id) if booking.event_id else ""),
            "note": f"{booking.get_kind_display()} · {booking.supplier_label}"[:200],
        },
    )
    return entry


def drop_expense(booking) -> int:
    """Снять расход, если оплата отменена (статус ушёл из «Bezahlt»)."""
    from apps.finance.expenses import ExpenseEntry

    deleted, _ = ExpenseEntry.objects.filter(
        source=ExpenseEntry.SOURCE_SUPPLIER, source_ref=str(booking.pk)
    ).delete()
    return deleted


def sync_expense(booking) -> None:
    """Привести расход в соответствие статусу записи логистики."""
    if booking.status == booking.STATUS_PAID and booking.cost_cents:
        record_expense(booking)
    else:
        drop_expense(booking)


def event_margin(event) -> dict:
    """Сводка по заезду: выручка, расходы (учтённые и плановые), маржа.

    `planned` — то, что ещё не оплачено: гид должен видеть будущий отток, иначе
    маржа выглядит красивее, чем есть.
    """
    from apps.finance.expenses import ExpenseEntry
    from apps.finance.models import RevenueEntry

    from .logistics import SupplierBooking

    revenue = RevenueEntry.objects.filter(
        source=RevenueEntry.SOURCE_EVENT, source_ref__in=_ticket_refs(event)
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    spent = ExpenseEntry.objects.filter(event=event).aggregate(total=Sum("amount"))[
        "total"
    ] or Decimal("0")
    planned_cents = (
        SupplierBooking.objects.filter(event=event)
        .exclude(status__in=(SupplierBooking.STATUS_PAID, SupplierBooking.STATUS_CANCELLED))
        .aggregate(total=Sum("cost_cents"))["total"]
        or 0
    )
    planned = Decimal(planned_cents) / 100
    return {
        "revenue": revenue,
        "spent": spent,
        "planned": planned,
        "margin": revenue - spent,
        "margin_after_planned": revenue - spent - planned,
        "open_items": SupplierBooking.objects.filter(
            event=event, status__in=SupplierBooking.OPEN_STATUSES
        ).count(),
    }


def _ticket_refs(event) -> list:
    """id билетов заезда — ключи, которыми выручка записана в журнал."""
    return [str(pk) for pk in event.tickets.values_list("pk", flat=True)]
