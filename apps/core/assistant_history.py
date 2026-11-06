"""AIS A-3d: история переписки с помощником — единственный писатель `AssistantTurn`.

Пишем ТОЛЬКО готовую проверенную запись ответа (её же видел пользователь): текст после
пост-проверки ИИ, ссылки идентификаторами, план данными. Повтор задачи — та же строка
(job уникален). Любой сбой записи — warning: история — дополнение, ответ важнее.
Срок — `ASSISTANT_HISTORY_DAYS` (90) и не больше `MAX_PER_USER` строк на человека.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

RETENTION_DAYS = int(getattr(settings, "ASSISTANT_HISTORY_DAYS", 90))
MAX_PER_USER = 200
SHOW = 5
#: служебные поля задачи, которые в историю не идут (промпт, лимиты, срок)
_DROP = ("prompt", "system", "schema", "ctx", "echo", "counted", "deadline", "digest", "q")
#: A-4a: пакет «создать» и его ошибки — только в кэше задачи: из истории не применить
_DROP += ("actions", "action_errors", "job")
#: A-5b: вопрос-уточнение и его пакет — только в кэше задачи
_DROP += ("options", "base", "slot", "at", "round", "question")


def _clean_entry(entry: dict) -> dict:
    from apps.core.assistant_ai import ENTRY_V

    # версия формата — как в кэше: запись старого формата при показе пропускается
    return {**{k: v for k, v in (entry or {}).items() if k not in _DROP}, "v": ENTRY_V}


def record(schema: str, user_pk, job: str, question: str, entry: dict) -> None:
    """Записать готовый ответ. Никогда не бросает."""
    from django_tenants.utils import schema_context

    from apps.core.models import AssistantTurn

    if not (user_pk and job and question) or (entry or {}).get("state") != "done":
        return
    kinds = {k for k, _label in AssistantTurn.KINDS}
    kind = entry.get("outcome") if entry.get("outcome") in kinds else AssistantTurn.KIND_FALLBACK
    try:
        with schema_context(schema):
            _turn, created = AssistantTurn.objects.get_or_create(
                job=job,
                defaults={
                    "user_id": user_pk,
                    "kind": kind,
                    "question": str(question)[:500],
                    "entry": _clean_entry(entry),
                },
            )
            if created:
                _cap(user_pk)
    except Exception:  # noqa: BLE001 — история — дополнение: ответ уже показан
        logger.warning("assistant history: record failed", exc_info=True)


def _cap(user_pk) -> None:
    from apps.core.models import AssistantTurn

    keep = AssistantTurn.objects.filter(user_id=user_pk).order_by("-created_at", "-pk")
    if not keep[MAX_PER_USER : MAX_PER_USER + 1].exists():
        return  # обычный случай — один дешёвый запрос по индексу
    old = list(keep.values_list("pk", flat=True)[MAX_PER_USER:])
    if old:
        AssistantTurn.objects.filter(pk__in=old).delete()


def recent(request, limit: int = SHOW) -> list[dict]:
    """Последние вопросы этого пользователя с ответами для показа (ссылки — заново)."""
    from django.db import transaction

    from apps.core import assistant_ai
    from apps.core.models import AssistantTurn

    try:
        # savepoint: сбой чтения (нет таблицы до миграции) не «отравит» внешнюю транзакцию
        with transaction.atomic():
            rows = list(AssistantTurn.objects.filter(user=request.user)[:limit])
    except Exception:  # noqa: BLE001 — нет таблицы до деплоя миграции: просто без истории
        logger.warning("assistant history: read failed", exc_info=True)
        return []
    from apps.core.assistant_ai import ENTRY_V

    out = []
    for turn in rows:
        if (turn.entry or {}).get("v") != ENTRY_V:
            continue  # старый формат записи — не показываем криво
        entry = {**(turn.entry or {}), "state": "done"}
        out.append(
            {
                "question": turn.question,
                "at": turn.created_at,
                "ans": assistant_ai.present(request, entry),
            }
        )
    return out


def clear(user) -> int:
    from apps.core.models import AssistantTurn

    deleted, _detail = AssistantTurn.objects.filter(user=user).delete()
    return deleted


def purge(now=None) -> int:
    """Удалить строки старше срока в текущей схеме (пачками)."""
    from apps.core.models import AssistantTurn

    cutoff = (now or timezone.now()) - timedelta(days=RETENTION_DAYS)
    total = 0
    while True:
        pks = list(
            AssistantTurn.objects.filter(created_at__lt=cutoff)
            .order_by("pk")
            .values_list("pk", flat=True)[:1000]
        )
        if not pks:
            return total
        deleted, _detail = AssistantTurn.objects.filter(pk__in=pks).delete()
        total += deleted
