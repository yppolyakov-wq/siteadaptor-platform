"""DC-5: скидка владельца на карточке ЛЮБОЙ сделки (ТЗ владельца 2026-08-25).

Правка ТЗ: «добавить поле скидка… при указании скидки учитываться в общей цене»,
и по макету блок скидки стоит МЕЖДУ составом и суммами. Поле `discount_cents`
уже есть у всех четырёх видов сделок (у заказа его же использует промокод —
SH-7), поэтому волна идёт БЕЗ миграций; здесь — единая точка применения:
приёмник один, а как пересчитать итог, знает домен.

Итог после скидки:
* заказ — `orders.editing.set_discount` (склад/леджер/письма прежние);
* запись услуги — `Booking.total_cents` = price + extras − discount (property);
* заявка — `Job.payable_gross` = брутто − скидка (счёт остаётся на gross);
* бронь номера — `total_cents` хранится, поэтому пересчитываем его по той же
  формуле, что `reprice`: (ночи − авто-скидка + допы) − скидка + Kurtaxe.
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

# kind → (поле причины/кода, максимальная длина причины)
NOTE_FIELDS = {
    "order": ("voucher_code", 12),
    "booking": ("voucher_code", 20),
    "stay": ("voucher_code", 20),
    "job": ("voucher_code", 20),
}

SUPPORTED = tuple(NOTE_FIELDS)


def supports(kind: str, obj=None) -> bool:
    """Скидку показываем там, где у сделки есть поле и она ещё не закрыта."""
    if kind not in SUPPORTED:
        return False
    return obj is None or hasattr(obj, "discount_cents")


def label_for(kind: str):
    return _("Rabatt")


def set_discount(kind: str, obj, *, cents: int, note: str = "", tenant=None):
    """Поставить скидку и пересчитать итог сделки. Возвращает новый итог (центы)."""
    cents = max(int(cents or 0), 0)
    field, limit = NOTE_FIELDS[kind]
    if kind == "order":
        from apps.orders import editing as order_editing

        order_editing.set_discount(obj, cents=cents, note=note[:limit], tenant=tenant)
        obj.refresh_from_db()
        return int(round(float(obj.total) * 100))

    obj.discount_cents = cents
    updated = ["discount_cents", "updated_at"]
    if note:
        setattr(obj, field, note[:limit])
        updated.insert(1, field)

    if kind == "stay":
        # Бронь номера хранит итог полем — пересчитываем той же формулой, что
        # `stays.services.reprice` (иначе показанная сумма разошлась бы с оплатой).
        from apps.core import extras as extras_engine

        lodging = _stay_lodging_cents(obj, extras_engine)
        obj.total_cents = max(0, lodging - cents) + obj.kurtaxe_cents
        updated.insert(1, "total_cents")

    obj.save(update_fields=updated)
    return _total_cents(kind, obj)


def _stay_lodging_cents(booking, extras_engine) -> int:
    """Стоимость проживания брони ДО скидки владельца (ночи − авто-скидка + допы)."""
    from apps.stays import pricing

    room = pricing.quote_total_cents(
        booking.unit, booking.arrival, booking.departure, rate_plan=booking.rate_plan
    )
    return max(0, room - booking.auto_discount_cents) + extras_engine.total_cents(booking.extras)


def _total_cents(kind: str, obj) -> int:
    if kind == "job":
        return int(round(float(obj.payable_gross) * 100))
    return int(getattr(obj, "total_cents", 0) or 0)
