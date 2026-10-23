"""FSM счёта (Track D / D4b). База — apps.core.fsm.

draft → issued → paid; сторно из issued/paid (номер сохраняется — нумерация
без дыр). После issued документ иммутабелен (правки блокирует вьюха).
"""

from apps.core.fsm import StateMachine, Transition


class InvoiceSM(StateMachine):
    transitions = [
        Transition("draft", "issued", "invoice.issued"),
        Transition("issued", "paid", "invoice.paid"),
        Transition("issued", "cancelled", "invoice.cancelled"),
        Transition("paid", "cancelled", "invoice.cancelled"),
    ]

    def on_transition(self, instance, t, **kw):
        # KA-D2: выручка заявки — при выставлении счёта, сторно — при отмене счёта.
        from .services import journal_invoice_revenue, reverse_invoice_revenue

        if t.dst == "issued":
            journal_invoice_revenue(instance)
        elif t.dst == "cancelled":
            reverse_invoice_revenue(instance)
