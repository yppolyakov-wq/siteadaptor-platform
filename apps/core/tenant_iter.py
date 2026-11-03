"""SM11: фоновый обход всех бизнесов — один бизнес не обрывает остальных.

До 2026-11-03 около 25 beat-задач обходили тенантов голым циклом
`for schema in …: with schema_context(schema): …`. Исключение в одном бизнесе
(например, тенант с неудавшейся регистрацией — схемы/таблиц нет, ProgrammingError
на КАЖДОМ проходе) обрывало цикл, и бизнесы после него навсегда оставались без
напоминаний, возврата склада, DSGVO-удалений, отписок. Порядок тенантов не был
задан — кого именно пропускали, менялось от прогона к прогону.

`schemas()` / `tenants()` — единый список: без public, без тенантов с
`provisioning_status="failed"`, в стабильном порядке (pk).
`isolated(schema, label)` — контекст одного бизнеса: ошибка пишется в лог
(`logger.exception`, с меткой задачи и схемой) и НЕ выходит наружу.

Транзакцию на весь бизнес НЕ открываем: в теле бывают внешние вызовы (Stripe-
списания рассрочки, HTTP iCal) — откат БД после уже списанных денег дал бы двойное
списание на следующем проходе. В проде Celery работает в autocommit, ошибка одного
запроса транзакцию не «отравляет». Если вызов уже внутри транзакции (тесты,
вложенный вызов) — ставим точку сохранения, чтобы ошибка одного бизнеса не
обрывала остальных ("current transaction is aborted").
"""

from __future__ import annotations

import logging
from contextlib import contextmanager, nullcontext

from django.db import connection, transaction
from django_tenants.utils import get_tenant_model, schema_context

logger = logging.getLogger(__name__)


def _queryset():
    model = get_tenant_model()
    qs = model.objects.exclude(schema_name="public")
    failed = getattr(model, "PROVISIONING_FAILED", None)
    if failed and hasattr(model, "provisioning_status"):
        qs = qs.exclude(provisioning_status=failed)
    return qs.order_by("pk")


def tenants() -> list:
    """Тенанты для фонового обхода (объекты)."""
    with schema_context("public"):
        return list(_queryset())


def schemas() -> list[str]:
    """Схемы тенантов для фонового обхода."""
    with schema_context("public"):
        return list(_queryset().values_list("schema_name", flat=True))


class Outcome:
    """Итог тела одного бизнеса: `failed` — было ли исключение."""

    failed = False


@contextmanager
def isolated(schema: str, label: str):
    """Тело одного бизнеса: ошибка → лог, обход продолжается.

    `with isolated(...) as outcome:` — по `outcome.failed` задача может, например,
    упасть В КОНЦЕ обхода, чтобы Celery повторил её (отписка от рассылок)."""
    outcome = Outcome()
    guard = transaction.atomic() if connection.in_atomic_block else nullcontext()
    try:
        with schema_context(schema), guard:
            yield outcome
    except Exception:  # noqa: BLE001 — изоляция бизнесов; ошибка уходит в лог/Sentry
        outcome.failed = True
        logger.exception("Фоновая задача %s: ошибка в схеме %s — обход продолжается", label, schema)
