"""Двусторонний мост «пространство поездки ↔ Telegram-группа» (MT-3b).

Гид добавляет бота бизнеса в группу тура и пишет там `/link <код>` — код виден в
кабинете заезда. С этого момента:

* запись ленты из веба уезжает в группу;
* сообщение из группы становится репликой чата пространства.

Эхо гасится источником: пришедшее из Telegram обратно не отправляется, а повтор
того же `message_id` не создаёт дубль (уникальный индекс + идемпотентный
`services.add_post`).

⚠️ Эксплуатация: у бота в @BotFather должен быть выключен privacy mode
(`/setprivacy → Disable`), иначе Telegram отдаёт боту только команды, и обычные
сообщения группы до нас не доходят.
"""

import logging

from .models import FeedPost, FeedSpace
from .services import add_post

logger = logging.getLogger(__name__)

LINK_COMMAND = "/link"


def _group_chat(message: dict) -> str:
    chat = message.get("chat") or {}
    if chat.get("type") not in ("group", "supergroup"):
        return ""
    chat_id = chat.get("id")
    return str(chat_id) if chat_id else ""


def _sender_name(message: dict) -> str:
    sender = message.get("from") or {}
    name = " ".join(x for x in (sender.get("first_name"), sender.get("last_name")) if x)
    return (name or sender.get("username") or "").strip()[:120]


def _customer_by_chat(sender_id) -> object | None:
    """Сопоставить автора с клиентом — если он привязывал бота в личном чате."""
    if not sender_id:
        return None
    from apps.telegram.models import TelegramLink

    link = TelegramLink.objects.filter(chat_id=str(sender_id)).select_related("customer").first()
    return link.customer if link else None


def try_link(bot, message: dict) -> str:
    """Обработать `/link <код>` в группе. → ответ боту или '' (не наша команда).

    Команда в группе приходит как `/link@botname <код>` — учитываем.
    """
    chat_id = _group_chat(message)
    text = (message.get("text") or "").strip()
    if not chat_id or not text.startswith(LINK_COMMAND):
        return ""
    payload = text[len(LINK_COMMAND) :]
    if payload.startswith("@"):  # /link@botname
        payload = payload.split(" ", 1)[1] if " " in payload else ""
    code = payload.strip()[:20]
    space = FeedSpace.objects.filter(tg_link_code=code).first() if code else None
    if space is None:
        return "Kein passender Code — bitte den Code aus dem Dashboard verwenden."
    space.tg_chat_id = chat_id
    space.save(update_fields=["tg_chat_id", "updated_at"])
    return f"✅ Verbunden mit «{space.title}». Beiträge laufen ab jetzt in beide Richtungen."


def ingest_group_message(bot, message: dict) -> bool:
    """Сообщение из привязанной группы → реплика чата пространства. → сохранено ли."""
    chat_id = _group_chat(message)
    if not chat_id:
        return False
    space = FeedSpace.objects.filter(tg_chat_id=chat_id).first()
    if space is None or not space.is_open:
        return False
    body = (message.get("text") or message.get("caption") or "").strip()
    if not body:
        # Медиа без подписи: сохраняем факт сообщения, чтобы группа не «теряла» его.
        body = "📎"
    sender = message.get("from") or {}
    add_post(
        space,
        body=body,
        kind=FeedPost.KIND_MESSAGE,
        customer=_customer_by_chat(sender.get("id")),
        name=_sender_name(message),
        source=FeedPost.SOURCE_TELEGRAM,
        external_ref=str(message.get("message_id") or "")[:64],
    )
    return True


def push_to_group(post) -> bool:
    """Отправить запись из веба в привязанную группу. → отправлено ли.

    Fail-safe: сбой Telegram не должен ронять публикацию — логируем и молчим.
    """
    space = post.space
    if not space.tg_chat_id or post.source == FeedPost.SOURCE_TELEGRAM:
        return False
    from apps.telegram.notify import active_bot
    from apps.telegram.services import send_message

    bot = active_bot()
    if bot is None:
        return False
    text = f"{post.author_label}: {post.body}".strip()
    try:
        send_message(bot.token, space.tg_chat_id, text[:4000])
    except Exception:  # noqa: BLE001
        logger.exception("telegram push failed for post %s", post.pk)
        return False
    return True
