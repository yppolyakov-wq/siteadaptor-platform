"""Фид товаров для Google Merchant Center: включение, адрес, перевыпуск (M23b.2).

План — docs/m23b-merchant-feed-plan-2026-10-18.md. Фид не зависит ни от подключения Google
(OAuth), ни от переключателя «Kanal eingeschaltet» (тот про публикацию акций): владелец
связывает Merchant Center с профилем в интерфейсе Google, нам нужен только адрес.

Хранение в `Channel(google_business).config`:
- `merchant_feed_token` — Fernet-шифротекст (в `secrets.SECRET_KEYS` → его перешифрует
  `rotate_secrets`). Владельцу адрес нужен многократно (копировать в Merchant Center),
  поэтому храним обратимо, а не хэшем;
- `merchant_feed` — `{"enabled": bool, "token_issued_at": iso}`, секретов нет.

Чтение СТРОГОЕ: значение, которое не расшифровывается нашим ключом, токеном не считается
(у `decrypted_config` фолбэк на «как есть» — тут он дал бы валидный токен из мусора)."""

from __future__ import annotations

import re
import secrets

from django.utils import timezone

from apps.secrets import crypto

from .models import Channel

TOKEN_KEY = "merchant_feed_token"
STATE_KEY = "merchant_feed"
MIN_TOKEN = 32  # = public_views.MERCHANT_FEED_MIN_TOKEN
STORE_CODE_MAX = 64  # лимит Google
# M23b.3: код магазина — печатный ASCII без пробелов, как его отдаёт профиль Google.
_STORE_CODE_RE = re.compile(r"[\x21-\x7e]{1,64}", re.ASCII)


def clean_store_code(value) -> str | None:
    """Код магазина из ввода: "" — убрать, None — недопустимо. Регистр сохраняем (Google
    сравнивает его с учётом регистра)."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return ""
    return value if _STORE_CODE_RE.fullmatch(value) else None


def channel() -> Channel:
    """Канал профиля Google (создаётся без побочных эффектов, `is_enabled` не трогаем)."""
    obj, _created = Channel.objects.get_or_create(type=Channel.GOOGLE_BUSINESS)
    return obj


def _read_token(config: dict) -> str | None:
    value = config.get(TOKEN_KEY)
    if not isinstance(value, str) or not value:
        return None
    token = crypto.decrypt(value)
    return token if len(token) >= MIN_TOKEN else None


def feed_state(obj: Channel | None) -> dict:
    """{"enabled", "issued_at", "token"} — токен расшифрован или None."""
    config = (obj.config or {}) if obj else {}
    state = config.get(STATE_KEY)
    state = state if isinstance(state, dict) else {}
    return {
        "enabled": bool(state.get("enabled")),
        "issued_at": state.get("token_issued_at") or "",
        "token": _read_token(config),
        "store_code": clean_store_code(state.get("store_code")) or "",
    }


def _new_token(config: dict, state: dict) -> None:
    config[TOKEN_KEY] = crypto.encrypt(secrets.token_urlsafe(32))
    state["token_issued_at"] = timezone.now().isoformat()


def _update(channel_pk, change) -> Channel:
    def mutate(config):
        state = config.get(STATE_KEY)
        state = dict(state) if isinstance(state, dict) else {}
        state.pop("token", None)  # плейнтекст ранних тестов M23b.1 не оставляем
        change(config, state)
        config[STATE_KEY] = state

    return Channel.update_config(channel_pk, mutate)


def enable(channel_pk) -> Channel:
    """Включить; токен выпускается, только если читаемого нет (повторный клик — тот же адрес)."""

    def change(config, state):
        state["enabled"] = True
        if _read_token(config) is None:
            _new_token(config, state)

    return _update(channel_pk, change)


def disable(channel_pk) -> Channel:
    """Выключить: фид становится пустым, адрес сохраняется для повторного включения."""

    def change(config, state):
        state["enabled"] = False

    return _update(channel_pk, change)


def rotate(channel_pk) -> Channel:
    """Новый адрес: старый сразу перестаёт работать; включённость не меняется."""

    def change(config, state):
        _new_token(config, state)

    return _update(channel_pk, change)


def set_store_code(channel_pk, value: str) -> Channel:
    """Записать код магазина (уже очищенный `clean_store_code`); "" убирает его."""

    def change(config, state):
        if value:
            state["store_code"] = value
        else:
            state.pop("store_code", None)

    return _update(channel_pk, change)
