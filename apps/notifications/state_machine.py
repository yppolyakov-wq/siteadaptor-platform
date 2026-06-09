"""Машина состояний уведомления. База — apps.core.fsm.

    pending ──► sent
       └─────► failed ──► pending (retry)

Смена статуса — только через apply(). Внешняя отправка (адаптер канала) — в
задаче apps.notifications.tasks.send_notification (S6.2).
"""

from apps.core.fsm import StateMachine, Transition

PENDING = "pending"
SENT = "sent"
FAILED = "failed"


class NotificationSM(StateMachine):
    transitions = [
        Transition(PENDING, SENT, "notification.sent"),
        Transition(PENDING, FAILED, "notification.failed"),
        Transition(FAILED, PENDING, "notification.requeued"),
    ]
