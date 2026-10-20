"""T-8.10h H-3: одноразовая ссылка «Mit Telegram verbinden» из кабинета.

Сырой токен уходит только в deep link (`t.me/<bot>?start=b-<raw>`); в кэше лежит sha256.
Один живой токен на бизнес: новая ссылка гасит прежнюю. Потребление атомарно — выигрывает
тот, чей `cache.delete` вернул True (два апдейта с одной ссылкой → одна привязка).
"""

from __future__ import annotations

import hashlib
import re
import secrets

from django.core.cache import cache

from apps.telegram import bots

PREFIX = "b-"
TTL = 15 * 60
_RAW_RE = re.compile(r"^[A-Za-z0-9_-]{20,60}$")


def _key(raw: str) -> str:
    return "tgplat:bind:" + hashlib.sha256(raw.encode()).hexdigest()


def _tenant_key(schema: str) -> str:
    return f"tgplat:bind-tenant:{schema}"


def issue(tenant, user, *, lang: str = "") -> str:
    """Deep link для привязки бизнеса к общему боту; '' — бот платформы недоступен."""
    bot = bots.platform_bot()
    if bot is None or not bot.username:
        return ""
    previous = cache.get(_tenant_key(tenant.schema_name))
    if previous:
        cache.delete(previous)
    raw = secrets.token_urlsafe(24)
    key = _key(raw)
    cache.set(
        key,
        {
            "schema": tenant.schema_name,
            "tenant_pk": tenant.pk,
            "user_pk": user.pk,
            "email": (getattr(user, "email", "") or "").strip(),
            "lang": lang or "",
        },
        TTL,
    )
    cache.set(_tenant_key(tenant.schema_name), key, TTL)
    return f"https://t.me/{bot.username}?start={PREFIX}{raw}"


def consume(raw: str) -> dict | None:
    """Payload токена ровно один раз; мусор/просрочка/повтор → None."""
    if not isinstance(raw, str) or not _RAW_RE.match(raw):
        return None
    key = _key(raw)
    payload = cache.get(key)
    if not isinstance(payload, dict):
        return None
    if not cache.delete(key):
        return None  # кто-то потребил раньше
    return payload
