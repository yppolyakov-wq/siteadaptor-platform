"""Общий разбор апдейтов Telegram ботов платформы и порталов (T-8.10h / T-8.28).

`slim` — только поля, нужные обработчикам (в брокер не уходит весь апдейт), `locale_for` —
язык ответа по `language_code` пользователя, кламп к языкам кабинета.
"""

from __future__ import annotations

from django.conf import settings

TEXT_MAX = 2000


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
            # H-5: «Meine Nummer senden» при регистрации — только номер и чей он.
            "contact_phone": str(_dict(message.get("contact")).get("phone_number") or "")[:30],
            "contact_user_id": _int(_dict(message.get("contact")).get("user_id")),
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


def locale_for(language_code: str) -> str:
    code = str(language_code or "")[:2].lower()
    return code if code in getattr(settings, "CABINET_LANGUAGES", ()) else "de"
