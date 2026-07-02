"""Telegram-бот портала агрегатора (TG4): webhook + подключение.

Переиспользуем generic Bot API из apps.telegram.services (чистые HTTP-функции).
На /start бот открывает выдачу портала как Telegram Mini App (web_app → portal
home). Подключение (connect_bot) ставит webhook на хост портала.
"""

import hmac
import json

from django.http import Http404, HttpResponse
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.telegram import services as tg

from .models import PortalBot


def connect_bot(bot: PortalBot) -> dict:
    """Проверить токен (getMe), сохранить username и поставить webhook на хост портала."""
    me = tg.get_me(bot.token)
    bot.bot_username = me.get("username", "")
    url = f"https://{bot.portal.host}/tg/{bot.webhook_secret}/"
    tg.set_webhook(bot.token, url, bot.webhook_secret)
    bot.is_active = True
    bot.save(update_fields=["bot_username", "is_active", "updated_at"])
    return me


def disconnect_bot(bot: PortalBot) -> None:
    if bot.token:
        try:
            tg.delete_webhook(bot.token)
        except Exception:  # noqa: BLE001 — отключение не должно падать
            pass
    bot.is_active = False
    bot.save(update_fields=["is_active", "updated_at"])


def handle_update(bot: PortalBot, update: dict, request) -> str:
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if not chat_id:
        return "skip"
    portal_url = request.build_absolute_uri(reverse("portal-home"))
    markup = {"inline_keyboard": [[{"text": _("🔎 Open"), "web_app": {"url": portal_url}}]]}
    tg.send_message(bot.token, chat_id, _("Welcome! Tap below to explore local offers."), markup)
    return "sent"


@csrf_exempt
@require_POST
def webhook(request, secret):
    bot = PortalBot.objects.filter(webhook_secret=secret, is_active=True).exclude(token="").first()
    if bot is None:
        raise Http404
    # secret_token заголовок ОБЯЗАТЕЛЕН (set_webhook всегда его задаёт) и сверяется
    # constant-time; пустой/чужой → 404 (закрывает обход пустым заголовком).
    header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(header, bot.webhook_secret):
        raise Http404
    try:
        update = json.loads(request.body.decode() or "{}")
    except ValueError:
        return HttpResponse("ok")
    try:
        handle_update(bot, update, request)
    except Exception:  # noqa: BLE001 — webhook всегда 200
        pass
    return HttpResponse("ok")
