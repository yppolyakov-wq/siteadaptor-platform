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


def commit_stock_for(kind: str, instance) -> None:
    """SM-3 (зеркало G11): вход в done-роль для job списывает Teile — builtin вешает
    commit_stock на литерал t.dst=='done', кастом-статус миновал бы списание.
    commit_stock идемпотентен (гард stock_committed) — повторный builtin-done
    безопасен. Прочие kind склад на done не двигают."""
    if kind == "job":
        from apps.jobs.services import commit_stock

        commit_stock(instance)


def restore_stock_for(kind: str, instance) -> None:
    """Вернуть складской остаток/ёмкость при кастом-cancel. order — позиции заказа
    (тот же `_restore_stock` + леджер); reservation — остаток акции + waitlist;
    ticket — стоп активной рассрочки (зеркало R10e: не деньги, но тот же «возврат
    при отмене» — иначе beat продолжит off-session списания по отменённому билету);
    прочие kinds ёмкость освобождают сами (по blocks_capacity), склад не двигают.
    job — release_stock (VF-13: возврат резерва Teile; зеркало builtin-отмены,
    идемпотентно по леджеру + гард stock_committed)."""
    if kind == "ticket":
        from apps.events.models import InstallmentPlan

        plan = getattr(instance, "installment_plan", None)
        if plan is not None and plan.status == InstallmentPlan.STATUS_ACTIVE:
            plan.status = InstallmentPlan.STATUS_CANCELLED
            plan.save(update_fields=["status", "updated_at"])
        # MX-0: зеркало освобождения companion-брони проживания (built-in путь —
        # TicketSM.on_transition; без зеркала кастом-cancel держал койку занятой).
        if getattr(instance, "stay_booking_id", None):
            from apps.events.services import release_linked_stay

            release_linked_stay(instance)
        # MX-2e: зеркало возврата stock-опций билета.
        from apps.core import option_trackers

        option_trackers.release_options("ticket", instance)
    elif kind == "order":
        from apps.orders.state_machine import _restore_stock

        _restore_stock(instance)
    elif kind == "job":
        from apps.jobs.services import release_stock

        release_stock(instance)
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
    elif kind in ("booking", "stay"):
        # P3 «ценовой слой»: кастом-cancel брони из акции возвращает лимит
        # кампании — зеркало ветки BookingSM (та же семантика возврата).
        if getattr(instance, "promotion_id", None):
            from apps.promotions.price_layer import return_units

            return_units(instance.promotion_id, 1)
        # MX-2e: зеркало возврата stock-опций брони/записи.
        from apps.core import option_trackers

        option_trackers.release_options(kind, instance)


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

    SM-3: cancel-блок пропускается, если `src_desc` ТОЖЕ cancelled-роли — сделка уже
    отменена, склад/лимит/ваучер вернулись при входе туда (эти возвраты, в отличие от
    finance, НЕ идемпотентны). Второй слой той же защиты — custom_edges дропает
    cancel↔cancel рёбра.
    """
    if dst_desc is None:
        return
    if dst_desc.revenue_recognized:
        record_revenue_for(kind, instance)
    if dst_desc.role == "done":
        commit_stock_for(kind, instance)
    # VF-13 (зеркало резерва): кастом-статус job роли active, «держащий ёмкость»
    # (blocks_capacity — дефолт роли), резервирует Teile как builtin `accepted`
    # (commit_stock идемпотентен; builtin quoted/accepted сюда не попадают —
    # builtin=True отфильтрован раньше).
    if kind == "job" and dst_desc.role == "active" and dst_desc.blocks_capacity:
        commit_stock_for(kind, instance)
    if dst_desc.role == "cancelled":
        if src_desc is not None and src_desc.role == "cancelled":
            return
        restore_stock_for(kind, instance)
        unredeem_for(instance)
        if src_desc is not None and src_desc.revenue_recognized:
            record_reversal_for(kind, instance)
