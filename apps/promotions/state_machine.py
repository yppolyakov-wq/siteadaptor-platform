"""Машины состояний для Promotion и Reservation.

Спецификация: docs/references/patterns/state-machine.md. База — apps.core.fsm.
Каждый переход пишет audit-событие (через StateMachine._audit).
"""

from django.db.models import F

from apps.core.fsm import StateMachine, Transition


class PromotionSM(StateMachine):
    transitions = [
        Transition("draft", "scheduled", "promotion.scheduled"),
        # прямая активация черновика без расписания — для ручного запуска
        Transition("draft", "active", "promotion.activated"),
        Transition("draft", "archived", "promotion.archived"),
        Transition("scheduled", "active", "promotion.activated"),
        Transition("scheduled", "archived", "promotion.archived"),
        Transition("active", "paused", "promotion.paused"),
        Transition("paused", "active", "promotion.activated"),
        Transition("active", "ended", "promotion.ended"),
        Transition("paused", "ended", "promotion.ended"),
    ]

    def on_transition(self, instance, t, **kw):
        # Авто-публикация в локальный агрегатор: active → upsert листинга,
        # ended/paused/archived → удаление. Через очередь; схема — из текущего
        # соединения (акция живёт в TENANT-схеме). Сам upsert/remove решает задача.
        if t.dst in ("active", "ended", "paused", "archived"):
            from django.db import connection

            from apps.aggregator.tasks import sync_aggregator_listing

            sync_aggregator_listing.delay(
                dedupe_key=f"agg:{instance.id}:{t.dst}",
                tenant_schema=connection.schema_name,
                promotion_id=str(instance.id),
            )


class ReservationSM(StateMachine):
    transitions = [
        Transition("pending", "confirmed", "reservation.confirmed"),
        Transition("pending", "cancelled", "reservation.cancelled"),
        Transition("pending", "expired", "reservation.expired"),
        Transition("confirmed", "fulfilled", "reservation.fulfilled"),
        Transition("confirmed", "cancelled", "reservation.cancelled"),
        Transition("confirmed", "expired", "reservation.expired"),
    ]

    def on_transition(self, instance, t, **kw):
        # Возврат остатка при отмене/истечении — в той же транзакции, что и смена
        # статуса (см. anti-oversell.md::cancel). Только у акций с лимитом.
        if t.dst in ("cancelled", "expired"):
            from .models import Promotion

            Promotion.objects.filter(
                id=instance.promotion_id, available_quantity__isnull=False
            ).update(available_quantity=F("available_quantity") + instance.quantity)

        # email-уведомление клиенту (ставится в очередь после коммита)
        if t.dst in ("confirmed", "cancelled", "expired"):
            from .notifications import enqueue_reservation_email

            enqueue_reservation_email(instance, t.dst)
