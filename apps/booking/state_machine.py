"""FSM записи по времени (Track D / D3). База — apps.core.fsm.

pending → confirmed → fulfilled; отмена из pending/confirmed; no_show из
confirmed. Отмена освобождает слот сама собой: пересечения считаются только по
ACTIVE_STATUSES. confirmed/cancelled шлют письмо клиенту (notifications dedupe).
"""

from apps.core.fsm import StateMachine, Transition


class BookingSM(StateMachine):
    kind = "booking"
    transitions = [
        Transition("pending", "confirmed", "booking.confirmed"),
        Transition("pending", "cancelled", "booking.cancelled"),
        Transition("confirmed", "fulfilled", "booking.fulfilled"),
        Transition("confirmed", "cancelled", "booking.cancelled"),
        Transition("confirmed", "no_show", "booking.no_show"),
    ]

    def on_transition(self, instance, t, **kw):
        if t.dst == "confirmed":
            from apps.finance.auto_invoice import on_confirmed

            on_confirmed("booking", instance)  # CO-2d: «Kauf auf Rechnung» → счёт
        if t.dst in ("confirmed", "cancelled"):
            from .notifications import enqueue_booking_email

            enqueue_booking_email(instance, t.dst)

        # P3 «ценовой слой»: бронь из акции возвращает лимит кампании (однократно
        # — FSM не даёт второй переход в cancelled; no_show лимит НЕ возвращает:
        # слот потрачен). Зеркало кастом-статусов — status_effects.
        if t.dst == "cancelled" and getattr(instance, "promotion_id", None):
            from apps.promotions.price_layer import return_units

            return_units(instance.promotion_id, 1)

        # B1.4: отмена → вернуть использование промокода/Gutschein (однократно —
        # FSM не даёт второй переход в cancelled).
        if t.dst == "cancelled" and getattr(instance, "voucher_code", ""):
            from apps.promotions.services import unredeem_voucher, voucher_return_cents

            # B1.5: balance-сертификату возвращается и списанная сумма (снимок).
            unredeem_voucher(instance.voucher_code, amount_cents=voucher_return_cents(instance))

        # MX-2e: отмена возвращает stock-опции записи (идемпотентно; зеркало —
        # status_effects.restore_stock_for).
        if t.dst == "cancelled":
            from apps.core import option_trackers

            option_trackers.release_options("booking", instance)

        # Услуга выполнена (G10) → выручка в журнал (идемпотентно по source_ref).
        # KA-H7: ставка — снимок записи (§ 19 → 0), визит по карте пишет только
        # Extras (сама услуга проведена при продаже карты). Общие брони без цены
        # (стол/комната) выручку не пишут.
        if t.dst == "fulfilled":
            # KA-MC X1: оплата на месте получена при исполнении (решение владельца).
            from apps.core.money_contract import settle_on_delivery

            settle_on_delivery("booking", instance)

        if t.dst == "fulfilled" and instance.total_cents:
            from apps.booking.revenue import revenue_for
            from apps.finance.services import record_revenue

            amount, rate = revenue_for(instance)
            record_revenue(
                source="booking",
                source_ref=str(instance.id),
                amount=amount,
                vat_rate=rate,
                customer=instance.customer,
                note=instance.reference_code,
            )
