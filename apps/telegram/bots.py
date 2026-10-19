"""T-8.10h: какой бот говорит с владельцем — свой бот бизнеса или общий бот платформы.

План — docs/t8-10h-platform-bot-plan-2026-10-19.md §1. Код акций из Telegram от бота
использует только ``.token``; вид бота (``kind``) нужен, чтобы черновик, задача и
✏️-форма скачивали фото ТЕМ ЖЕ ботом: ``file_id`` в Telegram привязан к боту.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

TENANT = "tenant"
PLATFORM = "platform"
KINDS = (TENANT, PLATFORM)


@dataclass(frozen=True)
class BotRef:
    kind: str
    token: str
    username: str = ""


def tenant_bot() -> BotRef | None:
    """Свой бот бизнеса (в схеме текущего тенанта)."""
    from .notify import active_bot

    bot = active_bot()
    if bot is None:
        return None
    return BotRef(TENANT, bot.token, bot.bot_username or "")


def platform_enabled() -> bool:
    return bool(getattr(settings, "TELEGRAM_PLATFORM_BOT_ENABLED", False))


def platform_bot() -> BotRef | None:
    """Общий бот платформы; выключен или без токена — нет бота."""
    if not platform_enabled():
        return None
    from apps.secrets.store import get_or_setting

    token = get_or_setting("telegram_platform_bot_token", "TELEGRAM_PLATFORM_BOT_TOKEN")
    if not token:
        return None
    return BotRef(PLATFORM, token, getattr(settings, "TELEGRAM_PLATFORM_BOT_USERNAME", "") or "")


def for_kind(kind: str | None) -> BotRef | None:
    """Бот по виду; неизвестный/пустой вид — свой бот (черновики и задачи до T-8.10h)."""
    return platform_bot() if kind == PLATFORM else tenant_bot()
