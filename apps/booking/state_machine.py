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
            from apps.promotions.services import unredeem_voucher

            # B1.5: balance-сертификату возвращается и списанная сумма (снимок).
            unredeem_voucher(
                instance.voucher_code, amount_cents=getattr(instance, "discount_cents", 0)
            )

        # MX-2e: отмена возвращает stock-опции записи (идемпотентно; зеркало —
        # status_effects.restore_stock_for).
        if t.dst == "cancelled":
            from apps.core import option_trackers

            option_trackers.release_options("booking", instance)

        # Услуга выполнена (G10) → выручка в журнал (НДС 19 %, идемпотентно по
        # source_ref). Общие брони без цены (стол/комната) выручку не пишут.
        if t.dst == "fulfilled" and instance.total_cents:
            from decimal import Decimal

            from apps.finance.services import record_revenue

            record_revenue(
                source="booking",
                source_ref=str(instance.id),
                amount=Decimal(instance.total_cents) / 100,  # #7: услуга + Extras
                vat_rate=Decimal("19.00"),
                customer=instance.customer,
                note=instance.reference_code,
            )
