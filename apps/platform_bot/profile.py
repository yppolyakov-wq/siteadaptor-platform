"""T-8.10h H-7f: «/profil» — данные бизнеса в чате общего бота.

План — docs/t8-10h-h7-owner-bot-ux-plan-2026-10-20.md §2 (решение владельца 2: в чате правим
только телефон, WhatsApp и согласие на каталог города; остальное — веб-кабинет).

- Бизнес — ТЕКУЩАЯ связь в момент действия; права перепроверяются при каждом сохранении.
- Значения проверяет та же модельная валидация, что форма кабинета (`modelform_factory`
  по тем же полям `Tenant`).
- Ожидание ввода — в кэше 10 минут (`tgplat:profile:<uid>`), «-» очищает поле.
- Каталог города: включить/выключить — вторым шагом, затем `apply_visibility`
  (как при сохранении «Mein Geschäft»).
"""

from __future__ import annotations

import re

from django.core.cache import cache
from django.utils.translation import gettext as _

from . import links

PREFIX = "pp:"
COMMAND_RE = re.compile(r"^/(?:profil|profile)(?:@\w+)?\s*$", re.IGNORECASE)
CALLBACK_RE = re.compile(r"^pp:(v|p|w|c|C:(\d{1,12}):([01]))$")
EDIT_TTL = 10 * 60
FIELDS = {"p": "contact_phone", "w": "whatsapp_number"}
SAVE_LIMIT = 10  # сохранений в час


def _send(bot, chat, text, markup=None):
    from .handler import send

    return send(bot, chat, text, markup)


def _key(uid) -> str:
    return f"tgplat:profile:{int(uid)}"


def _current(uid):
    link = links.active_links(uid).first()
    if link is None or not links.still_owner(link.tenant):
        return None
    return link.tenant


def _label(field: str) -> str:
    return {"contact_phone": _("Telefon"), "whatsapp_number": _("WhatsApp-Nummer")}[field]


def show(bot, uid, chat) -> str:
    tenant = _current(uid)
    if tenant is None:
        from .handler import _private_onboarding

        return _private_onboarding(bot, chat)
    dash = "—"
    catalog = _("an") if tenant.in_city_catalog else _("aus")
    lines = [
        "🏪 " + tenant.name,
        "📍 " + (", ".join(p for p in (tenant.address or "", tenant.city or "") if p) or dash),
        "📞 " + _("Telefon: %(v)s") % {"v": tenant.contact_phone or dash},
        "💬 " + _("WhatsApp: %(v)s") % {"v": tenant.whatsapp_number or dash},
        "🏙 " + _("Im Stadtkatalog: %(v)s") % {"v": catalog},
        _("Name, Adresse, Öffnungszeiten, E-Mail: im Kabinett unter „Einstellungen“."),
    ]
    rows = [
        [
            {"text": "📞 " + _("Telefon ändern"), "callback_data": PREFIX + "p"},
            {"text": "💬 " + _("WhatsApp ändern"), "callback_data": PREFIX + "w"},
        ],
        [{"text": "✉️ " + _("Einstellungen im Kabinett"), "callback_data": "pm:l:e"}],
    ]
    _send(bot, chat, "\n".join(lines), {"inline_keyboard": rows})
    return "profile"


def ask_value(bot, uid, chat, code: str) -> str:
    tenant = _current(uid)
    if tenant is None:
        _send(bot, chat, _("Nicht verfügbar."))
        return "denied"
    field = FIELDS[code]
    cache.set(_key(uid), {"field": field, "tenant": tenant.pk}, EDIT_TTL)
    _send(
        bot,
        chat,
        _("Neue %(label)s senden (z. B. +49 212 123456). „-“ löscht sie. /abbrechen bricht ab.")
        % {"label": _label(field)},
    )
    return "profile_wait"


def pending(uid) -> bool:
    return cache.get(_key(uid)) is not None


def cancel(uid) -> None:
    cache.delete(_key(uid))


def on_message(bot, message: dict, text: str) -> str:
    """Ввод значения после «📞/💬 ändern» ('' — ничего не ждём)."""
    from django import forms

    from apps.core import ratelimit
    from apps.tenants.models import Tenant

    uid, chat = message["from_id"], message["chat_id"]
    state = cache.get(_key(uid))
    if not state:
        return ""
    if text.startswith("/"):
        cancel(uid)
        return ""  # команда — не значение; дальше обычная маршрутизация
    if not text.strip():
        # Фото/стикер — не значение; стирать номер можно только явным «-».
        _send(bot, chat, _("Bitte die Nummer als Text senden — oder „-“ zum Löschen."))
        return "profile_wait"
    tenant = _current(uid)
    if tenant is None or tenant.pk != state.get("tenant"):
        cancel(uid)
        _send(bot, chat, _("Nicht verfügbar."))
        return "denied"
    if ratelimit.hit("tgplat-profile", str(uid), limit=SAVE_LIMIT, window=3600):
        _send(bot, chat, _("Zu viele Versuche. Bitte später erneut."))
        return "limited"
    field = state["field"]
    value = "" if text.strip() == "-" else text.strip()
    form_class = forms.modelform_factory(Tenant, fields=[field])
    form = form_class(data={field: value}, instance=tenant)
    if not form.is_valid():
        errors = "; ".join(str(e) for e in form.errors.get(field, [])) or _("Ungültig.")
        _send(bot, chat, _("Nicht gespeichert: %(errors)s") % {"errors": errors})
        return "profile_invalid"
    form.save(commit=False)
    tenant.save(update_fields=[field])
    cancel(uid)
    _send(bot, chat, _("✅ Gespeichert."))
    return show(bot, uid, chat)


def on_callback(bot, callback: dict) -> str:
    from apps.telegram import services

    uid, chat = callback.get("from_id"), callback.get("chat_id")
    services.answer_callback_query(bot.token, callback.get("id") or "")
    if not uid or chat != uid:
        return "skip"
    match = CALLBACK_RE.match(str(callback.get("data") or ""))
    if not match:
        return "skip"
    code, target_pk, target_value = match.groups()
    if code == "v":
        return show(bot, uid, chat)
    if code in FIELDS:
        return ask_value(bot, uid, chat, code)
    tenant = _current(uid)
    if tenant is None:
        _send(bot, chat, _("Nicht verfügbar."))
        return "denied"
    # KA-D5 (решение владельца 2026-10-23): каталог города — всегда. Старые кнопки
    # переключателя («pp:c», «pp:C:…») ничего не меняют, только объясняют.
    from django.conf import settings

    _send(
        bot,
        chat,
        _(
            "Alle Geschäfte erscheinen im Stadtkatalog. Wenn Sie nicht dort stehen "
            "möchten, schreiben Sie uns bitte: %(mail)s"
        )
        % {"mail": settings.PLATFORM_CONTACT_EMAIL},
    )
    return "catalog_info"
