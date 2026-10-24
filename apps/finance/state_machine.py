"""FSM счёта (Track D / D4b). База — apps.core.fsm.

draft → issued → paid; отмена из issued/paid. KA-12 E1.1: отмена выпускает
Stornorechnung — отдельный документ со своим номером и суммами со знаком минус;
оригинал не меняется (GoBD). Сама Stornorechnung переходов не имеет.
"""

from django.db import transaction

from apps.core.fsm import IllegalTransition, StateMachine, Transition


class InvoiceSM(StateMachine):
    transitions = [
        Transition("draft", "issued", "invoice.issued"),
        Transition("issued", "paid", "invoice.paid"),
        Transition("issued", "cancelled", "invoice.cancelled"),
        Transition("paid", "cancelled", "invoice.cancelled"),
    ]

    def apply(self, instance, dst, **kw):
        kind = getattr(instance, "kind", "invoice")
        if kind in ("storno", "credit"):  # B2-7b: корректура тоже без переходов
            raise IllegalTransition(f"invoice({kind})", instance.status, dst)
        if (
            dst == "cancelled"
            and kind == "advance"
            # B2-8c: вычет «живой», пока итоговый счёт не сторнирован (строки — снимок).
            and instance.deducted_in.exclude(final__status="cancelled").exists()
        ):
            # B2-8c: вычтенную предоплату не сторнируют — сначала итоговый счёт.
            raise IllegalTransition("invoice(advance, deducted)", instance.status, dst)
        if kind == "advance":
            # B2-8b (ревью): статус предоплаты и депозит сделки — одно целое; сделка
            # блокируется ПЕРВОЙ (как в sync_advance_paid) — порядок замков один.
            from .advance import lock_deal

            with transaction.atomic():
                if instance.deal_kind in ("stay", "booking", "job") and instance.deal_id:
                    lock_deal(instance.deal_kind, instance.deal_id)
                return super().apply(instance, dst, **kw)
        if dst == "cancelled":
            # Ревью W1.2 (H1): отмена и Stornorechnung — одно целое; сбой при выпуске
            # сторно откатывает и статус оригинала (иначе «Storniert» без документа).
            with transaction.atomic():
                return super().apply(instance, dst, **kw)
        return super().apply(instance, dst, **kw)

    def on_transition(self, instance, t, **kw):
        # KA-D2: выручка заявки — при выставлении счёта, сторно — при отмене счёта.
        from .services import journal_invoice_revenue, reverse_invoice_revenue

        if t.dst == "issued":
            journal_invoice_revenue(instance)
        elif t.dst == "paid":
            # KA-MC X3: оплаченный счёт закрывает и сделку, из которой выставлен.
            if getattr(instance, "kind", "invoice") == "advance":
                # B2-8b: оплачена предоплата → на сделке только депозит.
                from .advance import on_advance_paid

                on_advance_paid(instance, source=kw.get("source", "invoice"))
                return
            from apps.core.money_contract import settle_invoice_deal

            settle_invoice_deal(instance)
        elif t.dst == "cancelled":
            from .services import create_storno

            reverse_invoice_revenue(instance)
            storno = create_storno(instance)
            if getattr(instance, "kind", "") == "advance" and instance.sent_at:
                # B2-8d: клиент получил Anzahlungsrechnung — письмо «nicht mehr zahlen».
                from .advance import mail_storno

                mail_storno(instance, storno)
