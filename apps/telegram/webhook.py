"""Обработка апдейтов Telegram (M23/TG1).

v1: на /start (и любое сообщение) бот отвечает кнопкой, открывающей витрину как
Telegram Web App (Mini App). Логику держим тонкой и чистой — тестируем напрямую.
"""

from django.urls import reverse
from django.utils.translation import gettext as _

from . import services


def handle_update(bot, update: dict, request) -> str:
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = (message.get("text") or "").strip()
    if not chat_id:
        return "skip"

    # MT-3b: в ГРУППЕ бот ведёт себя иначе — там он мост пространства поездки,
    # а не витрина. Обрабатываем до общей ветки, чтобы группе не слать Mini App.
    if (chat.get("type") or "") in ("group", "supergroup"):
        return _handle_group(bot, message, chat_id)

    shop_url = request.build_absolute_uri(reverse("storefront-home"))
    markup = {"inline_keyboard": [[{"text": _("🛍 Open shop"), "web_app": {"url": shop_url}}]]}
    # /start <token> — привязка к боту: owner-<token> = владелец (UD4c), иначе
    # клиент (TG3). Дальше шлём соответствующие уведомления в этот чат.
    if text.startswith("/start"):
        from .notify import link_from_start, link_owner_from_start

        payload = text[len("/start") :].strip()
        tenant = getattr(request, "tenant", None)
        if payload.startswith("owner-") and tenant is not None:
            linked = link_owner_from_start(payload, chat_id, tenant)
        else:
            linked = bool(payload) and link_from_start(payload, chat_id)
        if linked:
            body = _("✅ Connected! You'll get your updates here.")
        else:
            body = _("Welcome! Tap below to open the shop.")
    else:
        body = _("Tap below to open the shop.")
    services.send_message(bot.token, chat_id, body, reply_markup=markup)
    return "sent"


def _handle_group(bot, message: dict, chat_id) -> str:
    """Групповой апдейт: команда привязки или сообщение в ленту (MT-3b).

    Мост живёт в apps/community — телеграм-слой только маршрутизирует, чтобы
    знание о пространствах поездки не растекалось по обоим приложениям.
    """
    from apps.community.telegram_bridge import ingest_group_message, try_link

    reply = try_link(bot, message)
    if reply:
        services.send_message(bot.token, chat_id, reply)
        return "linked"
    return "ingested" if ingest_group_message(bot, message) else "skip"
