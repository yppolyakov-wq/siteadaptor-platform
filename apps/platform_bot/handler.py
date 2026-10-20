"""T-8.10h: обработка апдейтов общего бота (Celery, public-схема).

H-2: только каркас — личный чат получает приветствие, группы бот покидает, блокировка
бота пользователем отмечается. Подключение бизнеса (H-3), акции (H-4) и регистрация
(H-5) достраиваются поверх. Клиенты бизнеса этим ботом не обслуживаются: у него нет
витрины, Mini App и клиентских уведомлений — только владельцы.
"""

from __future__ import annotations

import logging
import re

from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext as _

from apps.telegram import bots

from . import links

logger = logging.getLogger(__name__)

GROUP_TYPES = ("group", "supergroup", "channel")
CONNECT_RE = re.compile(r"^/start(?:@\w+)?\s+b-(\S+)\s*$")
CHOOSE_RE = re.compile(r"^/geschaeft(?:@\w+)?\s*$", re.IGNORECASE)
CHOOSE_CALLBACK_RE = re.compile(
    r"^g:([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$"
)
START_RE = re.compile(r"^/start(?:@\w+)?(?:\s.*)?$", re.DOTALL)
NEW_RE = re.compile(r"^/neu(?:@\w+)?\s*$", re.IGNORECASE)
CANCEL_RE = re.compile(r"^/(?:abbrechen|cancel)(?:@\w+)?\s*$", re.IGNORECASE)
CHOOSE_MAX = 20
CONNECT_LIMIT = 10  # попыток привязки на пользователя Telegram в час


def locale_for(language_code: str) -> str:
    code = str(language_code or "")[:2].lower()
    return code if code in getattr(settings, "CABINET_LANGUAGES", ()) else "de"


def send(bot, chat, text: str, markup=None) -> bool:
    """Ответ без утечки токена: текст HTTPError содержит URL с токеном бота."""
    from apps.telegram import services

    try:
        services.send_message(bot.token, chat, text, reply_markup=markup)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("platform bot send failed: %s", type(exc).__name__)
        return False


def handle(update: dict) -> str:
    bot = bots.platform_bot()
    if bot is None:
        return "off"
    if "member" in update:
        return _member(bot, update["member"])
    if "callback" in update:
        return _callback(bot, update["callback"])
    message = update.get("message")
    if not message:
        return "skip"
    if message.get("chat_type") != "private":
        return "skip"  # групповые сообщения не читаем
    if message.get("is_bot") or not message.get("from_id"):
        return "skip"
    if str(message.get("chat_id")) != str(message.get("from_id")):
        return "skip"  # личный чат: chat.id == from.id
    with translation.override(locale_for(message.get("language_code"))):
        return _private(bot, message, update.get("update_id"))


def _member(bot, member: dict) -> str:
    from apps.telegram import services

    if member.get("chat_type") in GROUP_TYPES and member.get("status") in (
        "member",
        "administrator",
    ):
        services.leave_chat(bot.token, member.get("chat_id"))
        return "left"
    if member.get("chat_type") == "private" and member.get("status") == "kicked":
        links.mark_blocked(member.get("from_id") or member.get("chat_id"))
        return "blocked"
    if member.get("chat_type") == "private" and member.get("status") == "member":
        links.mark_unblocked(member.get("from_id") or member.get("chat_id"))
        return "unblocked"
    return "skip"


def _callback(bot, callback: dict) -> str:
    from apps.telegram import services

    from . import routing

    data = str(callback.get("data") or "")
    if data.startswith(routing.PREFIX):
        return _promo_callback(bot, callback, data)
    if data.startswith("ps:"):
        from . import signup

        with translation.override(locale_for(callback.get("language_code"))):
            return signup.on_callback(bot, callback)
    services.answer_callback_query(bot.token, callback.get("id") or "")
    match = CHOOSE_CALLBACK_RE.match(data)
    if not match:
        return "skip"
    from_id = callback.get("from_id")
    if not from_id or callback.get("chat_id") != from_id:
        return "skip"
    with translation.override(locale_for(callback.get("language_code"))):
        link = links.select(from_id, match.group(1))
        if link is None:
            send(bot, from_id, _("Nicht verfügbar."))
            return "choose_denied"
        send(bot, from_id, _("Aktuelles Geschäft: %(name)s") % {"name": link.tenant.name})
    return "chosen"


def _start_url() -> str:
    from apps.tenants.quickstart import domain_base

    return f"https://{domain_base()}/aktion-starten/"


def _private(bot, message: dict, update_id=None) -> str:
    chat = message["chat_id"]
    links.mark_unblocked(message["from_id"])  # пишет боту — значит, не заблокировал
    text = (message.get("text") or "").strip()
    match = CONNECT_RE.match(text)
    if match:
        return _connect(bot, message, match.group(1))
    if CHOOSE_RE.match(text):
        return _choose(bot, message)
    # H-5b: регистрация (в т. ч. второго бизнеса) — раньше конвейера акций: пока идёт
    # диалог регистрации, сообщения — его шаги, а не текст акции.
    routed = _signup_message(bot, message, text)
    if routed:
        return routed
    current = links.active_links(message["from_id"]).first()
    if current is not None and not START_RE.match(text):
        return _promo_message(bot, message, current, update_id)
    if current is None:
        from . import signup

        reminded = signup.remind_pending(bot, message["from_id"], chat)
        if reminded:
            return reminded
    if current is not None:
        send(
            bot,
            chat,
            _(
                "Willkommen zurück! Schicken Sie z. B.: „Brötchen 2,50 € statt 3,90 €, heute bis 18 Uhr, 20 Stück“ — gern mit Foto."
            ),
        )
        return "welcome_back"
    return _private_onboarding(bot, chat)


def _private_onboarding(bot, chat) -> str:
    send(
        bot,
        chat,
        _(
            "Hallo! Ich veröffentliche Aktionen für Geschäfte in Ihrer Stadt — mit eigener Seite, QR-Code und Aushang."
        ),
        {
            "inline_keyboard": [
                [{"text": "💬 " + _("Hier im Chat starten"), "callback_data": "ps:go"}],
                [{"text": "⚡ " + _("Aktion starten"), "url": _start_url()}],
            ]
        },
    )
    return "onboarding"


def _signup_message(bot, message: dict, text: str) -> str:
    """H-5: регистрация в чате для тех, у кого ещё нет бизнеса ('' — не наш случай)."""
    from . import signup

    uid, chat = message["from_id"], message["chat_id"]
    if CANCEL_RE.match(text):
        return signup.cancel(bot, uid, chat)
    if NEW_RE.match(text):
        return signup.start(bot, uid, chat, message.get("language_code") or "")
    state = signup.load(uid)
    if state is None:
        return ""
    if START_RE.match(text):
        return signup.resume(bot, uid, chat, state)
    return signup.on_message(bot, message, state)


def _invalid(bot, chat) -> str:
    send(
        bot,
        chat,
        _("Link ungültig oder abgelaufen. Bitte im Kabinett einen neuen Link erzeugen."),
    )
    return "connect_invalid"


def _owner_in_schema(payload: dict) -> bool:
    """Право перепроверяется В МОМЕНТ привязки: ссылку мог выпустить уже не владелец.
    Ошибка БД не глотается — `_connect` вернёт токен, повтор апдейта пройдёт."""
    from django_tenants.utils import schema_context

    from apps.core.models import Membership

    with schema_context(payload["schema"]):
        return Membership.objects.filter(
            user_id=payload["user_pk"],
            user__is_active=True,
            role=Membership.ROLE_OWNER,
        ).exists()


def _connect(bot, message: dict, raw: str) -> str:
    """`/start b-<токен>` из кабинета — привязать бизнес к этому чату."""
    from apps.core import ratelimit
    from apps.tenants.models import Tenant

    from . import connect

    chat, from_id = message["chat_id"], message["from_id"]
    if ratelimit.hit("tgplat-connect", str(from_id), limit=CONNECT_LIMIT, window=3600):
        return _invalid(bot, chat)
    payload = connect.consume(raw)
    if payload is None:
        return _invalid(bot, chat)
    try:
        tenant = Tenant.objects.filter(
            schema_name=payload.get("schema") or "", pk=payload.get("tenant_pk")
        ).first()
        if tenant is None or not _owner_in_schema(payload):
            return _invalid(bot, chat)
        link = links.bind(
            from_id,
            tenant,
            via=links.OwnerTelegramLink.VIA_CABINET,
            user_pk=payload.get("user_pk"),
        )
    except Exception:
        connect.restore(raw, payload)  # сбой — не вина ссылки: повтор её примет
        raise
    text = _("✅ Verbunden mit %(name)s. Benachrichtigungen kommen ab jetzt hier.") % {
        "name": tenant.name
    }
    if links.active_links(from_id).count() > 1:
        text += "\n" + _("Mit /geschaeft wechseln Sie das Geschäft.")
    send(bot, chat, text)
    from . import tasks

    tasks.enqueue_connected_email(link, payload)
    return "connected"


def _choose(bot, message: dict) -> str:
    chat, from_id = message["chat_id"], message["from_id"]
    owned = list(links.active_links(from_id)[:CHOOSE_MAX])
    if not owned:
        return _private_onboarding(bot, chat)
    current = owned[0]
    new_row = [{"text": "➕ " + _("Neues Geschäft"), "callback_data": "ps:go"}]
    if len(owned) == 1:
        send(
            bot,
            chat,
            _("Aktuelles Geschäft: %(name)s") % {"name": current.tenant.name},
            {"inline_keyboard": [new_row]},
        )
        return "choose_single"
    keyboard = [
        [
            {
                "text": ("✓ " if link.pk == current.pk else "") + link.tenant.name[:60],
                "callback_data": f"g:{link.pk}",
            }
        ]
        for link in owned
    ]
    keyboard.append(new_row)
    send(
        bot,
        chat,
        _("Sie haben mehrere Geschäfte. Wählen Sie das aktuelle:"),
        {"inline_keyboard": keyboard},
    )
    return "choose_menu"


# --- H-4: акции через общий бот -----------------------------------------------------------


def _promo_message(bot, message: dict, link, update_id) -> str:
    """Текст/фото/альбом/команда владельца → тот же конвейер акций, что у своего бота,
    в схеме ТЕКУЩЕГО бизнеса (права перепроверяются там по таблице связей)."""
    from apps.core import ratelimit
    from apps.promotions import telegram_promo

    schema = link.tenant.schema_name
    chat = str(message["chat_id"])
    if ratelimit.hit("tg-promo", f"{schema}:{chat}", limit=telegram_promo.RATE_LIMIT, window=3600):
        send(bot, chat, _("Zu viele Entwürfe — bitte später erneut versuchen."))
        return "limited"
    update = {
        "update_id": update_id,
        "chat_id": message["chat_id"],
        "text": message.get("text") or "",
        "photo": message.get("photo") or "",
        "media_group_id": message.get("media_group_id") or "",
        "language_code": message.get("language_code") or "",
    }
    result = telegram_promo.handle_owner_message(schema, update, bot_kind=bots.PLATFORM)
    if result == "skip":
        send(bot, chat, _("Nicht verfügbar — bitte im Kabinett neu verbinden."))
        return "denied"
    return result


def _promo_callback(bot, callback: dict, data: str) -> str:
    """Кнопка превью `pb:` → схема превью из кэша (только для того, кому её показали)."""
    from apps.promotions import telegram_promo
    from apps.telegram import services

    from . import routing

    from_id = callback.get("from_id")
    cid = callback.get("id") or ""
    if not from_id or callback.get("chat_id") != from_id:
        services.answer_callback_query(bot.token, cid)
        return "skip"
    resolved = routing.resolve(from_id, data)
    if resolved is None:
        with translation.override(locale_for(callback.get("language_code"))):
            services.answer_callback_query(bot.token, cid, _("Abgelaufen."))
        return "expired"
    schema, inner = resolved
    return telegram_promo.handle_platform_callback(bot, schema, callback, inner)
