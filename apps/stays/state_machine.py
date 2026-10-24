"""FSM брони по датам (Track E / E1, side-effects — E3). База — apps.core.fsm.

pending → confirmed → fulfilled; отмена из pending/confirmed; no_show из
confirmed. Отмена освобождает ночи сама собой: занятость считается только по
ACTIVE_STATUSES. confirmed/cancelled шлют письмо клиенту (notifications dedupe);
fulfilled (выезд) пишет выручку в журнал finance (НДС 7 % — Beherbergung).
"""

from apps.core.fsm import StateMachine, Transition


class StayBookingSM(StateMachine):
    kind = "stay"
    transitions = [
        Transition("pending", "confirmed", "stay.confirmed"),
        Transition("pending", "cancelled", "stay.cancelled"),
        Transition("confirmed", "fulfilled", "stay.fulfilled"),
        Transition("confirmed", "cancelled", "stay.cancelled"),
        Transition("confirmed", "no_show", "stay.no_show"),
    ]

    def on_transition(self, instance, t, **kw):
        if t.dst == "confirmed":
            from apps.finance.auto_invoice import on_confirmed

            on_confirmed("stay", instance)  # CO-2d: «Kauf auf Rechnung» → счёт
        if t.dst in ("confirmed", "cancelled"):
            from .notifications import enqueue_stay_email

            enqueue_stay_email(instance, t.dst)

        # P4 «ценовой слой»: бронь из акции возвращает лимит кампании (однократно
        # — FSM не даёт второй переход в cancelled; зеркало — status_effects).
        if t.dst == "cancelled" and getattr(instance, "promotion_id", None):
            from apps.promotions.price_layer import return_units

            return_units(instance.promotion_id, 1)

        # MX-2e: отмена возвращает stock-опции брони (идемпотентно; зеркало
        # кастом-статусов — status_effects.restore_stock_for).
        if t.dst == "cancelled":
            from apps.core import option_trackers

            option_trackers.release_options("stay", instance)

        # B1.4: отмена → вернуть использование промокода/Gutschein (однократно —
        # FSM не даёт второй переход в cancelled).
        if t.dst == "cancelled" and getattr(instance, "voucher_code", ""):
            from apps.promotions.services import unredeem_voucher, voucher_return_cents

            # B1.5: balance-сертификату возвращается и списанная сумма (снимок).
            unredeem_voucher(instance.voucher_code, amount_cents=voucher_return_cents(instance))

        # PMS-R4: выезд освобождает физический номер грязным — хаускипинг видит
        # его в списке уборки, стойка отмечает «Sauber».
        if t.dst == "fulfilled" and instance.room_id:
            from .models import Room

            Room.objects.filter(pk=instance.room_id).update(housekeeping=Room.HK_DIRTY)

        # Выезд → журнал выручки (идемпотентно по source_ref). KA-H6: проживание —
        # по снимку ставки брони, питание тарифа — отдельной записью 19 %.
        if t.dst == "fulfilled":
            # KA-MC X1: оплата на месте получена при исполнении (решение владельца).
            from apps.core.money_contract import settle_on_delivery

            settle_on_delivery("stay", instance)

            from apps.stays import meal

            meal.record_revenue(instance)
