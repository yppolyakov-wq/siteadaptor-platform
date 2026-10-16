"""В1 (вариант 1 владельца, 2026-10-16): правила демо-бизнеса — одна точка истины.

Демо-витрину смотрят настоящие люди, поэтому путь покупки остаётся живым (заказ/бронь
создаются — иначе нечего «попробовать»), но ничего настоящего не происходит:
* на витрине плашка «Demo-Geschäft — Bestellungen sind nicht echt»;
* онлайн-оплаты, Vorkasse и счёта юрлицу нет — только «оплата на месте»;
* писем и Telegram из демо-бизнеса нет ни покупателю, ни владельцу.

Признак — поле `Tenant.is_demo` (ставит `demo_kits.apply_kit`), а не слаг кита:
`demo_switch.is_demo_tenant` отвечает за переключатель дизайна, это другая ось.
"""

from __future__ import annotations


def is_demo(tenant) -> bool:
    return bool(getattr(tenant, "is_demo", False))


def current_is_demo() -> bool:
    """Демо ли бизнес текущей схемы. В запросе — `connection.tenant` без запроса к БД;
    в Celery (`schema_context` даёт FakeTenant без полей) — один SELECT по схеме.
    Бизнес не найден — не демо (платформа шлёт свои письма как раньше)."""
    from django.db import connection

    tenant = getattr(connection, "tenant", None)
    if hasattr(tenant, "is_demo"):
        return is_demo(tenant)
    from apps.tenants.models import Tenant

    schema = getattr(connection, "schema_name", "") or ""
    return bool(Tenant.objects.filter(schema_name=schema).values_list("is_demo", flat=True).first())
