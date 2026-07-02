"""Публичный webhook Telegram (M23/TG1): POST /tg/<secret>/.

На домене арендатора (TenantMainMiddleware резолвит схему по хосту), без логина и
CSRF. secret в пути + опц. заголовок X-Telegram-Bot-Api-Secret-Token. Всегда
отвечаем 200, чтобы Telegram не ретраил (ошибки гасим).
"""

import hmac
import json
import logging

from django.http import Http404, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import TelegramBot
from .webhook import handle_update

logger = logging.getLogger("telegram")


@csrf_exempt
@require_POST
def webhook(request, secret):
    bot = (
        TelegramBot.objects.filter(webhook_secret=secret, is_active=True).exclude(token="").first()
    )
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
    except Exception:  # noqa: BLE001 — webhook всегда 200, иначе Telegram ретраит
        logger.exception("telegram webhook failed")
    return HttpResponse("ok")
