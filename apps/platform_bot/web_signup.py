"""T-8.30i: регистрация нового бизнеса из Mini App в том же окне.

Mini App (``unlinked``) получает одноразовую ссылку ``/aktion-starten/tg/<token>/``.
Токен знает только сервер (ключ — sha256), живёт 10 минут и гасится POST'ом; после
этого Telegram-пользователь помнится в сессии публичного хоста (2 ч), и быстрая
регистрация передаёт его в провижининг — чат станет владельцем ТОЛЬКО после
подтверждения почты (H-5b). План — docs/t8-30i-miniapp-signup-plan-2026-10-21.md.
"""

from __future__ import annotations

import hashlib
import secrets
import time

from django.core.cache import cache

TOKEN_TTL = 600
SESSION_KEY = "tg_websignup"
SESSION_TTL = 2 * 3600


def _key(raw: str) -> str:
    return "tgapp:websignup:" + hashlib.sha256(raw.encode()).hexdigest()


def allowed(uid: int) -> bool:
    """Не ограничен (Art. 18) и не упёрся в лимит бизнесов на чат."""
    from . import links, rights, signup

    if rights.is_restricted(uid):
        return False
    count = links.active_links(uid).count() + links.pending_for(uid).count()
    return count < signup.MAX_BOT_BUSINESSES


def issue(uid: int, lang: str = "") -> str:
    raw = secrets.token_urlsafe(24)
    cache.set(_key(raw), {"uid": int(uid), "lang": (lang or "")[:8]}, TOKEN_TTL)
    return raw


def key_of(raw: str) -> str:
    return _key(raw)


def peek(raw: str) -> dict | None:
    if not raw or len(raw) > 100:
        return None
    payload = cache.get(_key(raw))
    return payload if isinstance(payload, dict) else None


def take(raw: str) -> dict | None:
    """Погасить токен (один раз — побеждает тот, кто удалил ключ)."""
    payload = peek(raw)
    if payload is None or not cache.delete(_key(raw)):
        return None
    return payload


def url_for(raw: str) -> str:
    from apps.tenants.quickstart import domain_base

    return f"https://{domain_base()}/aktion-starten/tg/{raw}/"


def remember(request, payload: dict) -> None:
    request.session[SESSION_KEY] = {
        "uid": int(payload["uid"]),
        "lang": payload.get("lang") or "",
        "exp": int(time.time()) + SESSION_TTL,
    }


def from_session(request) -> dict | None:
    data = request.session.get(SESSION_KEY)
    if not isinstance(data, dict):
        return None
    if int(data.get("exp") or 0) < time.time() or not data.get("uid"):
        request.session.pop(SESSION_KEY, None)
        return None
    return data


def forget(request) -> None:
    request.session.pop(SESSION_KEY, None)
