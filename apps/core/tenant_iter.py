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

from celery.exceptions import SoftTimeLimitExceeded
from django.db import connection, transaction
from django_tenants.utils import get_tenant_model, schema_context

logger = logging.getLogger(__name__)


def _queryset():
    model = get_tenant_model()
    qs = model.objects.exclude(schema_name="public")
    # failed — схемы нет; pending — схема ещё создаётся (ProgrammingError каждый проход).
    skip = [
        getattr(model, n)
        for n in ("PROVISIONING_FAILED", "PROVISIONING_PENDING")
        if hasattr(model, n)
    ]
    if skip:
        qs = qs.exclude(provisioning_status__in=skip)
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
    except SoftTimeLimitExceeded:
        raise  # лимит времени задачи — не ошибка бизнеса: обход должен остановиться
    except Exception:  # noqa: BLE001 — изоляция бизнесов; ошибка уходит в лог/Sentry
        outcome.failed = True
        _tag_sentry(schema, label)
        logger.exception("Фоновая задача %s: ошибка в схеме %s — обход продолжается", label, schema)


def _tag_sentry(schema: str, label: str) -> None:
    """Метки бизнеса и задачи на событии Sentry: «один бизнес сломан 10 дней» отличим
    от «упали все сегодня». Без SDK (тесты/dev) — тихо ничего."""
    try:
        import sentry_sdk

        sentry_sdk.set_tag("tenant_schema", schema)
        sentry_sdk.set_tag("beat_task", label)
    except Exception:  # noqa: BLE001
        pass


def raise_if_failed(failed: list[str], label: str) -> None:
    """Для задач, которые ОБЯЗАНЫ дойти до каждого бизнеса (сроки хранения DSGVO/BMG):
    после обхода — падение задачи, видимое в Celery/Sentry; остальные бизнесы уже
    обработаны, повтор идемпотентен."""
    if failed:
        raise RuntimeError(f"{label}: не выполнено в схемах {', '.join(failed)}")
