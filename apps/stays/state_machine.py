"""FSM брони по датам (Track E / E1, side-effects — E3). База — apps.core.fsm.

pending → confirmed → fulfilled; отмена из pending/confirmed; no_show из
confirmed. Отмена освобождает ночи сама собой: занятость считается только по
ACTIVE_STATUSES. confirmed/cancelled шлют письмо клиенту (notifications dedupe);
fulfilled (выезд) пишет выручку в журнал finance (НДС 7 % — Beherbergung).
"""

from apps.core.fsm import StateMachine, Transition


class StayBookingSM(StateMachine):
    transitions = [
        Transition("pending", "confirmed", "stay.confirmed"),
        Transition("pending", "cancelled", "stay.cancelled"),
        Transition("confirmed", "fulfilled", "stay.fulfilled"),
        Transition("confirmed", "cancelled", "stay.cancelled"),
        Transition("confirmed", "no_show", "stay.no_show"),
    ]

    def on_transition(self, instance, t, **kw):
        if t.dst in ("confirmed", "cancelled"):
            from .notifications import enqueue_stay_email

            enqueue_stay_email(instance, t.dst)

        # Выезд → запись в журнал выручки (идемпотентно по source_ref). НДС 7 %
        # — размещение (Beherbergung) льготная ставка; завтрак/доп — вне v1.
        if t.dst == "fulfilled":
            from decimal import Decimal

            from apps.finance.services import record_revenue

            record_revenue(
                source="stay",
                source_ref=str(instance.id),
                amount=Decimal(instance.total_cents) / 100,
                vat_rate=Decimal("7.00"),
                customer=instance.customer,
                note=instance.reference_code,
            )
