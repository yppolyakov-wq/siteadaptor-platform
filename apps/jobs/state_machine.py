"""FSM заявки/сметы Handwerker (G6, side-effects — F3). База — apps.core.fsm.

new (Anfrage) → quoted (Angebot) → accepted (beauftragt) → done (erledigt) →
invoiced (abgerechnet); выходы declined (клиент отклонил смету) и cancelled.
quoted → письмо клиенту со ссылкой на публичное Angebot; accepted/declined →
письмо владельцу (notifications dedupe).
"""

from apps.core.fsm import StateMachine, Transition


class JobSM(StateMachine):
    kind = "job"
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
        from . import services, status_presets
        from .notifications import enqueue_job_email

        # KA-H10: момент принятия фиксируется на ЛЮБОМ пути (кабинет, доска, вебхук,
        # витрина) — от него держится блокировка сметы.
        if t.dst == "accepted" and getattr(instance, "accepted_at", None) is None:
            from django.utils import timezone

            instance.accepted_at = timezone.now()
            type(instance).objects.filter(pk=instance.pk, accepted_at__isnull=True).update(
                accepted_at=instance.accepted_at
            )

        # B1.4/B1.6: отмена → вернуть использование/остаток Gutschein (однократно —
        # FSM не даёт второй переход в cancelled).
        if t.dst == "cancelled" and getattr(instance, "voucher_code", ""):
            from apps.promotions.services import unredeem_voucher, voucher_return_cents

            unredeem_voucher(instance.voucher_code, amount_cents=voucher_return_cents(instance))

        # VF-13: резерв Teile при принятии сметы (Beauftragt) — commit_stock
        # (кламп, идемпотентно); витрина не продаст заложенное под заявку.
        if t.dst == "accepted":
            services.commit_stock(instance)
            # B2-8d: фирме с депозитом — Anzahlungsrechnung (после коммита, fail-soft).
            from apps.finance.auto_invoice import advance_on_confirmed

            advance_on_confirmed("job", instance)
        # VF-13: отмена/отклонение возвращает зарезервированное (release гардится
        # stock_committed — quoted→declined без резерва склад не двигает).
        if t.dst in ("cancelled", "declined"):
            services.release_stock(instance)
            # B2-8c: неоплаченная Anzahlungsrechnung отменённой заявки — сторно.
            from apps.finance.advance import cancel_unpaid_for_deal

            cancel_unpaid_for_deal("job", instance)

        # G11: расходники (Teile) списаны не позже erledigt (обычно уже при
        # Beauftragt — VF-13; повтор идемпотентен).
        if t.dst == "done":
            services.commit_stock(instance)
            # A9: клиенту — Auftrag fertig (Repair-Status) + ссылка на страницу статуса.
            # KA-12 A-6b: после «Abholbereit» клиент уже знает, что машина готова —
            # второе письмо «Auftrag fertig» при выдаче было бы лишним.
            if t.src != status_presets.READY_CODE:
                enqueue_job_email(instance, "done", status_url=_status_url(instance))

        # KA-12 A-6b: свой статус «Abholbereit» (по коду, имя может быть другим) —
        # клиенту «можно забирать» со ссылкой на страницу статуса.
        if t.dst == status_presets.READY_CODE:
            enqueue_job_email(instance, "ready", status_url=_status_url(instance))

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


def _status_url(job) -> str:
    """Абсолютная ссылка на публичную страницу статуса заявки ('' без домена)."""
    from django.db import connection
    from django.urls import reverse

    from apps.promotions.notifications import _base_url

    base = _base_url(connection.schema_name)
    return f"{base}{reverse('storefront-auftrag', args=[job.public_token])}" if base else ""
