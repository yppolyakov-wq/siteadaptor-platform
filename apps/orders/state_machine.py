"""FSM заказа Click & Collect (Track D / D2). База — apps.core.fsm.

new → confirmed → ready → picked_up; отмена — из любого незавершённого статуса.
Каждый переход шлёт письмо клиенту через notifications dedupe (D2b).
"""

from apps.core.fsm import StateMachine, Transition


class OrderSM(StateMachine):
    transitions = [
        Transition("new", "confirmed", "order.confirmed"),
        Transition("new", "cancelled", "order.cancelled"),
        Transition("confirmed", "ready", "order.ready"),
        Transition("confirmed", "cancelled", "order.cancelled"),
        Transition("ready", "picked_up", "order.picked_up"),
        Transition("ready", "cancelled", "order.cancelled"),
    ]

    def on_transition(self, instance, t, **kw):
        from .notifications import enqueue_order_email

        enqueue_order_email(instance, t.dst)
