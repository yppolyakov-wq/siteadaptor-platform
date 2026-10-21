"""T-8.30i: регистрация нового бизнеса из Mini App в том же окне.

Ссылки-токена НЕТ (ревью: пересланная ссылка привязала бы чужой бизнес к Telegram
отправителя). Метку ставит сама страница Mini App: тот же адрес, свой заголовок
(``X-TG-App`` — чужой сайт без CORS-preflight его не пошлёт), подписанный ``initData``.
После этого Telegram-пользователь помнится в сессии публичного хоста 30 минут, и быстрая
регистрация передаёт его в провижининг — чат станет владельцем ТОЛЬКО после
подтверждения почты (H-5b). План — docs/t8-30i-miniapp-signup-plan-2026-10-21.md.
"""

from __future__ import annotations

import time

SESSION_KEY = "tg_websignup"
SESSION_TTL = 30 * 60


def allowed(uid: int) -> bool:
    """Не ограничен (Art. 18) и не упёрся в лимит бизнесов на чат."""
    from . import links, rights, signup

    if rights.is_restricted(uid):
        return False
    count = links.active_links(uid).count() + links.pending_for(uid).count()
    return count < signup.MAX_BOT_BUSINESSES


def remember(request, *, uid: int, lang: str = "", name: str = "") -> None:
    request.session.cycle_key()  # новая сессия: подсаженный идентификатор не наследуется
    request.session[SESSION_KEY] = {
        "uid": int(uid),
        "lang": (lang or "")[:8],
        "name": (name or "")[:64],
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
