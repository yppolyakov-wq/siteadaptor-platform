"""T-8.10h H-4: кнопки превью акции в общем боте — `pb:<ref>` вместо `tp:…`.

Апдейт общего бота приходит без схемы бизнеса, поэтому callback_data несёт короткую
случайную ссылку; в кэше под (пользователь Telegram, ref) лежат схема и исходные данные
кнопки (`tp:ok:<token>` и т. п.). Чужой ref не найти под своим id; схема — та, где
создано ПРЕВЬЮ (не «текущий бизнес»: после /geschaeft ✅ старого превью публикует там,
куда оно и было адресовано).
"""

from __future__ import annotations

import re
import secrets

from django.core.cache import cache

PREFIX = "pb:"
TTL = 24 * 3600  # как у черновика
REF_RE = re.compile(r"^pb:([A-Za-z0-9_-]{12})$")
SCHEMA_RE = re.compile(r"^[a-z0-9_]{1,63}$")


def _key(tg_user_id, ref: str) -> str:
    return f"tgplat:ref:{int(tg_user_id)}:{ref}"


def wrap(tg_user_id, schema: str, inner: str) -> str:
    ref = secrets.token_urlsafe(9)  # 12 символов
    cache.set(_key(tg_user_id, ref), {"schema": schema, "data": inner}, TTL)
    return PREFIX + ref


def resolve(tg_user_id, data: str) -> tuple[str, str] | None:
    """(схема, исходные данные кнопки) — только для того, кому кнопку показали."""
    from apps.promotions.telegram_actions import CALLBACK_RE as ACTION_RE
    from apps.promotions.telegram_promo import CALLBACK_RE, REPEAT_CALLBACK_RE

    match = REF_RE.match(str(data or ""))
    if not match or not tg_user_id:
        return None
    value = cache.get(_key(tg_user_id, match.group(1)))
    if not isinstance(value, dict):
        return None
    schema, inner = str(value.get("schema") or ""), str(value.get("data") or "")
    if not SCHEMA_RE.match(schema):
        return None
    if not (CALLBACK_RE.match(inner) or REPEAT_CALLBACK_RE.match(inner) or ACTION_RE.match(inner)):
        return None
    return schema, inner
