"""T-8.10h H-7i: права субъекта данных в общем боте (Art. 15, 16, 18, 20, 21 DSGVO).

План — docs/t8-10h-h7-owner-bot-ux-plan-2026-10-20.md §2. Удаление (Art. 17) — `privacy.py`.

- `/meine_daten` — сводка + `meine-daten.json` (Art. 15 доступ, Art. 20 переносимость).
  По данным бота платформа — Verantwortlicher; данные самого бизнеса — в кабинете.
- `/berichtigen` — язык бота; отвязать не тот бизнес (Art. 16). Данные бизнеса — `/kabinett`.
- `/einschraenken` · `/freigeben` — ограничение обработки (Art. 18): сообщения не
  обрабатываются, доставка через общий бот молчит; данные целы. Работают при ограничении
  только сами права и `/datenschutz` / `/daten_loeschen`.
- `/widerspruch` — возражение (Art. 21): ИИ-разбор фото, напоминания. Полный отказ —
  удаление.

Единственный писатель `OwnerBotPrefs` — этот модуль.
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from contextvars import ContextVar

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _

from . import links
from .models import OwnerBotPrefs

PREFIX = "pr:"
EXPORT_RE = re.compile(r"^/(?:meine_daten|my_data)(?:@\w+)?\s*$", re.IGNORECASE)
CORRECT_RE = re.compile(r"^/(?:berichtigen|correct)(?:@\w+)?\s*$", re.IGNORECASE)
RESTRICT_RE = re.compile(r"^/(?:einschraenken|restrict)(?:@\w+)?\s*$", re.IGNORECASE)
RELEASE_RE = re.compile(r"^/(?:freigeben|unrestrict)(?:@\w+)?\s*$", re.IGNORECASE)
OBJECT_RE = re.compile(r"^/(?:widerspruch|object)(?:@\w+)?\s*$", re.IGNORECASE)
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
CALLBACK_RE = re.compile(rf"^pr:(?:l:([a-z]{{2}})|u:({UUID})|U:({UUID})|o:(ai|rem))$")
EXPORT_LIMIT = 3  # выгрузок в сутки
OBJECTIONS = {"ai": "ai_objected_at", "rem": "reminders_objected_at"}

# Ответ на входящее сообщение/кнопку (обработчик уже пропустил его через ограничение
# Art. 18). Всё остальное — фон (Celery: итог регистрации, подтверждение почты, ✅) — при
# ограничении молчит: одна проверка в точке отправки закрывает весь класс.
_INBOUND: ContextVar[bool] = ContextVar("platform_bot_inbound", default=False)


@contextmanager
def inbound():
    token = _INBOUND.set(True)
    try:
        yield
    finally:
        _INBOUND.reset(token)


def may_send(chat) -> bool:
    """Можно ли писать в этот чат через общий бот (Art. 18)."""
    if _INBOUND.get():
        return True
    try:
        return not is_restricted(int(chat))
    except (TypeError, ValueError):
        return True


def _send(bot, chat, text, markup=None):
    from .handler import send

    return send(bot, chat, text, markup)


# --- чтение (для остальных модулей) ------------------------------------------------------


def prefs(uid) -> OwnerBotPrefs | None:
    if not uid:
        return None
    try:
        return OwnerBotPrefs.objects.filter(tg_user_id=int(uid)).first()
    except (TypeError, ValueError):
        return None


def is_restricted(uid) -> bool:
    row = prefs(uid)
    return bool(row and row.restricted_at)


def ai_objected(uid) -> bool:
    row = prefs(uid)
    return bool(row and row.ai_objected_at)


def reminders_objected(uid) -> bool:
    row = prefs(uid)
    return bool(row and row.reminders_objected_at)


def preferred_locale(uid) -> str:
    row = prefs(uid)
    return row.locale if row and row.locale in _languages() else ""


def _languages() -> list[str]:
    return list(getattr(settings, "CABINET_LANGUAGES", ()) or ["de"])


def _set(uid, **fields) -> OwnerBotPrefs:
    row, _created = OwnerBotPrefs.objects.update_or_create(tg_user_id=int(uid), defaults=fields)
    return row


def erase(uid) -> None:
    """Часть `/daten_loeschen`: настройки прав тоже персональные данные."""
    OwnerBotPrefs.objects.filter(tg_user_id=int(uid)).delete()


# --- Art. 15 / 20 -------------------------------------------------------------------------


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def export_data(uid) -> dict:
    from . import signup

    uid = int(uid)
    rows = links.OwnerTelegramLink.objects.filter(tg_user_id=uid).select_related("tenant")
    row = prefs(uid)
    return {
        "controller": _("SiteAdaptor (Plattform-Bot)"),
        "telegram_user_id": uid,
        "businesses": [
            {
                "name": link.tenant.name,
                "active": link.is_active,
                "via": link.via,
                "connected_at": _iso(link.created_at),
                "selected_at": _iso(link.selected_at),
                "blocked_at": _iso(link.blocked_at),
                # T-8.30f: за каким пользователем кабинета закреплена связь
                "cabinet_user_id": link.user_pk,
            }
            for link in rows.order_by("created_at")[:50]
        ],
        "waiting_for_email_confirmation": [t.name for t in links.pending_for(uid)[:20]],
        "registration_in_progress": signup.load(uid) is not None,
        "settings": {
            "language": row.locale if row else "",
            "restricted_at": _iso(row.restricted_at) if row else None,
            "ai_objected_at": _iso(row.ai_objected_at) if row else None,
            "reminders_objected_at": _iso(row.reminders_objected_at) if row else None,
        },
        "exported_at": timezone.now().isoformat(),
    }


def send_export(bot, uid, chat) -> str:
    from apps.core import ratelimit
    from apps.telegram import services

    if ratelimit.hit("tgplat-export", str(uid), limit=EXPORT_LIMIT, window=24 * 3600):
        _send(bot, chat, _("Zu viele Versuche. Bitte später erneut."))
        return "limited"
    data = export_data(uid)
    names = [b["name"] for b in data["businesses"] if b["active"]]
    lines = [
        "📄 " + _("Ihre Daten in diesem Bot"),
        _("Telegram-ID: %(id)s") % {"id": data["telegram_user_id"]},
        _("Verbundene Geschäfte: %(names)s") % {"names": ", ".join(names) or "—"},
        _(
            "Daten Ihres Geschäfts (Aktionen, Kunden, Bestellungen) stehen im Kabinett und "
            "lassen sich dort exportieren: /kabinett"
        ),
        _("Die Datei unten wird von Telegram gespeichert, solange Sie den Chat behalten."),
    ]
    _send(bot, chat, "\n".join(lines))
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    try:
        services.send_document(bot.token, chat, "meine-daten.json", payload)
    except Exception:  # noqa: BLE001 — в тексте исключения URL с токеном бота
        _send(bot, chat, _("Die Datei konnte nicht gesendet werden. Bitte später erneut."))
        return "export_failed"
    return "exported"


# --- Art. 16 ------------------------------------------------------------------------------


def correct_menu(bot, uid, chat) -> str:
    rows = [[{"text": code.upper(), "callback_data": f"{PREFIX}l:{code}"} for code in _languages()]]
    for link in links.active_links(uid)[:10]:
        rows.append(
            [
                {
                    "text": "✂️ " + _("Trennen: %(name)s") % {"name": link.tenant.name[:40]},
                    "callback_data": f"{PREFIX}u:{link.pk}",
                }
            ]
        )
    _send(
        bot,
        chat,
        "\n".join(
            [
                "✏️ " + _("Daten berichtigen"),
                _("Sprache des Bots wählen oder ein falsch verbundenes Geschäft trennen."),
                _("Name, Adresse, Telefon Ihres Geschäfts: /profil oder /kabinett."),
            ]
        ),
        {"inline_keyboard": rows},
    )
    return "correct_menu"


def _own_link(uid, pk: str):
    return links.active_links(uid).filter(pk=pk).first()


# --- Art. 18 / 21 -------------------------------------------------------------------------


def restrict(bot, uid, chat) -> str:
    _set(uid, restricted_at=timezone.now())
    _send(
        bot,
        chat,
        _(
            "⏸ Verarbeitung eingeschränkt: Ich verarbeite Ihre Nachrichten nicht mehr und sende "
            "nichts über diesen Bot. Ihre Daten bleiben gespeichert. Aufheben: /freigeben"
        ),
    )
    return "restricted"


def release(bot, uid, chat) -> str:
    _set(uid, restricted_at=None)
    _send(bot, chat, _("▶ Einschränkung aufgehoben — der Bot arbeitet wieder normal."))
    return "released"


def objection_menu(bot, uid, chat) -> str:
    row = prefs(uid)

    def label(on: bool, text: str) -> str:
        return ("✅ " if on else "⬜ ") + text

    rows = [
        [
            {
                "text": label(bool(row and row.ai_objected_at), _("Keine KI-Fotoanalyse")),
                "callback_data": f"{PREFIX}o:ai",
            }
        ],
        [
            {
                "text": label(bool(row and row.reminders_objected_at), _("Keine Erinnerungen")),
                "callback_data": f"{PREFIX}o:rem",
            }
        ],
    ]
    _send(
        bot,
        chat,
        "\n".join(
            [
                "✋ " + _("Widerspruch"),
                _("Tippen zum Ein- und Ausschalten. Ganz widersprechen = /daten_loeschen."),
            ]
        ),
        {"inline_keyboard": rows},
    )
    return "objection_menu"


# --- вход ----------------------------------------------------------------------------------


def on_message(bot, message: dict, text: str) -> str:
    """'' — не команда прав."""
    uid, chat = message["from_id"], message["chat_id"]
    if EXPORT_RE.match(text):
        return send_export(bot, uid, chat)
    if CORRECT_RE.match(text):
        return correct_menu(bot, uid, chat)
    if RESTRICT_RE.match(text):
        return restrict(bot, uid, chat)
    if RELEASE_RE.match(text):
        return release(bot, uid, chat)
    if OBJECT_RE.match(text):
        return objection_menu(bot, uid, chat)
    return ""


def on_callback(bot, callback: dict) -> str:
    from django.utils import translation

    from apps.telegram import services

    uid, chat = callback.get("from_id"), callback.get("chat_id")
    services.answer_callback_query(bot.token, callback.get("id") or "")
    if not uid or chat != uid:
        return "skip"
    match = CALLBACK_RE.match(str(callback.get("data") or ""))
    if not match:
        return "skip"
    lang, ask_pk, do_pk, objection = match.groups()
    if lang:
        if lang not in _languages():
            return "skip"
        _set(uid, locale=lang)
        with translation.override(lang):
            _send(bot, chat, _("✅ Sprache gespeichert."))
        return "locale_set"
    if ask_pk or do_pk:
        link = _own_link(uid, ask_pk or do_pk)
        if link is None:
            _send(bot, chat, _("Nicht verfügbar."))
            return "denied"
        if ask_pk:
            _send(
                bot,
                chat,
                _("„%(name)s“ von diesem Telegram trennen? Das Geschäft selbst bleibt bestehen.")
                % {"name": link.tenant.name},
                {
                    "inline_keyboard": [
                        [
                            {
                                "text": "✂️ " + _("Ja, trennen"),
                                "callback_data": f"{PREFIX}U:{link.pk}",
                            },
                        ]
                    ]
                },
            )
            return "unlink_asked"
        links.unbind(link.tenant)
        _send(bot, chat, _("✅ Getrennt: %(name)s") % {"name": link.tenant.name})
        return "unlinked"
    field = OBJECTIONS[objection]
    row = prefs(uid)
    now_on = not bool(row and getattr(row, field))
    _set(uid, **{field: timezone.now() if now_on else None})
    return objection_menu(bot, uid, chat)
