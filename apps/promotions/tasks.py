"""Celery-beat задачи акций и броней.

Запускаются по расписанию ВНЕ tenant-контекста → проходим по всем схемам
арендаторов и работаем внутри schema_context. Чистая логика вынесена в
helper'ы (expire_due_reservations / roll_due_promotions), работающие в текущей
схеме — их и тестируем напрямую.

Задачи идемпотентны по своей природе (фильтр по времени), idempotent_task
здесь даёт единое имя и совместимость с dedupe-механизмом.
"""

from datetime import timedelta

from django.conf import settings
from django.db.models import Max
from django.utils import timezone
from django_tenants.utils import get_tenant_model, schema_context

from apps.core.jobs import idempotent_task

from .models import Customer, Promotion, Reservation
from .notifications import send_reservation_email  # noqa: F401 — регистрация Celery-таска
from .services import expire
from .state_machine import PromotionSM

# значение, которым затираем обезличенные контакты
_ANONYMIZED_NAME = "—"


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


def purge_due_customers(now=None) -> int:
    """DSGVO: обезличить контакты клиентов без активных броней (в текущей схеме).

    Кандидат — клиент, у которого нет pending/confirmed броней и чья последняя
    активность по броням старше RESERVATION_PII_RETENTION_DAYS. Сама строка
    Customer остаётся (для агрегатной статистики), но PII затирается.
    """
    now = now or timezone.now()
    cutoff = now - timedelta(days=settings.RESERVATION_PII_RETENTION_DAYS)

    active_customer_ids = Reservation.objects.filter(
        status__in=["pending", "confirmed"]
    ).values_list("customer_id", flat=True)

    stale = (
        Customer.objects.exclude(id__in=active_customer_ids)
        .annotate(last_activity=Max("reservations__updated_at"))
        .filter(last_activity__isnull=False, last_activity__lt=cutoff)
        # уже обезличенные не трогаем повторно
        .exclude(name=_ANONYMIZED_NAME, email="", phone="", note="")
    )

    count = 0
    for customer in stale:
        customer.name = _ANONYMIZED_NAME
        customer.email = ""
        customer.phone = ""
        customer.note = ""
        customer.save(update_fields=["name", "email", "phone", "note", "updated_at"])
        count += 1
    return count


@idempotent_task()
def purge_reservation_pii():
    """Beat: DSGVO-обезличивание старых контактов во всех схемах арендаторов."""
    total = 0
    now = timezone.now()
    for schema in _iter_tenant_schemas():
        with schema_context(schema):
            total += purge_due_customers(now)
    return {"purged": total}
