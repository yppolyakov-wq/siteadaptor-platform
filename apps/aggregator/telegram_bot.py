"""Telegram-бот портала агрегатора (TG4 → T-8.28): подключение + вебхук.

Вебхук только сверяет секрет, урезает апдейт и ставит задачу Celery с дедупом по
update_id; разговор ведёт `portal_bot.handle`. Подключение ставит webhook на хост
портала и меню команд на языках кабинета.
"""

import hmac
import json
import logging

from django.conf import settings
from django.http import Http404, HttpResponse
from django.utils import translation
from django.views.decorators.csrf import csrf_exempt

from apps.telegram import services as tg
from apps.telegram.updates import slim

from .models import PortalBot

logger = logging.getLogger(__name__)


def set_commands(bot: PortalBot) -> None:
    """Меню команд на всех языках кабинета (сбой — не ошибка подключения)."""
    from . import portal_bot

    for lang in ("", *getattr(settings, "CABINET_LANGUAGES", ())):
        with translation.override(lang or "de"):
            items = portal_bot.commands()
        try:
            tg.set_my_commands(bot.token, items, language_code=lang)
        except Exception as exc:  # noqa: BLE001
            logger.warning("portal bot commands failed: %s", type(exc).__name__)


def connect_bot(bot: PortalBot) -> dict:
    """Проверить токен (getMe), сохранить username и поставить webhook на хост портала."""
    me = tg.get_me(bot.token)
    bot.bot_username = me.get("username", "")
    url = f"https://{bot.portal.host}/tg/{bot.webhook_secret}/"
    tg.set_webhook(bot.token, url, bot.webhook_secret)
    bot.is_active = True
    bot.save(update_fields=["bot_username", "is_active", "updated_at"])
    set_commands(bot)
    return me


def disconnect_bot(bot: PortalBot) -> None:
    if bot.token:
        try:
            tg.delete_webhook(bot.token)
        except Exception:  # noqa: BLE001 — отключение не должно падать
            pass
    bot.is_active = False
    bot.save(update_fields=["is_active", "updated_at"])


def dedupe_key(bot_pk: int, update_id) -> str:
    return f"tgportal:{bot_pk}:{update_id}"


@csrf_exempt
def webhook(request, secret):
    # Дешёвый отказ до чтения бота: только POST и заголовок Telegram. Бот — ТОЛЬКО бот
    # портала этого хоста (fail-closed без портала); заголовок сверяется с ХРАНИМЫМ
    # секретом бота (путь — лишь адрес, из логов прокси его подделать нельзя).
    header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    portal = getattr(request, "portal", None)
    if request.method != "POST" or len(header) < 24 or portal is None:
        raise Http404
    from apps.core import ratelimit

    if ratelimit.hit("tgportal-hook", ratelimit.client_ip(request), limit=600, window=60):
        return HttpResponse(status=429)
    bot = (
        PortalBot.objects.filter(portal=portal, is_active=True)
        .exclude(token="")
        .only("pk", "webhook_secret")
        .first()
    )
    if bot is None or not bot.webhook_secret:
        raise Http404
    if not hmac.compare_digest(header.encode(), bot.webhook_secret.encode()):
        raise Http404
    if not hmac.compare_digest(str(secret).encode(), bot.webhook_secret.encode()):
        raise Http404
    try:
        update = json.loads(request.body.decode() or "{}")
    except (ValueError, UnicodeDecodeError):
        return HttpResponse("ok")
    if not isinstance(update, dict) or not isinstance(update.get("update_id"), int):
        return HttpResponse("ok")
    from .tasks import portal_bot_update

    try:
        portal_bot_update.delay(
            dedupe_key=dedupe_key(bot.pk, update["update_id"]), bot_pk=bot.pk, update=slim(update)
        )
    except Exception as exc:  # noqa: BLE001 — брокер недоступен: Telegram повторит доставку
        logger.warning("portal bot enqueue failed: %s", type(exc).__name__)
        return HttpResponse(status=503)
    return HttpResponse("ok")
