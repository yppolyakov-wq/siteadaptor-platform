"""T-8.10h: настройки общего бота платформы — из веб-админки (зашифрованные секреты
`apps.secrets`), иначе из settings/.env. Экран — admin «Plattform-Bot».

Токен и секрет вебхука в интерфейсе не показываются (write-only). Ошибки Telegram
наружу только типом/кодом: в URL запроса к Bot API стоит токен.
"""

from __future__ import annotations

import secrets as _secrets

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

KEY_ENABLED = "telegram_platform_bot_enabled"
KEY_TOKEN = "telegram_platform_bot_token"
KEY_USERNAME = "telegram_platform_bot_username"
KEY_SECRET = "telegram_platform_webhook_secret"
LAST_UPDATE_KEY = "tgplat:last-update"
SECRET_MIN = 24


KEYS = (KEY_ENABLED, KEY_TOKEN, KEY_USERNAME, KEY_SECRET)
_CACHE_TTL = 30.0  # с; в процессе (не в Redis: токен не должен лежать там открытым)
_cache: dict = {"at": 0.0, "values": {}}


def _values() -> dict:
    """Все ключи бота одним запросом, с коротким кэшем в процессе: бот читается на каждом
    апдейте и при каждой доставке уведомления."""
    import time

    now = time.monotonic()
    if now - _cache["at"] < _CACHE_TTL:
        return _cache["values"]
    from django_tenants.utils import schema_context

    from apps.secrets.models import PlatformSecret

    values = {}
    with schema_context("public"):
        for obj in PlatformSecret.objects.filter(key__in=KEYS):
            value = obj.get_value() if obj.is_set else ""
            if value:  # пустая расшифровка (смена ключа) = «не задано», действует .env
                values[obj.key] = value
    _cache.update(at=now, values=values)
    return values


def reset_cache() -> None:
    _cache.update(at=0.0, values={})


def _get(key: str) -> str | None:
    """Значение из админки; None — не задано там (тогда действует .env)."""
    return _values().get(key)


def _set(key: str, value: str, description: str) -> None:
    from django_tenants.utils import schema_context

    from apps.secrets.models import PlatformSecret

    with schema_context("public"):
        obj, _created = PlatformSecret.objects.get_or_create(
            key=key, defaults={"description": description}
        )
        obj.set_value(value)
        obj.save()
    reset_cache()


def enabled() -> bool:
    stored = _get(KEY_ENABLED)
    if stored is not None:
        return stored == "1"
    return bool(getattr(settings, "TELEGRAM_PLATFORM_BOT_ENABLED", False))


def token() -> str:
    stored = _get(KEY_TOKEN)
    return stored if stored else getattr(settings, "TELEGRAM_PLATFORM_BOT_TOKEN", "") or ""


def username() -> str:
    stored = _get(KEY_USERNAME)
    value = stored if stored else getattr(settings, "TELEGRAM_PLATFORM_BOT_USERNAME", "") or ""
    return value.lstrip("@")


def webhook_secret() -> str:
    stored = _get(KEY_SECRET)
    return stored if stored else getattr(settings, "TELEGRAM_PLATFORM_WEBHOOK_SECRET", "") or ""


def set_enabled(value: bool) -> None:
    _set(KEY_ENABLED, "1" if value else "0", "Plattform-Bot an/aus")


def set_token(value: str) -> None:
    _set(KEY_TOKEN, value.strip(), "Token des Plattform-Bots (BotFather)")


def set_username(value: str) -> None:
    _set(KEY_USERNAME, value.strip().lstrip("@"), "Benutzername des Plattform-Bots")


def ensure_secret() -> str:
    """Секрет вебхука; нет или короткий — сгенерировать и сохранить."""
    current = webhook_secret()
    if len(current) >= SECRET_MIN:
        return current
    fresh = _secrets.token_hex(24)
    _set(KEY_SECRET, fresh, "Webhook-Secret des Plattform-Bots")
    return fresh


def webhook_url() -> str:
    from django.urls import reverse

    from apps.tenants.quickstart import domain_base

    return f"https://{domain_base()}" + reverse(
        "platform-bot-webhook", urlconf="config.urls_public"
    )


def check_token(raw: str) -> str:
    """getMe; вернуть username бота. Ошибка — ValueError с безопасным текстом."""
    from apps.telegram import services

    try:
        me = services.get_me(raw)
    except Exception as exc:  # noqa: BLE001 — токен в URL: наружу только тип
        raise ValueError(type(exc).__name__) from None
    if not me.get("is_bot") or not me.get("username"):
        raise ValueError("kein Bot")
    return str(me["username"])


def apply_webhook() -> None:
    from apps.telegram import services

    bot_token = token()
    if not bot_token:
        raise ValueError("kein Token")
    try:
        services.set_webhook(bot_token, webhook_url(), ensure_secret())
    except Exception as exc:  # noqa: BLE001
        raise ValueError(type(exc).__name__) from None
    set_commands(bot_token)
    set_menu_button(bot_token)


def miniapp_url() -> str:
    """T-8.30: адрес Mini App «Mein Laden» (Telegram принимает только https)."""
    from apps.tenants.quickstart import domain_base

    return f"https://{domain_base()}/tg/app/"


def set_menu_button(bot_token: str) -> None:
    """Кнопка меню «Mein Laden» во всех личных чатах (сбой не ломает установку вебхука)."""
    import logging

    from apps.telegram import services

    try:
        services.set_chat_menu_button(bot_token, url=miniapp_url(), text="Mein Laden")
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).warning("setChatMenuButton failed: %s", type(exc).__name__)


def set_commands(bot_token: str) -> None:
    """Меню команд на всех языках кабинета (сбой не ломает установку вебхука)."""
    import logging

    from django.utils import translation
    from django.utils.translation import gettext as _

    from apps.telegram import services

    langs = ["", *getattr(settings, "CABINET_LANGUAGES", ())]
    for lang in langs:
        try:
            with translation.override(lang or "de"):
                commands = [
                    {"command": "neu", "description": _("Neues Geschäft anlegen")},
                    {"command": "geschaeft", "description": _("Geschäft wechseln")},
                    {"command": "wiederholen", "description": _("Aktion wiederholen")},
                    {"command": "abbrechen", "description": _("Abbrechen")},
                    {"command": "aktionen", "description": _("Meine Aktionen")},
                    {"command": "profil", "description": _("Mein Profil")},
                    {"command": "hilfe", "description": _("Hilfe")},
                    {"command": "kabinett", "description": _("Kabinett öffnen")},
                    {"command": "eigener_bot", "description": _("Eigener Bot")},
                    {"command": "datenschutz", "description": _("Datenschutz")},
                    {"command": "meine_daten", "description": _("Meine Daten anzeigen")},
                    {"command": "daten_loeschen", "description": _("Meine Daten löschen")},
                ]
            services.set_my_commands(bot_token, commands, language_code=lang)
        except Exception as exc:  # noqa: BLE001
            logging.getLogger(__name__).warning("setMyCommands failed: %s", type(exc).__name__)


def remove_webhook() -> None:
    from apps.telegram import services

    bot_token = token()
    if not bot_token:
        raise ValueError("kein Token")
    try:
        services.delete_webhook(bot_token)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(type(exc).__name__) from None


def webhook_info(bot_token: str = "") -> dict:
    """Состояние вебхука у Telegram: {url, pending, error, ok}. Ошибка — {'ok': False}."""
    from apps.telegram import services

    bot_token = bot_token or token()
    if not bot_token:
        return {"ok": False}
    try:
        info = services.get_webhook_info(bot_token, timeout=5)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": type(exc).__name__}
    return {
        "ok": True,
        "url": str(info.get("url") or ""),
        "pending": int(info.get("pending_update_count") or 0),
        "error": str(info.get("last_error_message") or "")[:200],
        "matches": str(info.get("url") or "") == webhook_url(),
    }


def mark_update() -> None:
    try:
        cache.set(LAST_UPDATE_KEY, timezone.now().isoformat(), 60 * 60 * 24 * 30)
    except Exception:  # noqa: BLE001 — статус для экрана, не критично
        pass


def last_update():
    """Время последнего принятого апдейта (datetime) или None."""
    from django.utils.dateparse import parse_datetime

    try:
        raw = cache.get(LAST_UPDATE_KEY) or ""
    except Exception:  # noqa: BLE001
        return None
    return parse_datetime(raw) if raw else None


def sources() -> dict:
    """Откуда берётся каждое значение — для честного экрана («Admin» / «.env» / «—»)."""

    def src(key, attr):
        if _get(key) is not None:
            return "admin"
        return "env" if getattr(settings, attr, "") else ""

    return {
        "enabled": src(KEY_ENABLED, "TELEGRAM_PLATFORM_BOT_ENABLED"),
        "token": src(KEY_TOKEN, "TELEGRAM_PLATFORM_BOT_TOKEN"),
        "username": src(KEY_USERNAME, "TELEGRAM_PLATFORM_BOT_USERNAME"),
        "secret": src(KEY_SECRET, "TELEGRAM_PLATFORM_WEBHOOK_SECRET"),
    }
