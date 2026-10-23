"""AI-CFG: настройки ИИ — значение из админки платформы, иначе из `.env`.

План — docs/ai-cfg-admin-settings-plan-2026-10-23.md. Приоритет: `override()` (проверка
ключа `ai_smoke`, предпросмотр формы) → строка `AIConfig` (ключ задан в админке) →
`settings` (`.env`). Settings читаются на КАЖДЫЙ вызов, поэтому `override_settings` в
тестах действует как раньше; кэшируется только словарь из БД (15 с на процесс).

Правило ЕС: `.env` — пол. Если там `AI_REQUIRE_EU=True`, админка может только
ужесточить, но не ослабить (взлом админки не отправит данные в США).

Чтение fail-safe: нет таблицы (префлайт до миграций), БД запрещена (тест) или любая
ошибка — значения `.env`, ошибка не кэшируется."""

from __future__ import annotations

import contextlib
import contextvars
import logging
import time
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger(__name__)

CACHE_SECONDS = 15


@dataclass(frozen=True)
class Spec:
    kind: str  # bool | int | float | list | str | prices
    group: str


_MODEL_KEYS = [
    f"{prefix}_{tier}"
    for prefix in (
        "ANTHROPIC_MODEL",
        "OPENAI_MODEL",
        "MISTRAL_MODEL",
        "BEDROCK_MODEL",
        "AZURE_OPENAI_DEPLOYMENT",
    )
    for tier in ("FAST", "STRONG")
]

SPECS: dict[str, Spec] = {
    "AI_ENABLED": Spec("bool", "general"),
    "AI_REQUIRE_EU": Spec("bool", "general"),
    "AI_ROUTE_FAST": Spec("list", "routes"),
    "AI_ROUTE_STRONG": Spec("list", "routes"),
    **{key: Spec("str", "models") for key in _MODEL_KEYS},
    "AI_TASKS_ENABLED": Spec("list", "tasks"),
    "AI_SEARCH_ENABLED": Spec("bool", "portal"),
    "AI_SEARCH_DAILY": Spec("int", "portal"),
    "AI_CATALOG_MODERATION": Spec("bool", "portal"),
    "AI_CATALOG_MODERATION_DAILY": Spec("int", "portal"),
    "AI_CATALOG_MODERATION_TENANT_DAILY": Spec("int", "portal"),
    "AI_TENANT_DAILY_CALLS": Spec("int", "limits"),
    "AI_TENANT_DAILY_EUR": Spec("float", "limits"),
    "AI_DAILY_BUDGET_EUR": Spec("float", "limits"),
    "AI_PRICES": Spec("prices", "limits"),
}

_override: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "ai_cfg_override", default=None
)
_cache: dict = {"values": None, "at": 0.0}


def reset_cache() -> None:
    _cache["values"] = None
    _cache["at"] = 0.0


def _db_values() -> dict:
    now = time.monotonic()
    if _cache["values"] is not None and now - _cache["at"] < CACHE_SECONDS:
        return _cache["values"]
    try:
        from django.db import connection, transaction
        from django_tenants.utils import schema_context

        from .models import AIConfig

        with schema_context("public"):
            if connection.in_atomic_block:
                with transaction.atomic():  # savepoint: ошибка не отравит внешнюю транзакцию
                    row = AIConfig.objects.filter(pk=1).values_list("values", flat=True).first()
            else:
                row = AIConfig.objects.filter(pk=1).values_list("values", flat=True).first()
    except Exception:  # noqa: BLE001 — нет таблицы/БД: действуют значения .env
        return {}
    values = {k: v for k, v in (row or {}).items() if k in SPECS}
    _cache["values"] = values
    _cache["at"] = now
    return values


def get(name: str, default=None):
    """Значение настройки ИИ: override → админка → `.env`."""
    over = _override.get()
    if over and name in over:
        return over[name]
    if name in SPECS:
        values = _db_values()
        if name in values:
            return values[name]
    return getattr(settings, name, default)


def require_eu() -> bool:
    """`.env` — пол: True там нельзя ослабить из админки."""
    over = _override.get()
    if over and "AI_REQUIRE_EU" in over:
        return bool(over["AI_REQUIRE_EU"])
    if getattr(settings, "AI_REQUIRE_EU", False):
        return True
    return bool(_db_values().get("AI_REQUIRE_EU", False))


def admin_values() -> dict:
    """Что задано в админке (копия) — для экрана."""
    return dict(_db_values())


def sources() -> dict[str, str]:
    values = _db_values()
    return {name: ("admin" if name in values else "env") for name in SPECS}


@contextlib.contextmanager
def override(**values):
    """Временно задать значения (ai_smoke, предпросмотр формы) поверх админки и `.env`."""
    token = _override.set({**(_override.get() or {}), **values})
    try:
        yield
    finally:
        _override.reset(token)


def save(values: dict, *, user=None) -> dict:
    """Записать значения админки (только ключи SPECS). → diff {key: [old, new]}."""
    from django_tenants.utils import schema_context

    from .models import AIConfig

    clean = {k: v for k, v in values.items() if k in SPECS}
    with schema_context("public"):
        row, _created = AIConfig.objects.get_or_create(pk=1)
        old = dict(row.values or {})
        row.values = clean
        row.updated_by = getattr(user, "get_username", lambda: "")() if user else ""
        row.save()
    reset_cache()
    keys = set(old) | set(clean)
    return {k: [old.get(k), clean.get(k)] for k in sorted(keys) if old.get(k) != clean.get(k)}
