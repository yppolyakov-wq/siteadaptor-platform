"""FSM заказа Click & Collect (Track D / D2). База — apps.core.fsm.

new → confirmed → ready → picked_up; отмена — из любого незавершённого статуса.
Внешние эффекты (письма клиенту по статусам) — D2b, через notifications dedupe.
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
