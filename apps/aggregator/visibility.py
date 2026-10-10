"""T-8.6: кто попадает в каталог города — одна точка истины.

План — docs/t8-6-catalog-hygiene-plan-2026-10-10.md §1. Используется ДВАЖДЫ:
- синками при записи листинга (`tasks._withheld`) — не-listable тенант листингов не получает;
- чтением портала (`AggregatorListing.objects.public()` → `withheld_schemas`) — правка
  статуса бизнеса (в том числе прямо в админке, мимо FSM) действует сразу, без ресинка.

`trial_expired` (льготная неделя после триала) из каталога НЕ убирает — только
приостановка (`suspended`) или выключенный бизнес.
"""

from __future__ import annotations

SUSPENDED = "suspended"


def listable(tenant) -> bool:
    """Может ли бизнес быть в каталоге города прямо сейчас."""
    if tenant is None:
        return False
    return bool(
        getattr(tenant, "is_active", True)
        and getattr(tenant, "subscription_status", "") != SUSPENDED
        and not getattr(tenant, "email_pending", False)
        and getattr(tenant, "in_city_catalog", True)
    )


def withheld_schemas():
    """Подзапрос схем, чьи листинги сейчас не показываются (для `.exclude(...__in=)`)."""
    from django.db.models import Q

    from apps.tenants.models import Tenant

    return Tenant.objects.filter(
        Q(is_active=False)
        | Q(subscription_status=SUSPENDED)
        | Q(email_pending=True)
        | Q(in_city_catalog=False)
    ).values("schema_name")


def apply_visibility(tenant) -> str:
    """Привести листинги бизнеса к его текущему статусу.

    Не listable — все листинги схемы удаляются (все виды разом); listable — фоновая
    реконсиляция всех видов (акции, номера, события, меню). → "removed" | "queued".
    """
    from django.db import transaction

    from .models import AggregatorListing

    if not listable(tenant):
        AggregatorListing.objects.filter(tenant_schema=tenant.schema_name).delete()
        return "removed"
    from .tasks import reconcile_aggregator_schema

    schema = tenant.schema_name
    transaction.on_commit(lambda: reconcile_aggregator_schema.delay(schema))
    return "queued"
