"""Запись учёта — fail-safe: сбой учёта пишется в лог (только имя исключения) и не роняет
вызов. Отдельная точка сохранения: ошибка БД не отравит транзакцию вызывающего кода."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)
PURGE_BATCH = 10_000


def record(
    *,
    tenant_schema: str,
    is_demo: bool,
    task: str,
    route: str,
    model: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
    images: int = 0,
    cost_cents=0,
    duration_ms: int = 0,
    ok: bool = True,
    error_code: str = "",
    fallback_used: bool = False,
) -> None:
    from .models import AIUsage

    try:
        with transaction.atomic():
            AIUsage.objects.create(
                day=timezone.localdate(),
                tenant_schema=(tenant_schema or "")[:63],
                is_demo=bool(is_demo),
                task=task[:40],
                route=route[:20],
                model=(model or "")[:100],
                tokens_in=max(0, int(tokens_in or 0)),
                tokens_out=max(0, int(tokens_out or 0)),
                images=min(int(images or 0), 32767),
                cost_cents=cost_cents or 0,
                duration_ms=max(0, int(duration_ms or 0)),
                ok=ok,
                error_code=(error_code or "")[:30],
                fallback_used=fallback_used,
            )
    except Exception as exc:  # noqa: BLE001 — учёт не смеет ронять вызов
        logger.warning("ai usage record failed: %s", type(exc).__name__)


def purge() -> int:
    """Удалить учёт старше `AI_USAGE_RETENTION_DAYS` пачками (beat раз в сутки)."""
    from .models import AIUsage

    cutoff = timezone.localdate() - timedelta(days=settings.AI_USAGE_RETENTION_DAYS)
    total = 0
    while True:
        ids = list(
            AIUsage.objects.filter(day__lt=cutoff)
            .order_by("pk")
            .values_list("pk", flat=True)[:PURGE_BATCH]
        )
        if not ids:
            return total
        total += AIUsage.objects.filter(pk__in=ids).delete()[0]
