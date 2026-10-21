"""T-8.30: проверка подписи Telegram Mini App (``initData``).

План — docs/t8-30-miniapp-plan-2026-10-20.md §1.2. Telegram подписывает строку параметров
ключом, производным от токена бота: ``secret = HMAC_SHA256(key="WebAppData", msg=token)``,
``hash = HMAC_SHA256(key=secret, msg=data_check_string)``, где ``data_check_string`` —
пары ``key=value`` кроме ``hash``, отсортированные по ключу и склеенные ``\\n``.

Подделать подпись без токена нельзя; окно — 5 минут; повтор той же подписи отбит.
Сама строка ``initData`` нигде не логируется — в ней имя и id пользователя.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from urllib.parse import parse_qsl

from django.core.cache import cache

MAX_BYTES = 4096
MAX_AGE = 300
CLOCK_SKEW = 30
SEEN_PREFIX = "tgapp:seen:"


class InitDataError(Exception):
    """Отказ проверки. ``code`` — короткий машинный код (его и только его логируем)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _pairs(init_data: str) -> list[tuple[str, str]]:
    if not isinstance(init_data, str) or not init_data:
        raise InitDataError("malformed")
    if len(init_data.encode("utf-8")) > MAX_BYTES:
        raise InitDataError("malformed")
    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        raise InitDataError("malformed") from None
    keys = [k for k, _v in pairs]
    if len(keys) != len(set(keys)):
        raise InitDataError("malformed")
    return pairs


def signature(pairs, bot_token: str) -> str:
    """Подпись набора пар (без ``hash``) — тем же алгоритмом, что у Telegram."""
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(pairs) if k != "hash")
    secret = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    return hmac.new(secret, dcs.encode("utf-8"), hashlib.sha256).hexdigest()


def verify(
    init_data: str,
    bot_token: str,
    *,
    now: int,
    max_age: int = MAX_AGE,
    allow_replay: bool = False,
) -> dict:
    """Проверить ``initData`` и вернуть ``{uid, language_code, start_param, digest, replay}``.

    Порядок: разбор → подпись → время → пользователь → повтор. Повтор отмечается ТОЛЬКО
    после успешной проверки (провал не «сжигает» чужую подпись). T-8.30f: с
    ``allow_replay`` повтор не бросает, а помечается ``replay=True`` — решение о
    допуске (тот же IP, лимит) принимает вызывающий."""
    if not bot_token:
        raise InitDataError("no_token")
    pairs = _pairs(init_data)
    data = dict(pairs)
    given = data.get("hash", "")
    if not given or not given.isascii():  # compare_digest падает на не-ASCII str → 500
        raise InitDataError("malformed")
    if not hmac.compare_digest(signature(pairs, bot_token), given):
        raise InitDataError("bad_hash")
    try:
        auth_date = int(data.get("auth_date", ""))
    except ValueError:
        raise InitDataError("expired") from None
    if now - auth_date > max_age or auth_date > now + CLOCK_SKEW:
        raise InitDataError("expired")
    try:
        user = json.loads(data.get("user", ""))
    except ValueError:
        raise InitDataError("bad_user") from None
    uid = user.get("id") if isinstance(user, dict) else None
    if not isinstance(uid, int) or isinstance(uid, bool) or uid <= 0:
        raise InitDataError("bad_user")
    digest = hashlib.sha256(given.encode("ascii", "ignore")).hexdigest()
    replay = not cache.add(SEEN_PREFIX + digest, 1, timeout=max_age + 60)
    if replay and not allow_replay:
        raise InitDataError("replay")
    lang = user.get("language_code")
    name = user.get("username") or user.get("first_name") or ""
    return {
        "uid": uid,
        "name": name[:64] if isinstance(name, str) else "",
        "language_code": lang if isinstance(lang, str) else "",
        "start_param": data.get("start_param", ""),
        "digest": digest,
        "replay": replay,
    }
