"""FSM брони по датам (Track E / E1). База — apps.core.fsm.

pending → confirmed → fulfilled; отмена из pending/confirmed; no_show из
confirmed. Отмена освобождает ночи сама собой: занятость считается только по
ACTIVE_STATUSES. Side-effects перехода (письма клиенту/владельцу + запись в
журнал выручки на fulfilled) подключаются в E3 — здесь чистая топология.
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
