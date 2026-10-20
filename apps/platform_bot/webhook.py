"""T-8.10h H-2: вебхук общего бота платформы (публичный хост).

Вебхук только сверяет секрет (путь + заголовок, constant-time), урезает апдейт до нужных
полей и ставит задачу с дедупом по update_id: повторы Telegram не плодят действий, а
запрос не висит на HTTP-вызовах. Ответ — всегда 200 (иначе Telegram копит ретраи).
"""

from __future__ import annotations

import hmac
import json
import logging

from django.http import Http404, HttpResponse
from django.views.decorators.csrf import csrf_exempt

from apps.telegram import bots
from apps.telegram.updates import TEXT_MAX, slim  # noqa: F401 — общий разбор (тесты, задачи)

logger = logging.getLogger(__name__)


def _secret() -> str:
    from . import config

    return config.webhook_secret()


def _same(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


@csrf_exempt
def webhook(request):
    # Путь без секрета (он попадал бы в логи прокси и Sentry) — секрет только в заголовке
    # X-Telegram-Bot-Api-Secret-Token. Выключенный бот и чужой метод — 404, не 405.
    # Дешёвый отказ ДО обращения к настройкам (БД): чужой метод/без заголовка — сразу 404.
    header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if request.method != "POST" or not header:
        raise Http404
    try:
        expected = _secret()
        enabled = bots.platform_enabled()
    except Exception as exc:  # noqa: BLE001 — БД недоступна: 404, Telegram повторит позже
        logger.warning("platform bot config unavailable: %s", type(exc).__name__)
        raise Http404 from None
    if not enabled or len(expected) < 24 or not _same(header, expected):
        raise Http404
    try:
        update = json.loads(request.body.decode() or "{}")
    except (ValueError, UnicodeDecodeError):
        return HttpResponse("ok")
    if not isinstance(update, dict) or not isinstance(update.get("update_id"), int):
        return HttpResponse("ok")
    from . import config, tasks

    config.mark_update()
    try:
        tasks.platform_bot_update.delay(
            dedupe_key=tasks.dedupe_key(update["update_id"]), update=slim(update)
        )
    except Exception as exc:  # noqa: BLE001 — брокер недоступен: Telegram повторит доставку
        logger.warning("platform bot enqueue failed: %s", type(exc).__name__)
        return HttpResponse(status=503)
    return HttpResponse("ok")
