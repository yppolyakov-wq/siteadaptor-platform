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
