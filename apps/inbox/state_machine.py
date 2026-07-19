"""FSM статуса треда/тикета (M22a). База — apps.core.fsm.

open ↔ pending ↔ resolved → closed; reopen из любого «закрытого» в open. Side-
effects (письма клиенту при ответе владельца) — M22b через notifications.
"""

from apps.core.fsm import StateMachine, Transition


class ConversationSM(StateMachine):
    transitions = [
        Transition("open", "pending", "conv.pending"),
        Transition("open", "resolved", "conv.resolved"),
        Transition("open", "closed", "conv.closed"),
        Transition("pending", "open", "conv.reopen"),
        Transition("pending", "resolved", "conv.resolved"),
        Transition("pending", "closed", "conv.closed"),
        Transition("resolved", "open", "conv.reopen"),
        Transition("resolved", "closed", "conv.closed"),
        Transition("closed", "open", "conv.reopen"),
    ]

    def on_transition(self, instance, t, **kw):
        # LS-6 service recovery: решённый ПРОБЛЕМНЫЙ тред → мягкое «Alles wieder
        # gut?» клиенту (дедуп на тред; гейты email/unsubscribed внутри).
        if t.dst == "resolved" and instance.priority == "high":
            from .notifications import enqueue_recovery_email

            enqueue_recovery_email(instance)
