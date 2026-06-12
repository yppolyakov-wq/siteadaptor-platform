"""FSM записи по времени (Track D / D3). База — apps.core.fsm.

pending → confirmed → fulfilled; отмена из pending/confirmed; no_show из
confirmed. Отмена освобождает слот сама собой: пересечения считаются только по
ACTIVE_STATUSES. Письма (подтверждение/напоминание) — D3c через notifications.
"""

from apps.core.fsm import StateMachine, Transition


class BookingSM(StateMachine):
    transitions = [
        Transition("pending", "confirmed", "booking.confirmed"),
        Transition("pending", "cancelled", "booking.cancelled"),
        Transition("confirmed", "fulfilled", "booking.fulfilled"),
        Transition("confirmed", "cancelled", "booking.cancelled"),
        Transition("confirmed", "no_show", "booking.no_show"),
    ]
