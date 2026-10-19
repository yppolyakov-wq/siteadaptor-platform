"""T-8.10h: обработка апдейтов общего бота (Celery, public-схема).

H-2: только каркас — личный чат получает приветствие, группы бот покидает, блокировка
бота пользователем отмечается. Подключение бизнеса (H-3), акции (H-4) и регистрация
(H-5) достраиваются поверх. Клиенты бизнеса этим ботом не обслуживаются: у него нет
витрины, Mini App и клиентских уведомлений — только владельцы.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext as _

from apps.telegram import bots

from . import links

logger = logging.getLogger(__name__)

GROUP_TYPES = ("group", "supergroup", "channel")


def locale_for(language_code: str) -> str:
    code = str(language_code or "")[:2].lower()
    return code if code in getattr(settings, "CABINET_LANGUAGES", ()) else "de"


def send(bot, chat, text: str, markup=None) -> bool:
    """Ответ без утечки токена: текст HTTPError содержит URL с токеном бота."""
    from apps.telegram import services

    try:
        services.send_message(bot.token, chat, text, reply_markup=markup)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("platform bot send failed: %s", type(exc).__name__)
        return False


def handle(update: dict) -> str:
    bot = bots.platform_bot()
    if bot is None:
        return "off"
    if "member" in update:
        return _member(bot, update["member"])
    if "callback" in update:
        return _callback(bot, update["callback"])
    message = update.get("message")
    if not message:
        return "skip"
    if message.get("chat_type") != "private":
        return "skip"  # групповые сообщения не читаем
    if message.get("is_bot") or not message.get("from_id"):
        return "skip"
    if str(message.get("chat_id")) != str(message.get("from_id")):
        return "skip"  # личный чат: chat.id == from.id
    with translation.override(locale_for(message.get("language_code"))):
        return _private(bot, message)


def _member(bot, member: dict) -> str:
    from apps.telegram import services

    if member.get("chat_type") in GROUP_TYPES and member.get("status") in (
        "member",
        "administrator",
    ):
        services.leave_chat(bot.token, member.get("chat_id"))
        return "left"
    if member.get("chat_type") == "private" and member.get("status") == "kicked":
        links.mark_blocked(member.get("from_id") or member.get("chat_id"))
        return "blocked"
    return "skip"


def _callback(bot, callback: dict) -> str:
    from apps.telegram import services

    services.answer_callback_query(bot.token, callback.get("id") or "")
    return "skip"


def _start_url() -> str:
    from apps.tenants.quickstart import domain_base

    return f"https://{domain_base()}/aktion-starten/"


def _private(bot, message: dict) -> str:
    chat = message["chat_id"]
    has_business = links.active_links(message["from_id"]).exists()
    if has_business:
        send(
            bot,
            chat,
            _(
                "Willkommen zurück! Schicken Sie z. B.: „Brötchen 2,50 € statt 3,90 €, heute bis 18 Uhr, 20 Stück“ — gern mit Foto."
            ),
        )
        return "welcome_back"
    send(
        bot,
        chat,
        _(
            "Hallo! Ich veröffentliche Aktionen für Geschäfte in Ihrer Stadt — mit eigener Seite, QR-Code und Aushang."
        ),
        {"inline_keyboard": [[{"text": "⚡ " + _("Aktion starten"), "url": _start_url()}]]},
    )
    return "onboarding"
