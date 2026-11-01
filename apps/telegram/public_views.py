"""Публичный webhook Telegram (M23/TG1): POST /tg/<secret>/.

На домене арендатора (TenantMainMiddleware резолвит схему по хосту), без логина и
CSRF. secret в пути + опц. заголовок X-Telegram-Bot-Api-Secret-Token. Всегда
отвечаем 200, чтобы Telegram не ретраил (ошибки гасим).
"""

import hmac
import json
import logging

from django.core.cache import cache
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
    # SEC-A1: compare_digest на str падает TypeError (500) на не-ASCII — сравниваем bytes.
    if not hmac.compare_digest(header.encode("utf-8"), bot.webhook_secret.encode("utf-8")):
        raise Http404
    from apps.core import ratelimit

    if ratelimit.hit("tg-tenant-hook", ratelimit.client_ip(request), limit=600, window=60):
        return HttpResponse(status=429)
    try:
        update = json.loads(request.body.decode() or "{}")
    except (ValueError, UnicodeDecodeError):
        return HttpResponse("ok")
    if not isinstance(update, dict):
        return HttpResponse("ok")
    # SEC-A1: Telegram повторяет доставку — один update_id обрабатываем один раз
    # (дедуп как у общего бота и бота портала; обработка здесь синхронная).
    update_id = update.get("update_id")
    if isinstance(update_id, int) and not cache.add(
        f"tgtenant:{bot.pk}:{update_id}", "1", timeout=86400
    ):
        return HttpResponse("ok")
    try:
        handle_update(bot, update, request)
    except Exception as exc:  # noqa: BLE001 — webhook всегда 200, иначе Telegram ретраит
        # Текст/трейсбэк исключения может нести URL с токеном бота — только тип (SEC-A1).
        logger.warning("telegram webhook failed: %s", type(exc).__name__)
    return HttpResponse("ok")
