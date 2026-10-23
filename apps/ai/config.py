"""AI-CFG: настройки ИИ — значение из админки платформы, иначе из `.env`.

План — docs/ai-cfg-admin-settings-plan-2026-10-23.md. Приоритет: `override()` (проверка
ключа `ai_smoke`, предпросмотр формы) → строка `AIConfig` (ключ задан в админке) →
`settings` (`.env`). Settings читаются на КАЖДЫЙ вызов, поэтому `override_settings` в
тестах действует как раньше; кэшируется только словарь из БД (15 с на процесс).

Правило ЕС: `.env` — пол. Если там `AI_REQUIRE_EU=True`, админка может только
ужесточить, но не ослабить (взлом админки не отправит данные в США).

Чтение fail-safe: нет таблицы (префлайт до миграций), БД запрещена (тест) или любая
ошибка — значения `.env`; ошибка кэшируется коротко (FAIL_CACHE_SECONDS), чтобы недоступная
БД не стоила запроса на каждый `get()`. TTL кэша — `AI_CONFIG_CACHE_SECONDS` (в тестах 0:
кэш процесса иначе пережил бы откат БД между тестами)."""

from __future__ import annotations

import contextlib
import contextvars
import logging
import time
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger(__name__)

CACHE_SECONDS = 15
FAIL_CACHE_SECONDS = 5


def _ttl() -> float:
    return float(getattr(settings, "AI_CONFIG_CACHE_SECONDS", CACHE_SECONDS))


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

#: Служебные ключи override: проверка формы видит ровно то, что будет сохранено (ключи без
#: значения формы → `.env`, а не прежняя строка админки); CLI-обход пола ЕС для ai_smoke.
ENV_BASELINE = "__env_baseline__"
ALLOW_NON_EU = "__allow_non_eu__"

_override: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "ai_cfg_override", default=None
)
_cache: dict = {"values": None, "at": 0.0, "ttl": 0.0}


def reset_cache() -> None:
    _cache["values"] = None
    _cache["at"] = 0.0
    _cache["ttl"] = 0.0


_MODEL_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-/@")
_NUM_MAX = 1_000_000


def _coerce(kind: str, value):
    """Значение из БД строго по типу реестра; иначе ValueError (ключ отбрасывается →
    действует `.env`). Строка `"false"` у bool, строка вместо списка маршрутов, NaN в
    бюджете — всё это мусор, а не значение (ревью AI-CFG)."""
    import math

    if kind == "bool":
        if isinstance(value, bool):
            return value
    elif kind == "int":
        if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= _NUM_MAX:
            return value
    elif kind == "float":
        if isinstance(value, int | float) and not isinstance(value, bool):
            if math.isfinite(value) and 0 <= value <= _NUM_MAX:
                return float(value)
    elif kind == "list":
        if isinstance(value, list) and all(isinstance(v, str) and len(v) <= 64 for v in value):
            return list(value)
    elif kind == "str":
        if isinstance(value, str) and len(value) <= 120 and set(value) <= _MODEL_CHARS:
            return value
    elif kind == "prices" and isinstance(value, dict):
        out = {}
        for model, pair in value.items():
            ok = (
                isinstance(model, str)
                and set(model) <= _MODEL_CHARS
                and isinstance(pair, list | tuple)
                and len(pair) == 2
                and all(isinstance(c, int) and not isinstance(c, bool) for c in pair)
                and all(0 <= c <= _NUM_MAX for c in pair)
            )
            if not ok:
                raise ValueError(model)
            out[model] = [pair[0], pair[1]]
        return out
    raise ValueError(kind)


def _clean(raw) -> dict:
    if not isinstance(raw, dict):
        if raw:
            logger.warning("ai config: row is not a dict, ignored")
        return {}
    out = {}
    for key, value in raw.items():
        if key not in SPECS:
            continue
        try:
            out[key] = _coerce(SPECS[key].kind, value)
        except ValueError:
            logger.warning("ai config: invalid value for %s ignored", key)
    return out


def _db_values() -> dict:
    now = time.monotonic()
    if _cache["values"] is not None and now - _cache["at"] < _cache["ttl"]:
        return _cache["values"]
    ttl = _ttl()
    try:
        from django.db import connection, transaction

        from .models import AIConfig

        # Таблица только в public; search_path тенанта (tenant, public) её находит — без
        # schema_context (тот сбрасывает кэш ContentType на каждом промахе).
        qs = AIConfig.objects.filter(pk=1).values_list("values", flat=True)
        if connection.in_atomic_block:
            with transaction.atomic():  # savepoint: ошибка не отравит внешнюю транзакцию
                row = qs.first()
        else:
            row = qs.first()
    except Exception:  # noqa: BLE001 — нет таблицы/БД: действуют значения .env
        _cache.update(values={}, at=now, ttl=min(FAIL_CACHE_SECONDS, ttl))
        return {}
    values = _clean(row)
    _cache.update(values=values, at=now, ttl=ttl)
    return values


def get(name: str, default=None):
    """Значение настройки ИИ: override → админка → `.env`."""
    over = _override.get()
    if over and name in over:
        return over[name]
    if name in SPECS and not (over and over.get(ENV_BASELINE)):
        values = _db_values()
        if name in values:
            return values[name]
    return getattr(settings, name, default)


def require_eu() -> bool:
    """`.env` — пол: True там нельзя ослабить ни из админки, ни через override формы.

    Ослабить может только `ai_smoke --allow-non-eu` (CLI, ключ ALLOW_NON_EU)."""
    over = _override.get() or {}
    if over.get(ALLOW_NON_EU):
        return False
    if getattr(settings, "AI_REQUIRE_EU", False):
        return True
    if "AI_REQUIRE_EU" in over:
        return bool(over["AI_REQUIRE_EU"])
    if over.get(ENV_BASELINE):
        return False
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
    """Записать значения админки (только ключи SPECS). → diff {key: [old, new]}.

    Строка блокируется: два одновременных сохранения не перетирают друг друга, а дифф
    для аудита честный. Вызывать внутри `transaction.atomic()` вместе с записью аудита."""
    from django.db import transaction
    from django_tenants.utils import schema_context

    from .models import AIConfig

    clean = _clean(values)
    with schema_context("public"), transaction.atomic():
        AIConfig.objects.get_or_create(pk=1)
        row = AIConfig.objects.select_for_update().get(pk=1)
        old = dict(row.values or {})
        row.values = clean
        row.updated_by = getattr(user, "get_username", lambda: "")() if user else ""
        row.save()
    reset_cache()
    keys = set(old) | set(clean)
    return {k: [old.get(k), clean.get(k)] for k in sorted(keys) if old.get(k) != clean.get(k)}
