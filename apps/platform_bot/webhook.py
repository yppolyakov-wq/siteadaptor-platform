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

from apps.telegram import bots

logger = logging.getLogger(__name__)

TEXT_MAX = 2000


def _secret() -> str:
    return getattr(settings, "TELEGRAM_PLATFORM_WEBHOOK_SECRET", "") or ""


def _int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def slim(update: dict) -> dict:
    """Только поля, нужные обработчику (в брокер не уходит весь апдейт)."""
    out = {"update_id": update.get("update_id")}
    message = update.get("message")
    if isinstance(message, dict):
        chat = _dict(message.get("chat"))
        sender = _dict(message.get("from"))
        photos = message.get("photo") if isinstance(message.get("photo"), list) else []
        largest = photos[-1].get("file_id") if photos and isinstance(photos[-1], dict) else ""
        out["message"] = {
            "chat_id": _int(chat.get("id")),
            "chat_type": str(chat.get("type") or "")[:16],
            "from_id": _int(sender.get("id")),
            "is_bot": bool(sender.get("is_bot")),
            "language_code": str(sender.get("language_code") or "")[:8],
            "text": str(message.get("text") or message.get("caption") or "")[:TEXT_MAX],
            "photo": str(largest or "")[:200],
            "media_group_id": str(message.get("media_group_id") or "")[:64],
        }
    callback = update.get("callback_query")
    if isinstance(callback, dict):
        sender = _dict(callback.get("from"))
        cmsg = _dict(callback.get("message"))
        out["callback"] = {
            "id": str(callback.get("id") or "")[:64],
            "from_id": _int(sender.get("id")),
            "language_code": str(sender.get("language_code") or "")[:8],
            "chat_id": _int(_dict(cmsg.get("chat")).get("id")),
            "message_id": _int(cmsg.get("message_id")),
            "data": str(callback.get("data") or "")[:64],
        }
    member = update.get("my_chat_member")
    if isinstance(member, dict):
        chat = _dict(member.get("chat"))
        out["member"] = {
            "chat_id": _int(chat.get("id")),
            "chat_type": str(chat.get("type") or "")[:16],
            "from_id": _int(_dict(member.get("from")).get("id")),
            "status": str(_dict(member.get("new_chat_member")).get("status") or "")[:16],
        }
    return out


def _same(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


@csrf_exempt
def webhook(request):
    # Путь без секрета (он попадал бы в логи прокси и Sentry) — секрет только в заголовке
    # X-Telegram-Bot-Api-Secret-Token. Выключенный бот и чужой метод — 404, не 405.
    expected = _secret()
    if not bots.platform_enabled() or len(expected) < 24 or request.method != "POST":
        raise Http404
    if not _same(request.headers.get("X-Telegram-Bot-Api-Secret-Token", ""), expected):
        raise Http404
    try:
        update = json.loads(request.body.decode() or "{}")
    except (ValueError, UnicodeDecodeError):
        return HttpResponse("ok")
    if not isinstance(update, dict) or not isinstance(update.get("update_id"), int):
        return HttpResponse("ok")
    from . import tasks

    try:
        tasks.platform_bot_update.delay(
            dedupe_key=tasks.dedupe_key(update["update_id"]), update=slim(update)
        )
    except Exception as exc:  # noqa: BLE001 — брокер недоступен: Telegram повторит доставку
        logger.warning("platform bot enqueue failed: %s", type(exc).__name__)
        return HttpResponse(status=503)
    return HttpResponse("ok")
