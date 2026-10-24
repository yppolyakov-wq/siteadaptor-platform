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
            from apps.core.money_contract import settle_invoice_deal

            settle_invoice_deal(instance)
        elif t.dst == "cancelled":
            from .services import create_storno

            reverse_invoice_revenue(instance)
            create_storno(instance)
