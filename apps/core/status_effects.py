"""FB-3 Вариант B Phase 2: эффекты статусов по РОЛИ (для КАСТОМ-статусов).

Встроенные `on_transition` (apps/*/state_machine.py) НЕ трогаем — их исторические квирки
(order: `returned` не un-redeem'ит, `cancelled` un-redeem'ит; ticket cancel не сторнирует
выручку) сохранены точно. Этот модуль даёт ЧИСТУЮ ролевую семантику для кастом-статусов:

- вход в кастом-статус с `revenue_recognized` → запись выручки (per-kind резолвер);
- вход в кастом-статус роли `cancelled` → возврат склада + un-redeem ваучера + (если
  ПОКИДАЕМЫЙ статус был `revenue_recognized`) сторно выручки.

Резолверы зовут ТЕ ЖЕ `finance`/`inventory`/`promotions` функции с ТЕМИ ЖЕ `source`/
`source_ref`, что built-in (revenue — `source_ref=str(id)`). Поэтому идемпотентность
`record_revenue`/`record_reversal` по `(source, source_ref)` защищает от двойного списания,
даже если путь заказа проходит и через встроенный revenue-статус, и через кастомный.

Wired в `StateMachine.apply()` — Phase 3 (когда появятся кастом-определения); срабатывает
ТОЛЬКО для кастом-статуса (`descriptor.builtin is False`), built-in идёт прежним путём.
"""

from decimal import Decimal


def _cents_eur(instance) -> Decimal:
    return Decimal(getattr(instance, "total_cents", 0) or 0) / 100


def record_revenue_for(kind: str, instance) -> None:
    """Записать выручку для kind (аргументы 1:1 со встроенным on_transition; идемпотентно
    по source_ref=str(id))."""
    from apps.finance.services import record_revenue

    if kind == "order":
        record_revenue(
            source="order",
            source_ref=str(instance.id),
            amount=instance.total,
            currency=instance.currency,
            customer=instance.customer,
            note=instance.reference_code,
        )
    elif kind == "booking":
        if not getattr(instance, "total_cents", 0):
            return
        record_revenue(
            source="booking",
            source_ref=str(instance.id),
            amount=_cents_eur(instance),
            vat_rate=Decimal("19.00"),
            customer=instance.customer,
            note=instance.reference_code,
        )
    elif kind == "stay":
        record_revenue(
            source="stay",
            source_ref=str(instance.id),
            amount=_cents_eur(instance),
            vat_rate=Decimal("7.00"),
            customer=instance.customer,
            note=instance.reference_code,
        )
    elif kind == "ticket":
        record_revenue(
            source="event",
            source_ref=str(instance.id),
            amount=_cents_eur(instance),
            vat_rate=Decimal("19.00"),
            customer=instance.customer,
            note=instance.reference_code,
        )
    elif kind == "reservation":
        price = instance.promotion.new_price
        if price:
            record_revenue(
                source="reservation",
                source_ref=str(instance.id),
                amount=price * instance.quantity,
                currency=instance.promotion.currency,
                customer=instance.customer,
                note=instance.reference_code,
            )
    # job — выручка через invoice-флоу, не через статус


# source_ref сторно: order — точный встроенный `{id}:return` (нетится с built-in); прочие
# kinds своего reversal не имеют → `{id}:reversal` (сумма = проведённая выручка).
_REVERSAL_REF = {"order": "{id}:return"}


def record_reversal_for(kind: str, instance) -> None:
    """Сторнировать выручку kind (для кастом-cancel после revenue-статуса). Сумма = та же,
    что записывалась; идемпотентно по source_ref."""
    from apps.finance.services import record_reversal

    ref = _REVERSAL_REF.get(kind, "{id}:reversal").format(id=instance.id)
    note = f"Storno {getattr(instance, 'reference_code', instance.id)}"
    if kind == "order":
        record_reversal(
            source="order",
            source_ref=ref,
            amount=instance.total,
            currency=instance.currency,
            customer=instance.customer,
            note=note,
        )
    elif kind in ("booking", "stay", "ticket"):
        source = "event" if kind == "ticket" else kind
        record_reversal(
            source=source,
            source_ref=ref,
            amount=_cents_eur(instance),
            customer=instance.customer,
            note=note,
        )
    elif kind == "reservation":
        price = instance.promotion.new_price
        if price:
            record_reversal(
                source="reservation",
                source_ref=ref,
                amount=price * instance.quantity,
                currency=instance.promotion.currency,
                customer=instance.customer,
                note=note,
            )


def restore_stock_for(kind: str, instance) -> None:
    """Вернуть складской остаток/ёмкость при кастом-cancel. order — позиции заказа
    (тот же `_restore_stock` + леджер); reservation — остаток акции + waitlist; прочие
    kinds ёмкость освобождают сами (по blocks_capacity), склад не двигают."""
    if kind == "order":
        from apps.orders.state_machine import _restore_stock

        _restore_stock(instance)
    elif kind == "reservation":
        from django.db.models import F

        from apps.promotions.models import Promotion
        from apps.promotions.services import notify_waitlist_available

        Promotion.objects.filter(id=instance.promotion_id, available_quantity__isnull=False).update(
            available_quantity=F("available_quantity") + instance.quantity
        )
        promo = Promotion.objects.filter(id=instance.promotion_id).first()
        if promo is not None:
            notify_waitlist_available(promo)


def unredeem_for(instance) -> None:
    """Вернуть использование промокода/Gutschein (generic, как built-in cancel)."""
    code = getattr(instance, "voucher_code", "")
    if not code:
        return
    from apps.promotions.services import unredeem_voucher

    unredeem_voucher(code, amount_cents=getattr(instance, "discount_cents", 0))


def apply_custom_effects(kind: str, instance, src_desc, dst_desc) -> None:
    """Ролевые эффекты при ВХОДЕ в КАСТОМ-статус `dst_desc` (built-in не зовёт это).

    revenue_recognized → запись выручки; роль cancelled → возврат склада + un-redeem +
    (если покидаемый `src_desc` был revenue_recognized) сторно. Идемпотентность finance
    защищает от двойного, если путь проходит и через встроенный revenue-статус.
    """
    if dst_desc is None:
        return
    if dst_desc.revenue_recognized:
        record_revenue_for(kind, instance)
    if dst_desc.role == "cancelled":
        restore_stock_for(kind, instance)
        unredeem_for(instance)
        if src_desc is not None and src_desc.revenue_recognized:
            record_reversal_for(kind, instance)
