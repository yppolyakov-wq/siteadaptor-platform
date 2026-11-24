"""Онлайн-депозит за date-range-бронь через Stripe Connect (Track E / E4).

Checkout создаётся НА connected account бизнеса (деньги идут ему; вариант B —
application_fee=0). Подтверждение оплаты ставит вебхук на public-схеме
(apps.billing.webhooks → mark_stay_paid), кросс-схемно через schema_context
(бронь живёт в TENANT-схеме). Зеркало apps.booking.payments (P2.5b).
"""

from apps.billing import connect
from apps.core.payment_holds import start_online_hold


def stay_deposit_checkout_url(booking, tenant, *, success_url: str, cancel_url: str) -> str:
    """URL Stripe-оплаты депозита за бронь (на connected account бизнеса)."""
    return connect.connected_checkout_session(
        connect_id=tenant.stripe_connect_id,
        amount_cents=booking.deposit_cents,
        product_name=f"Anzahlung {booking.reference_code}",
        metadata={
            "kind": "stay_deposit",
            "tenant_schema": tenant.schema_name,
            "booking_id": str(booking.id),
        },
        success_url=success_url,
        cancel_url=cancel_url,
        business_type=getattr(tenant, "business_type", ""),
        payment_method_types=getattr(tenant, "stripe_payment_methods", None),
        # KA-P6: брошенная оплата не держит ресурс бессрочно (expire_payment_holds).
        expires_at=start_online_hold(booking),
    )


def mark_stay_paid(
    *,
    tenant_schema: str,
    booking_id: str,
    payment_intent: str = "",
    amount_cents: int | None = None,
) -> bool:
    """Вебхук: депозит оплачен → payment_state=paid + авто-confirm (если юнит не
    требует ручного подтверждения). Кросс-схемно, идемпотентно.

    FB-33 D4b: строка — под блокировкой (`payment_holds.locked_deal`, как у заказа), вызовы
    Stripe — после неё. Второй платёж Stripe к сделке с уже записанным главным (решение
    владельца 2026-11-24: и у неотменённой) — строкой книги на `amount_cents` и назад
    только он (`settle_extra_payment`); главный intent не перезаписывается, у номера с
    «nicht erstatten» главный остаётся у бизнеса."""
    from django.db import transaction
    from django_tenants.utils import schema_context

    from apps.core import payment_holds
    from apps.core.fsm import IllegalTransition

    from .models import StayBooking
    from .state_machine import StayBookingSM

    if not tenant_schema or not booking_id:
        return False
    with schema_context(tenant_schema):
        with transaction.atomic():
            booking = payment_holds.locked_deal(StayBooking, booking_id)
            if booking is None:
                return False
            fields = []
            # KA-H6: Anzahlung меньше итога → «deposit» (остаток открыт), иначе «paid».
            # Уже полностью оплаченную (стойка) бронь вебхук не понижает.
            target = (
                StayBooking.PAYMENT_DEPOSIT
                if 0 < booking.deposit_cents < booking.total_cents
                else StayBooking.PAYMENT_PAID
            )
            # refunded не воскрешаем повтором вебхука (иначе возврат стал бы возможен снова).
            newly = booking.payment_state not in (
                target,
                StayBooking.PAYMENT_PAID,
                StayBooking.PAYMENT_REFUNDED,
            )
            extra = payment_holds.is_extra_payment(
                "stay", booking, payment_intent, newly_paid=newly
            )
            if newly:
                booking.payment_state = target
                fields.append("payment_state")
            # Главный платёж вторым не перезаписываем; главного нет (касса, потом онлайн) —
            # этот становится главным, как раньше.
            if (
                payment_intent
                and booking.stripe_payment_intent != payment_intent
                and (newly or not booking.stripe_payment_intent)
            ):
                booking.stripe_payment_intent = payment_intent
                fields.append("stripe_payment_intent")
            if booking.payment_due_at is not None:  # KA-P6: оплачено — удержание снято
                booking.payment_due_at = None
                fields.append("payment_due_at")
            from apps.core import folio

            if extra:
                payment_holds.record_extra_payment(
                    "stay", booking, intent=payment_intent, amount_cents=amount_cents
                )
            elif (
                "payment_state" in fields or "stripe_payment_intent" in fields
            ) and booking.payment_state != "refunded":
                # KA-12 B2-3: платёж в фолио ДО записи состояния (opening легаси);
                # новый intent пишется и у уже «оплаченной» сделки (поздний вебхук
                # после кассы) — иначе онлайн-деньги выпали бы из книги.
                folio.record_online("stay", booking, intent=payment_intent)
            if fields:
                fields.append("updated_at")
                booking.save(update_fields=fields)
        # ревью H3: возвраты, FSM и синк предоплаты — после блокировки строки
        payment_holds.settle_late_safely("stay", booking, newly_paid="payment_state" in fields)
        if extra:
            payment_holds.settle_extra_safely("stay", booking, intent=payment_intent)
        # Авто-подтверждение, если юнит не требует ручной проверки (анти-фрод).
        if not booking.unit.require_manual_confirm and booking.status == StayBooking.STATUS_PENDING:
            try:
                StayBookingSM().apply(booking, StayBooking.STATUS_CONFIRMED)
            except IllegalTransition:
                pass
        from apps.finance.advance import sync_advance_paid

        sync_advance_paid("stay", booking)  # B2-8b: депозит пришёл → предоплата оплачена
    return True
