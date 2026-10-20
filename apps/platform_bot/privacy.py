"""T-8.10h H-6: DSGVO в общем боте — `/datenschutz` (что храним) и `/daten_loeschen`.

Удаление (Art. 17): все связи пользователя Telegram с бизнесами, его следы в зеркалах
бизнесов, состояние регистрации и (лучшим усилием) черновики/ссылки кнопок в кэше.
Бизнесы не удаляются — это делается в кабинете. Подтверждение — одноразовой кнопкой.
"""

from __future__ import annotations

import secrets

from django.core.cache import cache
from django.utils.translation import gettext as _

from . import links

ERASE_TTL = 10 * 60
LIMIT_ERASE = 10  # запросов удаления в час на пользователя


def _send(bot, chat, text, markup=None):
    from .handler import send

    return send(bot, chat, text, markup)


def _privacy_url() -> str:
    from apps.tenants.quickstart import domain_base

    return f"https://{domain_base()}/datenschutz/"


def _nonce_key(uid) -> str:
    return f"tgplat:erase:{int(uid)}"


def _stored_lines(uid) -> list[str]:
    from . import signup

    names = [link.tenant.name for link in links.active_links(uid)[:10]]
    pending = [t.name for t in links.pending_for(uid)[:10]]
    lines = []
    if names:
        lines.append(_("Verbundene Geschäfte: %(names)s") % {"names": ", ".join(names)})
    if pending:
        lines.append(_("Warten auf E-Mail-Bestätigung: %(names)s") % {"names": ", ".join(pending)})
    if signup.load(uid) is not None:
        lines.append(_("Eine begonnene Registrierung (höchstens 2 Stunden)."))
    return lines


def info(bot, uid, chat) -> str:
    lines = [
        "🔒 " + _("Datenschutz"),
        _(
            "Wir speichern Ihre Telegram-ID und die Verbindung zu Ihren Geschäften; Nachrichten "
            "nur, um Aktionen anzulegen oder Ihr Geschäft zu registrieren (Entwürfe höchstens "
            "24 Stunden)."
        ),
        *_stored_lines(uid),
        _("Mehr: %(url)s") % {"url": _privacy_url()},
    ]
    markup = {"inline_keyboard": [[{"text": "🗑 " + _("Daten löschen"), "callback_data": "pd:ask"}]]}
    _send(bot, chat, "\n".join(lines), markup)
    return "privacy_info"


def ask(bot, uid, chat) -> str:
    from apps.core import ratelimit

    if ratelimit.hit("tgplat-erase", str(uid), limit=LIMIT_ERASE, window=3600):
        _send(bot, chat, _("Zu viele Versuche. Bitte später erneut."))
        return "limited"
    stored = _stored_lines(uid)
    if not stored and not links.OwnerTelegramLink.objects.filter(tg_user_id=int(uid)).exists():
        _send(bot, chat, _("Es sind keine Daten mehr gespeichert."))
        return "nothing"
    nonce = secrets.token_urlsafe(8)
    cache.set(_nonce_key(uid), nonce, ERASE_TTL)
    text = "\n".join(
        [
            "🗑 " + _("Alle Ihre Daten in diesem Bot löschen?"),
            *stored,
            _(
                "Ihre Geschäfte bleiben bestehen (löschen im Kabinett); Telegram ist danach nicht "
                "mehr verbunden."
            ),
        ]
    )
    rows = [
        [{"text": "✅ " + _("Ja, löschen"), "callback_data": f"pd:yes:{nonce}"}],
        [{"text": "❌ " + _("Abbrechen"), "callback_data": "pd:no"}],
    ]
    _send(bot, chat, text, {"inline_keyboard": rows})
    return "erase_asked"


def on_callback(bot, callback: dict) -> str:
    from apps.telegram import services

    uid, chat = callback.get("from_id"), callback.get("chat_id")
    services.answer_callback_query(bot.token, callback.get("id") or "")
    if not uid or chat != uid:
        return "skip"
    data = str(callback.get("data") or "")
    if data == "pd:ask":
        return ask(bot, uid, chat)
    if data == "pd:no":
        cache.delete(_nonce_key(uid))
        _send(bot, chat, _("Nichts gelöscht."))
        return "erase_cancelled"
    if data.startswith("pd:yes:"):
        expected = cache.get(_nonce_key(uid))
        if not expected or data[len("pd:yes:") :] != expected or not cache.delete(_nonce_key(uid)):
            _send(bot, chat, _("Abgelaufen. Bitte /daten_loeschen erneut senden."))
            return "erase_expired"
        return erase(bot, uid, chat)
    return "skip"


def erase(bot, uid, chat) -> str:
    from apps.core import cachescan

    from . import signup

    uid = int(uid)
    busy = _("Ihr Geschäft wird gerade angelegt — bitte in ein paar Minuten erneut.")
    with signup._lock(uid) as got:
        # Под замком регистрации: submit ставит «создаётся» тоже под ним — иначе задача
        # провижининга допишет метку/связь уже после удаления.
        if not got or cache.get(signup._pending_key(uid)):
            _send(bot, chat, busy)
            return "erase_busy"
        result = links.erase_user(uid)
        signup.drop(uid)
        cache.delete(f"tgplat:signup-submit:{uid}")
    # Ключи со случайной частью — лучшим усилием; гарантия — TTL ≤ 24 ч и отказ в правах
    # (связей уже нет).
    try:
        cachescan.delete_matching(f"tgplat:ref:{uid}:*")
        for schema in result["schemas"]:
            cachescan.delete_matching(f"tgpromo:draft:{schema}:{uid}:*")
            cachescan.delete_matching(f"tgpromo:mg*:{schema}:{uid}:*")
    except Exception:  # noqa: BLE001
        pass
    _send(
        bot,
        chat,
        _(
            "✅ Gelöscht. Telegram ist mit keinem Geschäft mehr verbunden. Ihre Geschäfte "
            "bleiben bestehen; neu verbinden geht im Kabinett."
        ),
    )
    return "erased"
