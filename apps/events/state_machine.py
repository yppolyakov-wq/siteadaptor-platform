"""FSM события и билета (A6). База — apps.core.fsm.

EventSM: draft → published → cancelled (мероприятие). TicketSM: pending →
confirmed → attended, отмена из pending/confirmed. На confirmed билет пишет
выручку в журнал finance (НДС 19 %, source «event», идемпотентно по source_ref);
бесплатные события (amount 0) record_revenue пропускает. Письма — A6c.
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


class TicketSM(StateMachine):
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

        # Продажа билета (подтверждён/оплачен) → выручка. НДС 19 % (стандарт; для
        # культурных мероприятий может быть 7 % — настраиваемо позже).
        if t.dst == "confirmed":
            from decimal import Decimal

            from apps.finance.services import record_revenue

            record_revenue(
                source="event",
                source_ref=str(instance.id),
                amount=Decimal(instance.total_cents) / 100,
                vat_rate=Decimal("19.00"),
                customer=instance.customer,
                note=instance.reference_code,
            )
