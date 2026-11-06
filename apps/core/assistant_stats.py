"""AIS A-6b: счётчики исходов помощника по дням — только КОДЫ, без текста фраз.

План — docs/ais-a6-quality-plan-2026-11-06.md §2. Нужны для того, что не доходит до истории
(`AssistantTurn`): отказы до модели (лимит, выключено, пусто/длинно), отправка в Support.
Ключ `asst:st:<YYYYMMDD>:<schema>:<route>:<code>`; маршрут и код — только из белых списков
(иначе `other`), поэтому текст фразы в ключ попасть не может. TTL 35 дней; потеря при
перезапуске Redis допустима (истина о переписке — история). Ключи читаются детерминированно
(даты × маршруты × коды), без `scan_iter`. Сбой Redis никогда не роняет ответ.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

TTL = 35 * 86400
CODES = (
    "ok",
    "answer",
    "unknown",
    "unclear",
    "check_failed",
    "scope",
    "disabled",
    "quota",
    "busy",
    "empty",
    "too_long",
    "unavailable",
    "timeout",
    "sent",
    "other",
)


def routes() -> tuple[str, ...]:
    from apps.core import assistant_router

    return tuple(h.key for h in assistant_router.HANDLERS)


def _key(day: date, schema: str, route: str, code: str) -> str:
    return f"asst:st:{day:%Y%m%d}:{schema}:{route}:{code}"


def bump(schema: str, route: str, code: str = "") -> None:
    """+1 к счётчику дня. Никогда не бросает."""
    from django.core.cache import cache

    route = route if route in routes() else "other"
    code = (code or "ok") if (code or "ok") in CODES else "other"
    key = _key(timezone.localdate(), schema or "?", route, code)
    try:
        if not cache.add(key, 1, TTL):
            cache.incr(key)
    except Exception:  # noqa: BLE001 — счётчик качества не роняет помощника
        logger.warning("assistant stats: bump failed", exc_info=True)


def read(schema: str, days: int = 30) -> dict[tuple[str, str], int]:
    """{(route, code): сумма за `days` дней} по бизнесу."""
    from django.core.cache import cache

    today = timezone.localdate()
    keys = {}
    for i in range(max(days, 1)):
        day = today - timedelta(days=i)
        for route in (*routes(), "other"):
            for code in CODES:
                keys[_key(day, schema, route, code)] = (route, code)
    try:
        got = cache.get_many(list(keys))
    except Exception:  # noqa: BLE001
        logger.warning("assistant stats: read failed", exc_info=True)
        return {}
    out: dict[tuple[str, str], int] = {}
    for key, value in got.items():
        pair = keys[key]
        out[pair] = out.get(pair, 0) + int(value or 0)
    return out
