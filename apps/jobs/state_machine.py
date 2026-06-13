"""FSM заявки/сметы Handwerker (G6). База — apps.core.fsm.

new (Anfrage) → quoted (Angebot) → accepted (beauftragt) → done (erledigt) →
invoiced (abgerechnet); выходы declined (клиент отклонил смету) и cancelled.
Side-effects (письма клиенту/владельцу, timestamps, Rechnung) — F2/F3.
"""

from apps.core.fsm import StateMachine, Transition


class JobSM(StateMachine):
    transitions = [
        Transition("new", "quoted", "job.quoted"),
        Transition("new", "cancelled", "job.cancelled"),
        Transition("quoted", "accepted", "job.accepted"),
        Transition("quoted", "declined", "job.declined"),
        Transition("quoted", "cancelled", "job.cancelled"),
        Transition("accepted", "done", "job.done"),
        Transition("accepted", "cancelled", "job.cancelled"),
        Transition("done", "invoiced", "job.invoiced"),
    ]
