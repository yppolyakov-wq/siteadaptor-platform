"""Celery-beat задачи акций и броней.

Запускаются по расписанию ВНЕ tenant-контекста → проходим по всем схемам
арендаторов и работаем внутри schema_context. Чистая логика вынесена в
helper'ы (expire_due_reservations / roll_due_promotions), работающие в текущей
схеме — их и тестируем напрямую.

Задачи идемпотентны по своей природе (фильтр по времени), idempotent_task
здесь даёт единое имя и совместимость с dedupe-механизмом.
"""

from django.utils import timezone
from django_tenants.utils import get_tenant_model, schema_context

from apps.core.jobs import idempotent_task

from .models import Promotion, Reservation
from .notifications import send_reservation_email  # noqa: F401 — регистрация Celery-таска
from .services import expire
from .state_machine import PromotionSM


def _iter_tenant_schemas():
    for tenant in get_tenant_model().objects.exclude(schema_name="public"):
        yield tenant.schema_name


def expire_due_reservations(now=None) -> int:
    """Просрочить pending/confirmed брони с истёкшим expires_at (в текущей схеме).

    Возврат остатка делает expire() через ReservationSM. Возвращает число
    просроченных броней.
    """
    now = now or timezone.now()
    stale = Reservation.objects.filter(
        status__in=["pending", "confirmed"],
        expires_at__isnull=False,
        expires_at__lt=now,
    )
    count = 0
    for res in stale:
        expire(res)
        count += 1
    return count


def roll_due_promotions(now=None) -> dict:
    """scheduled→active по starts_at, active→ended по ends_at (в текущей схеме)."""
    now = now or timezone.now()
    sm = PromotionSM()
    activated = ended = 0

    for promo in Promotion.objects.filter(
        status="scheduled", starts_at__isnull=False, starts_at__lte=now
    ):
        # если окно уже целиком в прошлом — не активируем (нет перехода
        # scheduled→ended; такую акцию владелец завершит/архивирует вручную)
        if promo.ends_at and promo.ends_at <= now:
            continue
        sm.apply(promo, "active")
        activated += 1

    for promo in Promotion.objects.filter(status="active", ends_at__isnull=False, ends_at__lte=now):
        sm.apply(promo, "ended")
        ended += 1

    return {"activated": activated, "ended": ended}


@idempotent_task()
def expire_reservations():
    """Beat: просрочка броней по всем схемам арендаторов."""
    now = timezone.now()
    total = 0
    for schema in _iter_tenant_schemas():
        with schema_context(schema):
            total += expire_due_reservations(now)
    return {"expired": total}


@idempotent_task()
def roll_promotion_statuses():
    """Beat: активация/завершение акций по расписанию во всех схемах."""
    now = timezone.now()
    activated = ended = 0
    for schema in _iter_tenant_schemas():
        with schema_context(schema):
            res = roll_due_promotions(now)
            activated += res["activated"]
            ended += res["ended"]
    return {"activated": activated, "ended": ended}
