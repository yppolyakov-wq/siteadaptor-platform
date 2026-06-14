"""FSM события и билета (A6). База — apps.core.fsm.

EventSM: draft → published → cancelled (мероприятие). TicketSM: pending →
confirmed → attended, отмена из pending/confirmed. На confirmed билет пишет
выручку в журнал finance (НДС 19 %, source «event», идемпотентно по source_ref);
бесплатные события (amount 0) record_revenue пропускает. Письма — A6c.
"""

from apps.core.fsm import StateMachine, Transition


class EventSM(StateMachine):
    transitions = [
        Transition("draft", "published", "event.published"),
        Transition("draft", "cancelled", "event.cancelled"),
        Transition("published", "cancelled", "event.cancelled"),
        Transition("published", "draft", "event.unpublished"),
    ]


class TicketSM(StateMachine):
    transitions = [
        Transition("pending", "confirmed", "ticket.confirmed"),
        Transition("pending", "cancelled", "ticket.cancelled"),
        Transition("confirmed", "attended", "ticket.attended"),
        Transition("confirmed", "cancelled", "ticket.cancelled"),
    ]

    def on_transition(self, instance, t, **kw):
        # Продажа билета (подтверждён/оплачен) → выручка. НДС 19 % (стандарт; для
        # культурных мероприятий может быть 7 % — настраиваемо позже).
        if t.dst == "confirmed":
            from decimal import Decimal

            from apps.finance.services import record_revenue

            record_revenue(
                source="event",
                source_ref=str(instance.id),
                amount=Decimal(instance.total_cents) / 100,
                vat_rate=Decimal("19.00"),
                customer=instance.customer,
                note=instance.reference_code,
            )
