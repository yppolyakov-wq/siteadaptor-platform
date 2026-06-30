"""FSM заявки/сметы Handwerker (G6, side-effects — F3). База — apps.core.fsm.

new (Anfrage) → quoted (Angebot) → accepted (beauftragt) → done (erledigt) →
invoiced (abgerechnet); выходы declined (клиент отклонил смету) и cancelled.
quoted → письмо клиенту со ссылкой на публичное Angebot; accepted/declined →
письмо владельцу (notifications dedupe).
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

    def on_transition(self, instance, t, **kw):
        from . import services
        from .notifications import enqueue_job_email

        # G11: расходники (Teile) списываются со склада при erledigt (один раз).
        if t.dst == "done":
            services.commit_stock(instance)
            # A9: клиенту — Auftrag fertig (Repair-Status) + ссылка на страницу статуса.
            from django.db import connection
            from django.urls import reverse

            from apps.promotions.notifications import _base_url

            base = _base_url(connection.schema_name)
            status_url = (
                f"{base}{reverse('storefront-auftrag', args=[instance.public_token])}"
                if base
                else ""
            )
            enqueue_job_email(instance, "done", status_url=status_url)

        if t.dst == "quoted":
            # Ссылку на публичное Angebot строим только при известном домене
            # (есть Domain) — в тестах base пуст, reverse не зовём.
            from django.db import connection
            from django.urls import reverse

            from apps.promotions.notifications import _base_url

            base = _base_url(connection.schema_name)
            url = (
                f"{base}{reverse('storefront-angebot', args=[instance.public_token])}"
                if base
                else ""
            )
            enqueue_job_email(instance, "quoted", angebot_url=url)
        elif t.dst in ("accepted", "declined"):
            enqueue_job_email(instance, t.dst)
