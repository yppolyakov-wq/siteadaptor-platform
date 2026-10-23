"""FSM события и билета (A6). База — apps.core.fsm.

EventSM: draft → published → cancelled (мероприятие). TicketSM: pending →
confirmed → attended, отмена из pending/confirmed. На confirmed билет пишет
выручку в журнал finance (source «event», идемпотентно по source_ref; KA-H8 — к
оплате по снимку ставки), отмена сторнирует проведённое. Письма — A6c.
"""

from apps.core.fsm import StateMachine, Transition


class EventSM(StateMachine):
    transitions = [
        Transition("draft", "published", "event.published"),
        Transition("draft", "cancelled", "event.cancelled"),
        Transition("published", "cancelled", "event.cancelled"),
        Transition("published", "draft", "event.unpublished"),
    ]

    def on_transition(self, instance, t, **kw):
        # Авто-листинг в агрегатор (A6): published → upsert, draft/cancelled →
        # remove. Через очередь; схема — из соединения (событие в TENANT-схеме);
        # сам upsert/remove решает задача (учитывает модуль + будущую дату).
        if t.dst in ("published", "draft", "cancelled"):
            from django.db import connection

            from apps.aggregator.tasks import sync_aggregator_event

            sync_aggregator_event.delay(
                dedupe_key=f"agg-event:{instance.id}:{t.dst}",
                tenant_schema=connection.schema_name,
                event_id=str(instance.id),
            )

        # KA-H8: отмена события → отмена его билетов (возврат, письмо, стоп рассрочки).
        # После коммита, фоном: возврат — сетевой вызов на каждый билет.
        if t.dst == "cancelled":
            from django.db import connection, transaction

            from .tasks import cancel_event_tickets

            actor = kw.get("actor")
            schema = connection.schema_name
            event_id = str(instance.id)
            actor_id = getattr(actor, "pk", None)

            def _enqueue():
                try:
                    cancel_event_tickets.delay(
                        tenant_schema=schema, event_id=event_id, actor_id=actor_id
                    )
                except Exception:  # noqa: BLE001 — брокер недоступен: событие уже отменено
                    import logging

                    logging.getLogger(__name__).exception(
                        "event cancel fan-out not queued (%s %s)", schema, event_id
                    )

            transaction.on_commit(_enqueue)


class TicketSM(StateMachine):
    kind = "ticket"
    transitions = [
        Transition("pending", "confirmed", "ticket.confirmed"),
        Transition("pending", "cancelled", "ticket.cancelled"),
        Transition("confirmed", "attended", "ticket.attended"),
        Transition("confirmed", "cancelled", "ticket.cancelled"),
    ]

    def on_transition(self, instance, t, **kw):
        # Письмо клиенту/владельцу (A6c) на подтверждение/отмену.
        if t.dst in ("confirmed", "cancelled"):
            from .notifications import enqueue_ticket_email

            enqueue_ticket_email(instance, t.dst)

        # B1.4: отмена → вернуть использование промокода/Gutschein (однократно —
        # FSM не даёт второй переход в cancelled).
        if t.dst == "cancelled" and getattr(instance, "voucher_code", ""):
            from apps.promotions.services import unredeem_voucher

            # B1.5: balance-сертификату возвращается и списанная сумма (снимок).
            unredeem_voucher(
                instance.voucher_code, amount_cents=getattr(instance, "discount_cents", 0)
            )

        # MX-0: отмена → освободить companion-бронь проживания. Раньше это делали
        # только два вьюха-хелпера — отмена с единой доски оставляла койку занятой.
        if t.dst == "cancelled" and getattr(instance, "stay_booking_id", None):
            from .services import release_linked_stay

            release_linked_stay(instance)

        # MX-2e: отмена возвращает stock-опции билета (идемпотентно; зеркало —
        # status_effects.restore_stock_for).
        if t.dst == "cancelled":
            from apps.core import option_trackers

            option_trackers.release_options("ticket", instance)

        # R10e: отмена билета → стоп будущих списаний рассрочки (без авто-возврата;
        # уже оплаченные доли возвращает владелец вручную в кабинете).
        if t.dst == "cancelled":
            from .models import InstallmentPlan

            plan = getattr(instance, "installment_plan", None)
            if plan is not None and plan.status == InstallmentPlan.STATUS_ACTIVE:
                plan.status = InstallmentPlan.STATUS_CANCELLED
                plan.save(update_fields=["status", "updated_at"])

        # Продажа билета (подтверждён/оплачен) → выручка. KA-H8: к оплате (после
        # ваучера) по снимку ставки билета; § 19 → 0 %.
        if t.dst == "confirmed":
            from . import revenue

            revenue.record_revenue(instance)

        # KA-H8: отмена → сторно ровно проведённой выручки (ключ «{id}:reversal» —
        # общий с status_effects, поэтому встроенный и свой путь дают одно сторно).
        if t.dst == "cancelled":
            from . import revenue

            revenue.record_reversal(instance, retained_cents=kw.get("retained_cents", 0))
