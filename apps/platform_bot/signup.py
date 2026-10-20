"""T-8.10h H-5: регистрация нового бизнеса прямо в общем боте (без шага на сайте).

План — docs/t8-10h-platform-bot-plan-2026-10-19.md §8. Пошаговый диалог; состояние —
в кэше ЗАШИФРОВАННЫМ (персональные данные, TTL 2 ч), ключ — id пользователя Telegram.
На каждом шаге поля проверяет та же ``QuickStartForm``, что веб «Aktion in 3 Klicks»;
финальный ✅ — полная проверка той же формой и тот же провижининг
(``start_quick_provisioning`` → ``provision_quick``). Когда схема и акция готовы,
задача провижининга вызывает ``finish``: чат привязывается владельцем (via=signup),
владельцу уходит ссылка на акцию; вход в кабинет — только ссылкой из письма.
В логи — только имена шагов и коды, без ввода пользователя.
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager

from django.core.cache import cache
from django.db import IntegrityError
from django.utils import translation
from django.utils.translation import gettext as _

from . import links

logger = logging.getLogger(__name__)

PREFIX = "ps:"
STATE_TTL = 2 * 3600
PENDING_TTL = 30 * 60
MIN_SECONDS = 20  # аналог too_fast веба: живой человек не проходит 9 шагов за секунды
STEPS = ("promo", "type", "name", "city", "district", "street", "postcode", "phone", "email")
STEP_FIELDS = {
    "promo": (
        "title",
        "description",
        "new_price",
        "old_price",
        "percent",
        "quantity",
        "term",
        "until",
        "until_time",
        "__all__",
    ),
    "type": ("business_type",),
    "name": ("business_name",),
    "city": ("city",),
    "district": ("district",),
    "street": ("street",),
    "postcode": ("postcode",),
    "phone": ("phone",),
    "email": ("email",),
}
LIMIT_START = 10  # начал регистрацию — в час на пользователя
LIMIT_STEP = 120  # ответов на шаги — в час
LIMIT_SIGNUP = 3  # готовых регистраций — в сутки на пользователя (свой номер подтверждён)
LIMIT_SIGNUP_UNVERIFIED = 1  # без «Meine Nummer senden» — строже (одноразовые аккаунты)
LIMIT_MAIL = 3  # на один e-mail в сутки (не заваливать чужой ящик письмами)
LIMIT_GLOBAL = 30  # всего регистраций через бот — в час (подтверждённые номером)
LIMIT_GLOBAL_UNVERIFIED = 10  # без подтверждённого номера — отдельная, меньшая корзина
LIMIT_LOGIN_MAIL = 3  # писем-входа на один адрес в час
LIMIT_CONFIRM_RESEND = 3  # повторных писем подтверждения из бота — в час на пользователя
MAX_BOT_BUSINESSES = 5  # бизнесов на один чат (подключённые + ждущие почты): иначе обход Р-5


# --- состояние --------------------------------------------------------------------------


def _key(uid) -> str:
    return f"tgplat:signup:{int(uid)}"


def _pending_key(uid) -> str:
    return f"tgplat:signup-pending:{int(uid)}"


def load(uid) -> dict | None:
    from apps.secrets import crypto

    raw = cache.get(_key(uid))
    if not raw:
        return None
    try:
        state = json.loads(crypto.decrypt(raw) or "null")
    except (ValueError, TypeError):
        return None
    return state if isinstance(state, dict) and state.get("v") == 1 else None


def save(uid, state: dict) -> None:
    from apps.secrets import crypto

    cache.set(_key(uid), crypto.encrypt(json.dumps(state)), STATE_TTL)


def drop(uid) -> None:
    cache.delete(_key(uid))


@contextmanager
def _lock(uid):
    """Альбом приходит N апдейтами параллельно: правка состояния — под коротким замком."""
    key = f"tgplat:signup-lock:{int(uid)}"
    got = False
    for _attempt in range(50):
        if cache.add(key, 1, 60):
            got = True
            break
        time.sleep(0.1)
    try:
        yield got
    finally:
        if got:
            cache.delete(key)


# --- отправка ---------------------------------------------------------------------------


def _send(bot, chat, text, markup=None):
    from .handler import send

    return send(bot, chat, text, markup)


def _rate(scope: str, ident, limit: int, window: int) -> bool:
    from apps.core import ratelimit

    return ratelimit.hit(scope, str(ident), limit=limit, window=window)


# --- вход в диалог ----------------------------------------------------------------------


def start(bot, uid, chat, lang: str) -> str:
    # H-5b (решение владельца): второй и следующие бизнесы — тоже прямо в чате.
    if links.active_links(uid).count() + links.pending_for(uid).count() >= MAX_BOT_BUSINESSES:
        _send(
            bot,
            chat,
            _("Ein weiteres Geschäft legen Sie auf der Website an: %(url)s") % {"url": _web_url()},
        )
        return "has_business"
    if cache.get(_pending_key(uid)):
        _send(bot, chat, _("Ihr Geschäft wird gerade angelegt — einen Moment bitte."))
        return "pending"
    state = load(uid)
    if state is not None:
        return resume(bot, uid, chat, state)
    if _rate("tgplat-signup-start", uid, LIMIT_START, 3600):
        _send(bot, chat, _("Zu viele Versuche. Bitte später erneut."))
        return "limited"
    state = {
        "v": 1,
        "uid": int(uid),
        "step": "promo",
        "lang": lang,
        "started": time.time(),
        "data": {},
    }
    current = links.active_links(uid).first()
    if current is not None:
        _send(
            bot,
            chat,
            _("Neues Geschäft — Ihr bisheriges (%(name)s) bleibt bestehen.")
            % {"name": current.tenant.name},
        )
    save(uid, state)
    _send(
        bot,
        chat,
        _(
            "Los geht's! Ihre Angaben speichern wir nur, bis Sie veröffentlichen (höchstens "
            "2 Stunden). Datenschutz: %(url)s"
        )
        % {"url": _privacy_url()},
    )
    _prompt(bot, chat, state)
    return "started"


def resume(bot, uid, chat, state) -> str:
    _send(bot, chat, _("Weiter, wo Sie aufgehört haben. Abbrechen: /abbrechen"))
    _prompt(bot, chat, state)
    return "resumed"


def cancel(bot, uid, chat) -> str:
    drop(uid)
    _send(bot, chat, _("Abgebrochen. Neu starten: /neu"))
    return "cancelled"


def _web_url() -> str:
    from .handler import _start_url

    return _start_url()


def _privacy_url() -> str:
    from apps.tenants.quickstart import domain_base

    return f"https://{domain_base()}/datenschutz/"


# --- шаги -------------------------------------------------------------------------------


def _next_step(state: dict, after: str) -> str:
    from apps.core import districts

    index = STEPS.index(after) + 1
    while index < len(STEPS):
        step = STEPS[index]
        if step == "district" and not districts.choices_for(state["data"].get("city", "")):
            state["data"]["district"] = ""
            index += 1
            continue
        return step
    return "summary"


def _advance(bot, chat, uid, state, step) -> str:
    following = _next_step(state, step)
    if state.get("editing") and not (step == "city" and following == "district"):
        state.pop("editing", None)
        following = "summary"
    state["step"] = following
    save(uid, state)
    _prompt(bot, chat, state)
    return state["step"]


def _as_post(data: dict) -> dict:
    """Состояние → данные формы. Незаполненные шаги — пустые (их ошибки не смотрим)."""
    from apps.core import city_categories as cc

    post = {
        "term": "week",
        "customer_response": "reserve",
        "in_city_catalog": "on",
        "city_category": cc.suggest_for_business_type(data.get("business_type", "")),
    }
    for key, value in data.items():
        if key in ("photo_ids", "warnings", "phone_verified"):
            continue
        if key == "in_city_catalog":
            if value:
                post[key] = "on"
            else:
                post.pop(key, None)
            continue
        post[key] = value
    return post


def _form(data: dict):
    from apps.tenants.quickstart import QuickStartForm

    return QuickStartForm(data=_as_post(data))


def _step_errors(data: dict, step: str) -> list[str]:
    form = _form(data)
    form.is_valid()
    out = []
    for field in STEP_FIELDS.get(step, ()):
        out.extend(str(e) for e in form.errors.get(field, ()))
    return out


def on_message(bot, message: dict, state: dict) -> str:
    uid, chat = message["from_id"], message["chat_id"]
    if _rate("tgplat-signup-step", uid, LIMIT_STEP, 3600):
        return "limited"
    text = (message.get("text") or "").strip()
    with _lock(uid) as got:
        if not got:
            return "busy"
        state = load(uid) or state
        step = state.get("step")
        data = state["data"]
        if step == "promo":
            return _promo_step(bot, chat, uid, state, message, text)
        photo = message.get("photo") or ""
        if photo and not text:
            # Остальные фото альбома пришли после шага акции — дописать молча.
            from apps.promotions import quick

            ids = data.setdefault("photo_ids", [])
            if photo not in ids and len(ids) < quick.MAX_PHOTOS:
                ids.append(photo)
            save(uid, state)
            return "photo_added"
        if step == "phone" and message.get("contact_phone"):
            if message.get("contact_user_id") != uid:
                _send(bot, chat, _("Bitte Ihre eigene Nummer teilen oder eintippen."))
                return "phone"
            text = message["contact_phone"]
        if step in ("name", "city", "street", "postcode", "phone", "email") and text:
            field = {
                "name": "business_name",
                "city": "city",
                "street": "street",
                "postcode": "postcode",
                "phone": "phone",
                "email": "email",
            }[step]
            trial = {**data, field: text[:200]}
            if step == "city":
                trial["district"] = ""
            errors = _step_errors(trial, step)
            if errors:  # прежнее (верное) значение не теряем
                _send(bot, chat, "⚠️ " + errors[0])
                _prompt(bot, chat, state)
                return step
            data.update(trial)
            if step == "phone":
                data["phone_verified"] = bool(message.get("contact_phone"))
            return _advance(bot, chat, uid, state, step)
        _prompt(bot, chat, state)
        return step or "promo"


def _promo_step(bot, chat, uid, state, message, text) -> str:
    from apps.promotions import message_parse, quick
    from apps.promotions.telegram_promo import _warning

    data = state["data"]
    photo = message.get("photo") or ""
    if photo:
        ids = data.setdefault("photo_ids", [])
        if photo not in ids and len(ids) < quick.MAX_PHOTOS:
            ids.append(photo)
    if not text:
        save(uid, state)
        if photo and not data.get("title"):
            return "promo_photo"  # подпись придёт с другим фото альбома или отдельно
        _prompt(bot, chat, state)
        return "promo"
    if text.startswith("/"):
        save(uid, state)
        _prompt(bot, chat, state)  # незнакомая команда — не текст акции
        return "promo"
    parsed = message_parse.parse(text)
    if not parsed.title:
        save(uid, state)
        _send(bot, chat, _("Wie heißt das Angebot? Schreiben Sie es bitte dazu."))
        return "promo"
    data.update(
        title=parsed.title,
        description=parsed.description,
        new_price="" if parsed.new_price is None else str(parsed.new_price),
        old_price="" if parsed.old_price is None else str(parsed.old_price),
        percent="" if parsed.percent is None else str(parsed.percent),
        quantity="" if parsed.quantity is None else str(parsed.quantity),
        term=parsed.term or "week",
        until=parsed.until.isoformat() if parsed.until else "",
        until_time=parsed.until_time.strftime("%H:%M") if parsed.until_time else "",
        until_time_for=quick.until_time_key(parsed.term, parsed.until) if parsed.until_time else "",
        warnings=list(parsed.warnings),
    )
    errors = _step_errors(data, "promo")
    if errors:
        save(uid, state)
        _send(bot, chat, "⚠️ " + errors[0])
        return "promo"
    for code in data["warnings"][:3]:
        note = _warning(code)
        if note:
            _send(bot, chat, "⚠️ " + note)
    return _advance(bot, chat, uid, state, "promo")


def _prompt(bot, chat, state) -> None:
    from apps.core import districts
    from apps.tenants.models import Tenant
    from apps.tenants.quickstart import QUICK_TYPES, known_cities

    step = state.get("step")
    data = state["data"]
    if step == "promo":
        _send(
            bot,
            chat,
            _(
                "1/8 · Ihre erste Aktion: z. B. „Brötchen 2,50 € statt 3,90 €, heute bis 18 Uhr, "
                "20 Stück“ — gern mit Foto."
            ),
        )
    elif step == "type":
        labels = dict(Tenant.BUSINESS_TYPES)
        rows = [
            [{"text": str(labels[v]), "callback_data": f"ps:t:{v}"}]
            for v in QUICK_TYPES
            if v in labels
        ]
        _send(bot, chat, _("2/8 · Was für ein Geschäft haben Sie?"), {"inline_keyboard": rows})
    elif step == "name":
        _send(bot, chat, _("3/8 · Wie heißt Ihr Geschäft?"))
    elif step == "city":
        cities = known_cities()[:6]
        state["cities"] = cities  # кнопка несёт индекс в ЭТОТ список (не меняется после показа)
        if state.get("uid"):
            save(state["uid"], state)
        markup = (
            {
                "inline_keyboard": [
                    [{"text": c, "callback_data": f"ps:c:{i}"}] for i, c in enumerate(cities)
                ]
            }
            if cities
            else None
        )
        _send(bot, chat, _("4/8 · In welcher Stadt? (oder eintippen)"), markup)
    elif step == "district":
        options = districts.choices_for(data.get("city", ""))[:12]
        rows = [[{"text": name, "callback_data": f"ps:d:{slug}"}] for slug, name in options]
        rows.append([{"text": _("Kein Stadtteil"), "callback_data": "ps:d:-"}])
        _send(bot, chat, _("4/8 · Welcher Stadtteil?"), {"inline_keyboard": rows})
    elif step == "street":
        _send(bot, chat, _("5/8 · Straße und Hausnummer?"))
    elif step == "postcode":
        _send(bot, chat, _("6/8 · Postleitzahl?"))
    elif step == "phone":
        _send(
            bot,
            chat,
            _("7/8 · Telefon für Ihre Kundschaft? (eintippen oder Knopf unten)"),
            {
                "keyboard": [[{"text": "📞 " + _("Meine Nummer senden"), "request_contact": True}]],
                "resize_keyboard": True,
                "one_time_keyboard": True,
            },
        )
    elif step == "email":
        _send(
            bot,
            chat,
            _("8/8 · Ihre E-Mail? Dorthin kommt der Bestätigungs- und Anmeldelink."),
            {"remove_keyboard": True},
        )
    else:
        _summary(bot, chat, state)


def _summary(bot, chat, state) -> None:
    from apps.promotions import response as promo_response
    from apps.tenants.models import Tenant

    data = state["data"]
    types = dict(Tenant.BUSINESS_TYPES)
    responses = dict(promo_response.CHOICES)
    catalog = data.get("in_city_catalog", True)
    lines = [
        "📋 " + _("Bitte prüfen:"),
        "📣 " + (data.get("title") or "—"),
        "🏪 "
        + (data.get("business_name") or "—")
        + " · "
        + str(types.get(data.get("business_type"), "—")),
        "📍 "
        + ", ".join(
            x
            for x in (
                data.get("street"),
                f"{data.get('postcode', '')} {data.get('city', '')}".strip(),
            )
            if x
        ),
        "📞 " + (data.get("phone") or "—"),
        "✉️ " + (data.get("email") or "—"),
        "🙋 " + str(responses.get(data.get("customer_response") or "reserve", "")),
        ("✅ " if catalog else "⬜ ") + _("Auch im Stadtportal zeigen"),
    ]
    if data.get("photo_ids"):
        lines.append(f"📷 {len(data['photo_ids'])}")
    rows = [
        [{"text": "✅ " + _("Veröffentlichen"), "callback_data": "ps:ok"}],
        [
            {"text": "✏️ " + _("Ändern"), "callback_data": "ps:e"},
            {"text": "🙋 " + _("Reaktion"), "callback_data": "ps:r"},
        ],
        [{"text": ("✅ " if catalog else "⬜ ") + _("Stadtportal"), "callback_data": "ps:p"}],
        [{"text": "❌ " + _("Abbrechen"), "callback_data": "ps:x"}],
    ]
    _send(bot, chat, "\n".join(lines), {"inline_keyboard": rows})


# --- кнопки -----------------------------------------------------------------------------

EDITABLE = (
    ("promo", "📣"),
    ("type", "🏪"),
    ("name", "🔤"),
    ("city", "📍"),
    ("street", "🏠"),
    ("postcode", "#️⃣"),
    ("phone", "📞"),
    ("email", "✉️"),
)


def on_callback(bot, callback: dict) -> str:
    from apps.telegram import services

    uid, chat = callback.get("from_id"), callback.get("chat_id")
    services.answer_callback_query(bot.token, callback.get("id") or "")
    if not uid or chat != uid:
        return "skip"
    data = str(callback.get("data") or "")[len(PREFIX) :]
    if data == "go":
        return start(bot, uid, chat, callback.get("language_code") or "")
    if data.startswith("l:"):
        return send_login_link(bot, uid, chat, data[2:])
    if data.startswith("m:"):
        return resend_confirmation(bot, uid, chat, data[2:])
    with _lock(uid) as got:
        if not got:
            return "busy"
        state = load(uid)
        if state is None:
            _send(bot, chat, _("Abgelaufen. Neu starten: /neu"))
            return "expired"
        return _on_state_callback(bot, uid, chat, state, data)


def _on_state_callback(bot, uid, chat, state, data) -> str:
    from apps.core import districts
    from apps.promotions import response as promo_response
    from apps.tenants.quickstart import QUICK_RESPONSES, QUICK_TYPES

    fields = state["data"]
    if data == "x":
        return cancel(bot, uid, chat)
    if data == "ok":
        if state.get("step") != "summary":
            _prompt(bot, chat, state)
            return state.get("step") or "promo"
        return submit(bot, uid, chat, state)
    if data == "e":
        # Подписи — метки полей той же формы (уже переведены), не внутренние имена шагов.
        form = _form(fields)
        names = {
            "promo": "title",
            "type": "business_type",
            "name": "business_name",
            "city": "city",
            "street": "street",
            "postcode": "postcode",
            "phone": "phone",
            "email": "email",
        }
        rows = [
            [{"text": f"{icon} {form.fields[names[step]].label}", "callback_data": f"ps:e:{step}"}]
            for step, icon in EDITABLE
        ]
        _send(bot, chat, _("Was möchten Sie ändern?"), {"inline_keyboard": rows})
        return "edit_menu"
    if data.startswith("e:") and data[2:] in dict(EDITABLE):
        state["step"], state["editing"] = data[2:], True
        save(uid, state)
        _prompt(bot, chat, state)
        return state["step"]
    if data == "p":
        fields["in_city_catalog"] = not fields.get("in_city_catalog", True)
        save(uid, state)
        _summary(bot, chat, state)
        return "summary"
    if data == "r":
        labels = dict(promo_response.CHOICES)
        rows = [[{"text": str(labels[k]), "callback_data": f"ps:r:{k}"}] for k in QUICK_RESPONSES]
        _send(bot, chat, _("Was tun Kund:innen?"), {"inline_keyboard": rows})
        return "response_menu"
    if data.startswith("r:") and data[2:] in QUICK_RESPONSES:
        fields["customer_response"] = data[2:]
        save(uid, state)
        _summary(bot, chat, state)
        return "summary"
    if data.startswith("t:") and state.get("step") == "type" and data[2:] in QUICK_TYPES:
        fields["business_type"] = data[2:]
        return _advance(bot, chat, uid, state, "type")
    if data.startswith("c:") and state.get("step") == "city" and data[2:].isdigit():
        cities = list(state.get("cities") or [])
        index = int(data[2:])
        if index < len(cities):
            fields["city"], fields["district"] = cities[index], ""
            return _advance(bot, chat, uid, state, "city")
    if data.startswith("d:") and state.get("step") == "district":
        slug = data[2:]
        allowed = {s for s, _n in districts.choices_for(fields.get("city", ""))}
        if slug == "-" or slug in allowed:
            fields["district"] = "" if slug == "-" else slug
            return _advance(bot, chat, uid, state, "district")
    _prompt(bot, chat, state)
    return "skip"


# --- отправка формы ---------------------------------------------------------------------


def submit(bot, uid, chat, state) -> str:
    import hashlib

    from apps.promotions import quick, telegram_promo

    data = state["data"]
    if time.time() - float(state.get("started") or 0) < MIN_SECONDS:
        _send(bot, chat, _("Bitte prüfen Sie Ihre Angaben und senden Sie erneut."))
        return "too_fast"
    form = _form(data)
    if not form.is_valid():
        for step in STEPS:
            errors = [str(e) for f in STEP_FIELDS[step] for e in form.errors.get(f, ())]
            if errors:
                state["step"], state["editing"] = step, True
                save(uid, state)
                _send(bot, chat, "⚠️ " + errors[0])
                _prompt(bot, chat, state)
                return f"invalid_{step}"
        _send(bot, chat, _("Bitte prüfen Sie Ihre Angaben und senden Sie erneut."))
        return "invalid"
    if links.active_links(uid).count() + links.pending_for(uid).count() >= MAX_BOT_BUSINESSES:
        _send(
            bot,
            chat,
            _("Ein weiteres Geschäft legen Sie auf der Website an: %(url)s") % {"url": _web_url()},
        )
        return "has_business"
    guard = f"tgplat:signup-submit:{int(uid)}"
    if cache.get(guard):
        _send(bot, chat, _("Ihr Geschäft wird gerade angelegt — einen Moment bitte."))
        return "busy"  # двойной ✅ во время отправки
    cd = form.cleaned_data
    mail_key = hashlib.sha256(cd["email"].encode()).hexdigest()
    # Свой номер, подтверждённый кнопкой Telegram, — порог выше; без него (одноразовые
    # аккаунты) — строже и в отдельной общей корзине, чтобы не блокировать остальных.
    # Владелец уже подтверждённого (почтой) бизнеса — проверенный пользователь.
    verified = (
        bool(data.get("phone_verified"))
        or links.active_links(uid).filter(via=links.OwnerTelegramLink.VIA_SIGNUP).exists()
    )
    per_user = LIMIT_SIGNUP if verified else LIMIT_SIGNUP_UNVERIFIED
    global_scope = "tgplat-signup-global" if verified else "tgplat-signup-global-unverified"
    global_limit = LIMIT_GLOBAL if verified else LIMIT_GLOBAL_UNVERIFIED
    if _rate("tgplat-signup", uid, per_user, 86400) or _rate(
        "tgplat-signup-mail", mail_key, LIMIT_MAIL, 86400
    ):
        _send(bot, chat, _("Zu viele Versuche. Bitte später erneut."))
        return "limited"
    if _rate(global_scope, "all", global_limit, 3600):
        logger.warning("platform bot signup global cap reached (verified=%s)", verified)
        _send(bot, chat, _("Zu viele Versuche. Bitte später erneut."))
        return "limited"
    if not cache.add(guard, 1, 300):
        return "busy"
    promo = form.promo_payload()
    if data.get("photo_ids"):
        uploads, failed = telegram_promo.photos_from_telegram(bot.token, data["photo_ids"])
        if uploads:
            try:
                promo["images"] = quick.save_photos(uploads)
            except Exception:  # noqa: BLE001 — акция без фото лучше, чем никакой
                failed = True
        if failed:
            _send(bot, chat, _("Foto konnte nicht übernommen werden."))
    # Метка «создаётся» — ДО запуска: быстрый воркер может закончить (finish снимает
    # метку) раньше, чем мы вернёмся сюда; иначе метка висела бы после готового бизнеса.
    cache.set(_pending_key(uid), 1, PENDING_TTL)
    drop(uid)
    tenant = None
    try:
        tenant = _provision(bot, chat, form, cd, promo, state, uid)
    except Exception as exc:  # noqa: BLE001 — ввод не теряем, «создаётся» не вешаем
        logger.warning("platform bot signup provisioning failed: %s", type(exc).__name__)
        tenant = None
    if tenant is None:
        cache.delete(_pending_key(uid))
        save(uid, state)  # ввод не теряем — можно нажать ✅ ещё раз позже
        cache.delete(guard)
        _send(bot, chat, _("Das hat nicht geklappt — bitte später erneut versuchen."))
        return "failed"
    # Повторный ✅ уже ловит снятое состояние («abgelaufen»); защиту снимаем сразу, иначе
    # следующий бизнес этого чата 5 минут молча не создавался бы.
    cache.delete(guard)
    if cache.get(_pending_key(uid)):  # задача ещё идёт — итог придёт отдельным сообщением
        _send(bot, chat, "⏳ " + _("Ihr Geschäft wird angelegt — gleich kommt der Link."))
    logger.info("platform bot signup submitted")
    return "submitted"


def _provision(bot, chat, form, cd, promo, state, uid):
    from apps.tenants import quickstart
    from apps.tenants.services import start_quick_provisioning

    tenant = None
    slug = quickstart.suggest_slug(cd["business_name"])
    for _attempt in range(3):
        try:
            tenant = start_quick_provisioning(
                business_name=cd["business_name"].strip(),
                slug=slug,
                business_type=cd["business_type"],
                city=cd["city"],
                district=cd.get("district") or "",
                email=cd["email"],
                address=form.address_line(),
                phone=cd["phone"],
                promo=promo,
                in_city_catalog=cd.get("in_city_catalog", False),
                telegram={"tg_user_id": int(uid), "lang": state.get("lang") or ""},
            )
            break
        except IntegrityError:
            slug = quickstart.suggest_slug(f"{cd['business_name']} {cd['city']}")
            if _attempt:
                slug = quickstart.suggest_slug(f"{cd['business_name']} {int(time.time()) % 10000}")
    return tenant


# --- после провижининга (вызывает задача provision_quick) ---------------------------------


def _mask(email: str) -> str:
    name, _sep, domain = (email or "").partition("@")
    return f"{name[:1]}***@{domain}" if domain else "***"


def finish(tenant_id, telegram: dict, promo_pk, ok: bool) -> str:
    """Схема готова (или нет): сообщить итог — один раз. Чат станет владельцем только после
    подтверждения почты (H-5b, решение владельца: иначе чужой адрес = чужой бизнес)."""
    from apps.telegram import bots
    from apps.tenants.models import Tenant

    uid = int(telegram.get("tg_user_id") or 0)
    if uid:
        cache.delete(_pending_key(uid))  # и без бота: иначе «создаётся» висело бы 30 мин
    bot = bots.platform_bot()
    if not uid or bot is None:
        return "off"
    lang = telegram.get("lang") or ""
    from .handler import locale_for

    with translation.override(locale_for(lang)):
        tenant = Tenant.objects.filter(pk=tenant_id).first()
        if not ok or tenant is None or tenant.provisioning_status != Tenant.PROVISIONING_READY:
            _send(
                bot,
                uid,
                _("Das Anlegen hat nicht geklappt. Bitte /neu oder die Website: %(url)s")
                % {"url": _web_url()},
            )
            return "failed"
        if not tenant.email_pending:
            # Почту подтвердили раньше, чем задача дошла сюда, — привязать сразу и всё же
            # прислать ссылку на акцию.
            result, bound_uid, bound_lang = links.complete_pending(tenant)
            url = _promo_url(tenant, promo_pk) if promo_pk else ""
            if url:
                _send(bot, uid, _("Ihre Aktion: %(url)s") % {"url": url})
            if result in ("bound", "taken"):
                bound_message(tenant, bound_uid or uid, result, bound_lang or lang)
            return result
        if not cache.add(f"tgplat:signup-done:{tenant.pk}", 1, 7 * 86400):
            return "already"
        lines = ["🎉 " + _("Fertig! Ihr Geschäft ist angelegt.")]
        rows = []
        if promo_pk:
            url = _promo_url(tenant, promo_pk)
            if url:
                lines.append(_("Ihre Aktion: %(url)s") % {"url": url})
                rows.append([{"text": "👀 " + _("Live ansehen"), "url": url}])
        else:
            lines.append(_("Die Aktion bitte nach der Bestätigung noch einmal senden."))
        lines.append(
            _(
                "Bitte bestätigen Sie Ihre E-Mail (%(mail)s) — danach ist dieser Chat mit Ihrem "
                "Geschäft verbunden und Sie erscheinen im Stadtportal."
            )
            % {"mail": _mask(_owner_email(tenant))}
        )
        rows.append(
            [{"text": "✉️ " + _("E-Mail erneut senden"), "callback_data": f"ps:m:{tenant.pk}"}]
        )
        if not _send(bot, uid, "\n".join(lines), {"inline_keyboard": rows}):
            cache.delete(f"tgplat:signup-done:{tenant.pk}")  # повтор задачи пришлёт снова
    return "awaiting_email"


def _owner_email(tenant) -> str:
    from django_tenants.utils import schema_context

    from apps.core.models import Membership

    with schema_context(tenant.schema_name):
        owner = (
            Membership.objects.filter(role=Membership.ROLE_OWNER, user__is_active=True)
            .select_related("user")
            .order_by("created_at")
            .first()
        )
        email = owner.user.email if owner else ""
    return email or (tenant.owner_email or "")


def bound_message(tenant, uid: int, result: str, lang: str = "") -> str:
    """Почта подтверждена → сообщение в чат регистрации (один раз на бизнес)."""
    from apps.telegram import bots

    from .handler import locale_for

    bot = bots.platform_bot()
    if bot is None or not uid:
        return "off"
    if not cache.add(f"tgplat:signup-bound-msg:{tenant.pk}", 1, 7 * 86400):
        return "already"
    with translation.override(locale_for(lang)):
        ok = False
        if result == "bound":
            login = {
                "text": "🔑 " + _("Anmeldelink per E-Mail"),
                "callback_data": f"ps:l:{tenant.pk}",
            }
            ok = _send(
                bot,
                uid,
                _(
                    "✅ E-Mail bestätigt — Ihr Geschäft „%(name)s“ ist jetzt hier verbunden. "
                    "Neue Aktionen: einfach hier schreiben."
                )
                % {"name": tenant.name},
                {"inline_keyboard": [[login]]},
            )
        else:
            ok = _send(
                bot,
                uid,
                _(
                    "E-Mail bestätigt. Benachrichtigungen für „%(name)s“ laufen über einen "
                    "anderen Chat (im Kabinett festgelegt)."
                )
                % {"name": tenant.name},
            )
    if not ok:
        cache.delete(f"tgplat:signup-bound-msg:{tenant.pk}")  # повтор задачи пришлёт снова
    return result


def resend_confirmation(bot, uid, chat, tenant_ref: str) -> str:
    """✉️ — письмо подтверждения ещё раз: только чату, который этот бизнес регистрировал."""
    import hashlib

    from apps.core import owner_login
    from apps.tenants.models import Tenant

    tenant = (
        Tenant.objects.filter(pk=tenant_ref).first()
        if tenant_ref.isascii() and tenant_ref.isdigit()
        else None
    )
    marker = links.pending_marker(tenant) if tenant is not None else None
    if tenant is None or not tenant.email_pending or not marker or int(marker["uid"]) != int(uid):
        _send(bot, chat, _("Nicht verfügbar."))
        return "denied"
    email = _owner_email(tenant)
    if not email:
        _send(bot, chat, _("Nicht verfügbar."))
        return "denied"
    mail_key = hashlib.sha256(email.encode()).hexdigest()
    if (
        _rate("tgplat-confirm-resend", uid, LIMIT_CONFIRM_RESEND, 3600)
        or _rate("owner-confirm", tenant.schema_name, 3, 3600)
        or _rate("tgplat-signup-mail", mail_key, LIMIT_MAIL, 86400)
    ):
        _send(bot, chat, _("Zu viele Versuche. Bitte später erneut."))
        return "limited"
    owner_login.send_confirmation(tenant, email)
    _send(bot, chat, _("Bestätigungslink an %(mail)s gesendet.") % {"mail": _mask(email)})
    return "sent"


def remind_pending(bot, uid, chat) -> str:
    """Чат с неподтверждёнными бизнесами пишет боту — напомнить про почту."""
    pending = list(links.pending_for(uid)[:MAX_BOT_BUSINESSES])
    if not pending:
        return ""
    rows = [
        [{"text": "✉️ " + tenant.name[:50], "callback_data": f"ps:m:{tenant.pk}"}]
        for tenant in pending
    ]
    _send(
        bot,
        chat,
        _(
            "Bitte zuerst Ihre E-Mail bestätigen — danach ist der Chat verbunden. Link erneut senden:"
        ),
        {"inline_keyboard": rows},
    )
    return "awaiting_email"


def _promo_url(tenant, promo_pk) -> str:
    from django.urls import reverse

    from apps.tenants.services import site_url_for

    try:
        path = reverse("storefront-promotion", args=[promo_pk], urlconf="config.urls_tenant")
    except Exception:  # noqa: BLE001
        return ""
    return site_url_for(tenant) + path


def send_login_link(bot, uid, chat, tenant_ref: str, *, next_path: str = "") -> str:
    """🔑 — ссылка входа в кабинет ПИСЬМОМ (вход только через почту, решение владельца)."""
    from django_tenants.utils import schema_context

    from apps.core import owner_login
    from apps.core.models import Membership
    from apps.tenants.models import Tenant

    tenant = (
        Tenant.objects.filter(pk=tenant_ref).first()
        if tenant_ref.isascii() and tenant_ref.isdigit()
        else None
    )
    if tenant is None or not links.is_owner(uid, tenant) or not links.still_owner(tenant):
        _send(bot, chat, _("Nicht verfügbar."))
        return "denied"
    if _rate("tgplat-login-link", uid, 3, 3600):
        _send(bot, chat, _("Zu viele Versuche. Bitte später erneut."))
        return "limited"
    with schema_context(tenant.schema_name):
        owner = (
            Membership.objects.filter(role=Membership.ROLE_OWNER, user__is_active=True)
            .select_related("user")
            .order_by("created_at")
            .first()
        )
        email = owner.user.email if owner else ""
    if not email:
        _send(bot, chat, _("Nicht verfügbar."))
        return "denied"
    import hashlib

    # Лимит на получателя: адрес владельца задавал регистрирующий — не заваливать ящик.
    if _rate(
        "tgplat-login-mail", hashlib.sha256(email.encode()).hexdigest(), LIMIT_LOGIN_MAIL, 3600
    ):
        _send(bot, chat, _("Zu viele Versuche. Bitte später erneut."))
        return "limited"
    owner_login.send_login_link(tenant, email, next_path=next_path)
    _send(bot, chat, _("Anmeldelink an %(mail)s gesendet.") % {"mail": _mask(email)})
    return "sent"
