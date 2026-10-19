"""T-8.10h H-2: вебхук общего бота платформы (публичный хост).

Вебхук только сверяет секрет (путь + заголовок, constant-time), урезает апдейт до нужных
полей и ставит задачу с дедупом по update_id: повторы Telegram не плодят действий, а
запрос не висит на HTTP-вызовах. Ответ — всегда 200 (иначе Telegram копит ретраи).
"""

from __future__ import annotations

import hmac
import json
import logging

from django.conf import settings
from django.http import Http404, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.telegram import bots

logger = logging.getLogger(__name__)

TEXT_MAX = 2000


def _secret() -> str:
    return getattr(settings, "TELEGRAM_PLATFORM_WEBHOOK_SECRET", "") or ""


def slim(update: dict) -> dict:
    """Только поля, нужные обработчику (в брокер не уходит весь апдейт)."""
    out = {"update_id": update.get("update_id")}
    message = update.get("message")
    if isinstance(message, dict):
        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        photos = message.get("photo") or []
        largest = photos[-1].get("file_id") if photos and isinstance(photos[-1], dict) else ""
        out["message"] = {
            "chat_id": chat.get("id"),
            "chat_type": str(chat.get("type") or "")[:16],
            "from_id": sender.get("id"),
            "is_bot": bool(sender.get("is_bot")),
            "language_code": str(sender.get("language_code") or "")[:8],
            "text": str(message.get("text") or message.get("caption") or "")[:TEXT_MAX],
            "photo": str(largest or "")[:200],
            "media_group_id": str(message.get("media_group_id") or "")[:64],
        }
    callback = update.get("callback_query")
    if isinstance(callback, dict):
        sender = callback.get("from") or {}
        cmsg = callback.get("message") or {}
        out["callback"] = {
            "id": str(callback.get("id") or "")[:64],
            "from_id": sender.get("id"),
            "language_code": str(sender.get("language_code") or "")[:8],
            "chat_id": (cmsg.get("chat") or {}).get("id"),
            "message_id": cmsg.get("message_id"),
            "data": str(callback.get("data") or "")[:64],
        }
    member = update.get("my_chat_member")
    if isinstance(member, dict):
        chat = member.get("chat") or {}
        out["member"] = {
            "chat_id": chat.get("id"),
            "chat_type": str(chat.get("type") or "")[:16],
            "from_id": (member.get("from") or {}).get("id"),
            "status": str((member.get("new_chat_member") or {}).get("status") or "")[:16],
        }
    return out


@csrf_exempt
@require_POST
def webhook(request, secret):
    expected = _secret()
    if not bots.platform_enabled() or not expected:
        raise Http404
    header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not (hmac.compare_digest(secret, expected) and hmac.compare_digest(header, expected)):
        raise Http404
    try:
        update = json.loads(request.body.decode() or "{}")
    except (ValueError, UnicodeDecodeError):
        return HttpResponse("ok")
    if not isinstance(update, dict) or update.get("update_id") is None:
        return HttpResponse("ok")
    from . import tasks

    try:
        tasks.platform_bot_update.delay(
            dedupe_key=f"tgplat:{update['update_id']}", update=slim(update)
        )
    except Exception as exc:  # noqa: BLE001 — брокер недоступен: Telegram повторит доставку
        logger.warning("platform bot enqueue failed: %s", type(exc).__name__)
        return HttpResponse(status=503)
    return HttpResponse("ok")
