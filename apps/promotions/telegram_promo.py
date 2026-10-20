"""T-8.10b: акция из сообщения владельца в Telegram (B-1: правила, без ИИ).

План — docs/t8-10b-telegram-promo-plan-2026-10-19.md. Поток: сообщение владельца в
личном чате бота → Celery (дедуп по update_id) → `message_parse` → черновик в кэше
(24 ч, только поля формы и file_id фото) → превью с кнопками ✅/✏️/❌ → ✅ проходит ТУ ЖЕ
форму и хвост, что веб-ассистент T-8.4 (лимит 5, срок, товар), ✏️ открывает веб-форму с
префиллом. Только владелец: личный чат, chat.id == from.id == owner_chat_id. Миграций нет.
"""

from __future__ import annotations

import logging
import re
import secrets
import time
from contextlib import contextmanager
from contextvars import ContextVar

from django.conf import settings
from django.core.cache import cache
from django.db import connection, transaction
from django.urls import reverse
from django.utils import formats, translation
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

DRAFT_TTL = 24 * 3600
DONE_TTL = 7 * 24 * 3600
CLAIM_TTL = 180  # «pending» живёт коротко: упавший воркер не запирает черновик на неделю
ALBUM_TTL = 10 * 60
RATE_LIMIT = 30  # черновиков на чат в час
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16}$")
# H-7a: ph — «📷 Foto hinzufügen» (следующие фото — в этот черновик), px — убрать фото.
# H-7d: wh — «📍 Wo erscheint sie?» после публикации (токен → pk акции из mark_done).
CALLBACK_RE = re.compile(r"^tp:(ok|no|ph|px|wh):([A-Za-z0-9_-]{16})$")
LAST_TTL = 30 * 60  # фото без подписи в течение 30 мин после превью — в последний черновик
REPEAT_CALLBACK_RE = re.compile(
    r"^tp:rp:([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$"
)
REPEAT_COMMAND_RE = re.compile(r"(?i)^/(?:wiederholen|nochmal|repeat)(?:@\w+)?\s*$")
REPEAT_LIMIT = 3
WARNING_LIMIT = 3


# --- кто и где ----------------------------------------------------------------------------


# T-8.10h H-4: превью/меню в ОБЩЕМ боте — кнопки заворачиваются в `pb:<ref>` (схема в
# кэше), сверху «Für: <бизнес>». Вне общего бота значения пустые → вывод байт-в-байт.
_CALLBACK_WRAP: ContextVar = ContextVar("tp_callback_wrap", default=None)
_BUSINESS: ContextVar = ContextVar("tp_business", default="")


def _cbdata(data: str) -> str:
    wrap = _CALLBACK_WRAP.get()
    return wrap(data) if wrap else data


@contextmanager
def platform_scope(schema: str, chat, tenant):
    """Контекст ответа через общий бот: кнопки `pb:`, адресат-бизнес в тексте."""
    from apps.platform_bot import routing

    tokens = (
        _CALLBACK_WRAP.set(lambda data: routing.wrap(int(chat), schema, data)),
        _BUSINESS.set(getattr(tenant, "name", "") or ""),
    )
    try:
        yield
    finally:
        _CALLBACK_WRAP.reset(tokens[0])
        _BUSINESS.reset(tokens[1])


def _business_line() -> str:
    name = _BUSINESS.get()
    return "🏪 " + _("Für: %(name)s") % {"name": name} if name else ""


def owner_ok(tenant, chat, bot_kind: str = "tenant") -> bool:
    """Право писать от имени бизнеса. Свой бот — чат владельца из настроек (как было);
    общий бот — живая связь в ТАБЛИЦЕ + выпустивший ссылку всё ещё владелец."""
    from apps.telegram import bots

    if tenant is None or not chat:
        return False
    if bot_kind == bots.PLATFORM:
        from apps.platform_bot import links

        return (
            str(chat).isdigit() and links.is_owner(int(chat), tenant) and links.still_owner(tenant)
        )
    return str(chat) == owner_chat(tenant)


def owner_chat(tenant) -> str:
    from apps.telegram.notify import owner_chat_id

    return str(owner_chat_id(tenant) or "") if tenant is not None else ""


def is_owner_private(message: dict, tenant) -> bool:
    """Личный чат ВЛАДЕЛЬЦА: chat.id == from.id == owner_chat_id, не бот."""
    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    owner = owner_chat(tenant)
    return bool(
        owner
        and (chat.get("type") or "") == "private"
        and str(chat.get("id")) == owner
        and str(sender.get("id")) == owner
        and not sender.get("is_bot")
    )


def bot_locale(sender: dict | None, tenant) -> str:
    """Язык ответов: язык Telegram владельца, если он среди языков кабинета, иначе бизнеса."""
    from apps.notifications.services import tenant_locale

    code = str((sender or {}).get("language_code") or "")[:2].lower()
    if code in getattr(settings, "CABINET_LANGUAGES", ()):
        return code
    return tenant_locale()


def gate(tenant) -> str:
    """ "" — можно; иначе текст отказа (модуль акций выключен / подписка ограничена)."""
    from apps.billing.state_machine import GATED_STATUSES
    from apps.core.modules import is_module_active

    if getattr(tenant, "subscription_status", "") in GATED_STATUSES:
        return _("Ihr Konto ist eingeschränkt — bitte im Kabinett die Abrechnung prüfen.")
    if not is_module_active(tenant, "promotions"):
        return _("Aktionen sind in Ihrem Kabinett nicht aktiv.")
    return ""


def owner_user(tenant):
    from apps.core.models import Membership

    m = Membership.objects.filter(role=Membership.ROLE_OWNER).select_related("user").first()
    return m.user if m else None


# --- черновики ----------------------------------------------------------------------------


def _last_key(schema: str, chat: str) -> str:
    return f"tgpromo:last:{schema}:{chat}"


def _arm_key(schema: str, chat: str) -> str:
    """«📷 Foto hinzufügen» нажата: следующие фото (и альбомы) — в этот черновик."""
    return f"tgpromo:arm:{schema}:{chat}"


def remember_last(schema: str, chat: str, token: str) -> None:
    cache.set(_last_key(schema, str(chat)), token, LAST_TTL)


def photo_tip() -> str:
    """Как работать с фото — одна строка для приветствия, подсказок и /hilfe."""
    from . import quick

    return "📷 " + _(
        "Fotos: mit der Beschreibung senden (als Album bis zu %(n)s Fotos) oder später "
        "über „📷 Foto hinzufügen“ in der Vorschau nachschicken. Das erste Foto ist das Titelbild."
    ) % {"n": quick.MAX_PHOTOS}


def _draft_key(schema: str, chat: str, token: str) -> str:
    return f"tgpromo:draft:{schema}:{chat}:{token}"


def _done_key(schema: str, token: str) -> str:
    return f"tgpromo:done:{schema}:{token}"


def store_draft(schema: str, chat: str, data: dict) -> str:
    token = secrets.token_urlsafe(12)
    cache.set(_draft_key(schema, chat, token), data, DRAFT_TTL)
    return token


def load_draft(schema: str, chat: str, token: str) -> dict | None:
    if not TOKEN_RE.match(token or ""):
        return None
    value = cache.get(_draft_key(schema, str(chat), token))
    return value if isinstance(value, dict) else None


def drop_draft(schema: str, chat: str, token: str) -> None:
    cache.delete(_draft_key(schema, str(chat), token))


def load_for_web(tenant, token: str) -> dict | None:
    """✏️: черновик для веб-формы — chat берётся из ТЕКУЩЕЙ привязки владельца."""
    chat = owner_chat(tenant)
    draft = load_draft(connection.schema_name, chat, token) if chat else None
    if draft is None:
        # Общий бот: зеркало могло устареть (Save кабинета) — чат из живой связи.
        from apps.platform_bot.models import OwnerTelegramLink

        link = OwnerTelegramLink.objects.filter(tenant=tenant, is_active=True).first()
        if link is not None and str(link.tg_user_id) != chat:
            draft = load_draft(connection.schema_name, str(link.tg_user_id), token)
    return draft


def mark_done(schema: str, token: str, pk) -> None:
    cache.set(_done_key(schema, token), str(pk), DONE_TTL)


def claim(schema: str, token: str) -> bool:
    """Атомарный замок публикации (общий для ✅ в Telegram и Save в веб-форме)."""
    return cache.add(_done_key(schema, token), "pending", CLAIM_TTL)


def done_value(schema: str, token: str):
    return cache.get(_done_key(schema, token))


def release(schema: str, token: str) -> None:
    cache.delete(_done_key(schema, token))


# --- черновик из сообщения ----------------------------------------------------------------


def draft_from_parsed(parsed, tenant, *, photo_ids=()) -> dict:
    from apps.core import city_categories as cc

    from . import ai_draft, quick

    data = {
        "title": parsed.title,
        "description": parsed.description,
        "new_price": "" if parsed.new_price is None else str(parsed.new_price),
        "old_price": "" if parsed.old_price is None else str(parsed.old_price),
        "percent": "" if parsed.percent is None else str(parsed.percent),
        "quantity": "" if parsed.quantity is None else str(parsed.quantity),
        "term": parsed.term or quick.default_term(tenant),
        "until": parsed.until.isoformat() if parsed.until else "",
        "until_time": parsed.until_time.strftime("%H:%M") if parsed.until_time else "",
        "until_time_for": quick.until_time_key(parsed.term, parsed.until)
        if parsed.until_time
        else "",
        "customer_response": quick.default_response(tenant),
        "city_category": cc.suggest_for_business_type(getattr(tenant, "business_type", "")),
        "product": "",
        "photo_ids": list(photo_ids)[: quick.MAX_PHOTOS],
        "warnings": list(parsed.warnings),
    }
    # Свой товар — только при единственном совпадении целым словом (иначе каждое
    # сообщение заводило бы товар-дубль).
    try:
        product, _candidates = ai_draft.match_own_product(parsed.title, parsed.title)
    except Exception:  # noqa: BLE001 — подсказка товара необязательна
        product = None
    if product is not None:
        data["product"] = str(product.pk)
    return data


def form_for(draft: dict, tenant):
    from . import quick

    post = {
        k: v
        for k, v in draft.items()
        if k not in ("photo_ids", "warnings", "bot") and v not in (None, "")
    }
    form = quick.QuickPromotionForm(data=post, files=None, tenant=tenant)
    form.is_valid()
    return form


def _warning(code: str) -> str:
    texts = {
        "price_condition": _("Bedingungen wie „2 für 1“ bitte im Formular (✏️) eintragen."),
        "time_past": _("Die Uhrzeit liegt schon in der Vergangenheit — Frist ohne Uhrzeit."),
        "price_and_percent": _("Preis und Rabatt zugleich — es zählt der Preis."),
        "old_not_higher": _("Der „statt“-Preis ist nicht höher — weggelassen."),
        "date_rolled": _("Das Datum liegt im nächsten Jahr."),
    }
    if code.startswith("claim:"):
        return _("Bitte prüfen: „%(word)s“ ist eine Werbeaussage.") % {"word": code[6:40]}
    return texts.get(code, "")


def _money(value) -> str:
    return formats.number_format(value, 2, use_l10n=True)


def render_preview(draft: dict, tenant, form, token: str) -> tuple[str, dict]:
    """Текст превью (без parse_mode) + клавиатура ✅/✏️/❌."""
    from . import limits
    from . import text_check as ptc

    lines = ["📣 " + _("Entwurf")]
    if _business_line():
        lines.append(_business_line())
    lines.append(draft.get("title") or "—")
    facts = []
    if draft.get("new_price"):
        price = _money(draft["new_price"]) + " €"
        if draft.get("old_price"):
            price += " " + _("statt") + " " + _money(draft["old_price"]) + " €"
        facts.append(price)
    elif draft.get("percent"):
        facts.append(f"−{draft['percent']} %")
    if form.is_valid():
        promo = form.build()
        end = promo.ends_at
        if end is not None:
            from django.utils import timezone

            local = timezone.localtime(end)
            facts.append(
                _("bis %(when)s") % {"when": formats.date_format(local, "SHORT_DATETIME_FORMAT")}
            )
    if draft.get("quantity"):
        facts.append(_("%(n)s Stück") % {"n": draft["quantity"]})
    if facts:
        lines.append(" · ".join(facts))
    if draft.get("photo_ids"):
        lines.append(f"📷 {len(draft['photo_ids'])}")
    elif draft.get("photo_from"):
        lines.append("📷 " + _("Fotos aus der Vorlage"))
    product = form.cleaned_data.get("product") if form.is_valid() else None
    if product is not None:
        # Свой товар задаёт «обычную» цену витрины — владелец видит его до ✅.
        lines.append("📦 " + str(product))
    if draft.get("ai_draft"):
        lines.append("✨ " + _("Vorschlag aus dem Foto — bitte prüfen."))
    notes = [_warning(c) for c in draft.get("warnings") or () if _warning(c)]
    if form.is_valid():
        try:
            for finding in ptc.for_promotion(form.build(), tenant)[:WARNING_LIMIT]:
                notes.append(str(getattr(finding, "message", "") or ""))
        except Exception:  # noqa: BLE001 — подсказки необязательны
            pass
    else:
        for errors in form.errors.values():
            notes.extend(str(e) for e in errors)
    usage = limits.usage(tenant)
    if usage and usage.get("full"):
        notes.append(_("Limit erreicht — ✅ speichert als Entwurf."))
    lines += ["⚠️ " + n for n in notes if n][: WARNING_LIMIT + 3]

    buttons = []
    if form.is_valid():
        buttons.append(
            {"text": "✅ " + _("Veröffentlichen"), "callback_data": _cbdata(f"tp:ok:{token}")}
        )
    edit = edit_url(token)
    if edit:
        buttons.append({"text": "✏️ " + _("Bearbeiten"), "url": edit})
        if draft.get("bot") == "platform":
            lines.append("✏️ " + _("Bearbeiten im Browser — nicht angemeldet? /kabinett"))
    buttons.append({"text": "❌ " + _("Verwerfen"), "callback_data": _cbdata(f"tp:no:{token}")})
    photo_row = [{"text": "📷 " + _("Foto hinzufügen"), "callback_data": _cbdata(f"tp:ph:{token}")}]
    if draft.get("photo_ids") or draft.get("photo_from"):
        photo_row.append(
            {"text": "🗑 " + _("Fotos entfernen"), "callback_data": _cbdata(f"tp:px:{token}")}
        )
    return "\n".join(lines), {"inline_keyboard": [buttons, photo_row]}


def edit_url(token: str) -> str:
    from apps.telegram.services import tenant_base_url

    base = tenant_base_url()
    if not base:
        return ""
    path = reverse("promotions:promotion-quick", urlconf="config.urls_tenant")
    return f"{base}{path}?entwurf={token}"


def _bot_kind(bot) -> str:
    """Вид бота (T-8.10h): у своего бота-модели атрибута ``kind`` нет — это свой бот."""
    from apps.telegram import bots

    return getattr(bot, "kind", bots.TENANT)


def _send(bot, chat, text: str, markup=None, photo_id: str = "") -> bool:
    """Ответ в чат. Ошибка HTTP НЕ уходит наружу: текст requests.HTTPError содержит
    URL с токеном бота, а вебхук пишет трейсбэк в лог/Sentry."""
    from apps.telegram import services

    try:
        if photo_id and len(text) <= services.CAPTION_MAX:
            try:
                services.send_photo(bot.token, chat, photo_id, text, reply_markup=markup)
                return True
            except Exception:  # noqa: BLE001 — фото не ушло: текст важнее картинки
                pass
        services.send_message(bot.token, chat, text, reply_markup=markup)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("tg promo send failed: %s", type(exc).__name__)
        return False


# --- приём сообщения ----------------------------------------------------------------------


def slim_update(update: dict) -> dict:
    """В брокер — только нужные поля апдейта."""
    message = update.get("message") or {}
    photos = message.get("photo") or []
    largest = photos[-1].get("file_id") if photos and isinstance(photos[-1], dict) else ""
    sender = message.get("from") or {}
    return {
        "update_id": update.get("update_id"),
        "chat_id": (message.get("chat") or {}).get("id"),
        "text": str(message.get("text") or message.get("caption") or "")[:2000],
        "photo": str(largest or "")[:200],
        "media_group_id": str(message.get("media_group_id") or "")[:64],
        "language_code": str(sender.get("language_code") or "")[:8],
    }


def enqueue_owner_message(bot, update: dict, tenant) -> str:
    from apps.core import ratelimit

    from . import tasks

    slim = slim_update(update)
    chat = str(slim["chat_id"])
    with translation.override(bot_locale({"language_code": slim["language_code"]}, tenant)):
        if ratelimit.hit(
            "tg-promo", f"{connection.schema_name}:{chat}", limit=RATE_LIMIT, window=3600
        ):
            _send(bot, chat, _("Zu viele Entwürfe — bitte später erneut versuchen."))
            return "limited"
        try:
            tasks.telegram_owner_message.delay(
                dedupe_key=f"tgmsg:{connection.schema_name}:{slim['update_id']}",
                schema=connection.schema_name,
                update=slim,
                bot_kind=_bot_kind(bot),
            )
        except Exception as exc:  # брокер недоступен — честно сказать, а не молча потерять
            logger.warning("tg promo enqueue failed: %s", type(exc).__name__)
            _send(bot, chat, _("Gerade nicht möglich — bitte später erneut senden."))
            return "failed"
    return "queued"


def _album_key(schema: str, chat: str, group: str) -> str:
    return f"tgpromo:mg:{schema}:{chat}:{group}"


def _album_wait_key(schema: str, chat: str, group: str) -> str:
    return f"tgpromo:mgw:{schema}:{chat}:{group}"


@contextmanager
def _album_lock(schema: str, chat: str, group: str):
    """Фото альбома приходят отдельными задачами почти одновременно — без замка
    read-modify-write списка фото терял бы обновления. Не дождались — работаем без замка."""
    key = f"tgpromo:mgl:{schema}:{chat}:{group}"
    got = False
    for _i in range(30):
        if cache.add(key, "1", 15):
            got = True
            break
        time.sleep(0.1)
    try:
        yield
    finally:
        if got:
            cache.delete(key)


def handle_owner_message(schema: str, update: dict, bot_kind: str = "tenant") -> str:
    """Тело Celery-задачи: разбор → черновик → превью. Никогда не бросает наружу."""
    from django_tenants.utils import schema_context

    from apps.telegram import bots
    from apps.tenants.models import Tenant

    with schema_context(schema):
        tenant = Tenant.objects.filter(schema_name=schema).first()
        bot = bots.for_kind(bot_kind)
        if tenant is None or bot is None:
            return "skip"
        chat = str(update.get("chat_id") or "")
        if not owner_ok(tenant, chat, bot_kind):
            return "skip"  # владелец перепривязан, пока сообщение ждало в очереди
        with translation.override(
            bot_locale({"language_code": update.get("language_code")}, tenant)
        ):
            try:
                if bot_kind == bots.PLATFORM:
                    with platform_scope(schema, chat, tenant):
                        return _handle(bot, tenant, schema, chat, update)
                return _handle(bot, tenant, schema, chat, update)
            except Exception as exc:  # noqa: BLE001 — без трейсбэка: в нём текст владельца
                logger.warning("tg promo failed: %s", type(exc).__name__)
                # Повтор того же update_id задача не возьмёт (дедуп) — сказать честно.
                _send(bot, chat, _("Das hat nicht geklappt — bitte die Nachricht erneut senden."))
                return "error"


def _handle(bot, tenant, schema, chat, update) -> str:
    reason = gate(tenant)
    if reason:
        _send(bot, chat, reason)
        return "gated"
    if REPEAT_COMMAND_RE.match((update.get("text") or "").strip()) and not update.get("photo"):
        return repeat_menu(bot, chat)
    photo = update.get("photo") or ""
    group = update.get("media_group_id") or ""
    if photo and not (update.get("text") or "").strip():
        added = _photo_to_last(bot, tenant, schema, chat, photo, group)
        if added:
            return added
    if group and photo:
        with _album_lock(schema, chat, group):
            result = _album_photo(schema, chat, group, photo, update)
        if result:
            return result
    return _new_draft(bot, tenant, schema, chat, update, photo, group)


def _photo_to_last(bot, tenant, schema, chat, photo, group) -> str:
    """H-7a: фото без подписи вскоре после превью — в ПОСЛЕДНИЙ черновик, а не новый.

    Одиночное фото — в последний черновик всегда. Альбом — ТОЛЬКО после «📷 Foto
    hinzufügen»: подпись альбома может прийти на любом его фото и позже остальных, и без
    явной кнопки фото нового альбома ушли бы в старый черновик (ревью H-7a). Превью —
    один раз на альбом (иначе по сообщению на каждое фото)."""
    from . import quick

    token = cache.get(_arm_key(schema, chat)) if group else cache.get(_last_key(schema, chat))
    if not token:
        return ""
    lock = f"tgpromo:lastlock:{schema}:{chat}"
    for _attempt in range(30):
        if cache.add(lock, "1", 15):
            break
        import time

        time.sleep(0.1)
    else:
        return "photo_busy"  # не новый черновик из одиночного фото: просто пропуск
    try:
        draft = load_draft(schema, chat, token)
        # file_id фото принадлежит боту: фото из своего бота не смешиваем с черновиком
        # общего бота (и наоборот) — Telegram не отдаст чужой файл.
        if draft is None or draft.get("bot", "tenant") != _bot_kind(bot):
            return ""
        if done_value(schema, token) is not None:
            return ""  # ✅ уже взял черновик в публикацию — фото к нему не дописать
        ids = list(draft.get("photo_ids") or [])
        if photo in ids:
            return "photo_dup"
        if len(ids) >= quick.MAX_PHOTOS:
            if not group or cache.add(f"tgpromo:fullmsg:{schema}:{chat}:{group}", 1, ALBUM_TTL):
                _send(bot, chat, _("Höchstens %(n)s Fotos pro Aktion.") % {"n": quick.MAX_PHOTOS})
            return "photo_full"
        ids.append(photo)
        draft["photo_ids"] = ids
        draft.pop("photo_from", None)  # свои фото заменяют фото шаблона-повтора
        cache.set(_draft_key(schema, chat, token), draft, DRAFT_TTL)
        if group:
            cache.set(_album_key(schema, chat, group), token, ALBUM_TTL)
            if not cache.add(f"tgpromo:albumpreview:{schema}:{chat}:{group}", 1, ALBUM_TTL):
                return "photo_added"
    finally:
        cache.delete(lock)
    _resend_preview(bot, tenant, schema, chat, token, draft)
    return "photo_added"


def _resend_preview(bot, tenant, schema, chat, token, draft) -> None:
    form = form_for(draft, tenant)
    text, markup = render_preview(draft, tenant, form, token)
    ids = draft.get("photo_ids") or []
    _send(bot, chat, text, markup, photo_id=ids[0] if ids else "")


def _album_photo(schema, chat, group, photo, update) -> str:
    """Фото альбома: к уже созданному черновику — дописать; подпись ещё не пришла —
    отложить молча (Telegram кладёт подпись на одно фото, порядок задач не гарантирован)."""
    from . import quick

    token = cache.get(_album_key(schema, chat, group))
    draft = load_draft(schema, chat, token) if token else None
    if draft is not None:
        ids = list(draft.get("photo_ids") or [])
        if photo not in ids and len(ids) < quick.MAX_PHOTOS:
            ids.append(photo)
            draft["photo_ids"] = ids
            cache.set(_draft_key(schema, chat, token), draft, DRAFT_TTL)
        return "album"
    if not (update.get("text") or "").strip():
        wait_key = _album_wait_key(schema, chat, group)
        waiting = list(cache.get(wait_key) or [])
        if photo not in waiting and len(waiting) < quick.MAX_PHOTOS:
            waiting.append(photo)
        cache.set(wait_key, waiting, ALBUM_TTL)
        return "album_wait"
    return ""


def _new_draft(bot, tenant, schema, chat, update, photo, group) -> str:
    from . import message_parse, quick

    parsed = message_parse.parse(update.get("text") or "")
    if not parsed.signals and not photo:
        _send(
            bot,
            chat,
            _(
                "Schicken Sie z. B.: „Brötchen 2,50 € statt 3,90 €, heute bis 18 Uhr, 20 Stück“ — gern mit Foto."
            )
            + "\n"
            + photo_tip(),
        )
        return "hint"
    draft = draft_from_parsed(parsed, tenant, photo_ids=[photo] if photo else [])
    draft["bot"] = _bot_kind(bot)  # file_id фото привязан к боту (T-8.10h)
    if photo:
        # B-2: ИИ — до замка альбома (вызов долгий), и только в ПУСТЫЕ описательные поля.
        ai_fill(bot, tenant, draft, photo, hint=parsed.title)
    if not draft.get("title"):
        _send(bot, chat, _("Wie heißt das Angebot? Schreiben Sie es bitte dazu."))
        return "no_title"
    cache.delete(_arm_key(schema, chat))  # новая акция — «📷» старой больше не действует
    if group:
        with _album_lock(schema, chat, group):
            waiting = cache.get(_album_wait_key(schema, chat, group)) or []
            cache.delete(_album_wait_key(schema, chat, group))
            ids = draft["photo_ids"] + [p for p in waiting if p not in draft["photo_ids"]]
            draft["photo_ids"] = ids[: quick.MAX_PHOTOS]
            token = store_draft(schema, chat, draft)
            cache.set(_album_key(schema, chat, group), token, ALBUM_TTL)
    else:
        token = store_draft(schema, chat, draft)
    remember_last(schema, chat, token)
    form = form_for(draft, tenant)
    text, markup = render_preview(draft, tenant, form, token)
    _send(bot, chat, text, markup, photo_id=photo)
    return "preview"


AI_FIELDS = ("title", "description")


def ai_fill(bot, tenant, draft: dict, photo_id: str, *, hint: str = "") -> bool:
    """B-2 (T-8.10a в Telegram): ИИ по фото дописывает ТОЛЬКО пустые описательные поля —
    название, описание, раздел/признаки каталога города, свой товар. Цены, скидки, сроки и
    количество приходят только из текста владельца (правила). ИИ выключен / сбой — черновик
    как без ИИ. Фото уходит провайдеру уменьшенной копией без EXIF."""
    from apps.ai.api import is_enabled
    from apps.ai.images import reencode
    from apps.core import city_categories as cc
    from apps.telegram import services

    from . import ai_draft

    if not is_enabled():
        return False
    # Раздел по типу бизнеса — подстановка, а не выбор владельца: ИИ по фото точнее.
    guessed = cc.suggest_for_business_type(getattr(tenant, "business_type", ""))
    category_open = draft.get("city_category") in ("", None, guessed)
    if all(draft.get(f) for f in AI_FIELDS) and not category_open and draft.get("city_tags"):
        return False  # заполнять нечего — не тратить вызов
    data = services.download_file(bot.token, photo_id)
    if not data:
        return False
    try:
        photo = reencode(data)
        result, _code = ai_draft.draft_from_photo(photo, hint=hint, tenant=tenant)
    except Exception as exc:  # noqa: BLE001 — подсказка необязательна
        logger.info("tg promo ai skipped: %s", type(exc).__name__)
        return False
    if not result or not result.get("recognised"):
        return False
    used = False
    for field in AI_FIELDS:
        if not draft.get(field) and result.get(field):
            draft[field], used = result[field], True
    if category_open and result.get("city_category"):
        if result["city_category"] != draft.get("city_category"):
            draft["city_category"], used = result["city_category"], True
    if not draft.get("city_tags") and result.get("city_tags"):
        draft["city_tags"], used = list(result["city_tags"]), True
    product = result.get("product")
    if not draft.get("product") and product:
        draft["product"], used = str(product["pk"]), True
    if used:
        draft["ai_draft"] = "1"
        # Подсказки «claims» ИИ-текста (как в веб-ассистенте) — в превью.
        known = list(draft.get("warnings") or [])
        claims = [f"claim:{w}" for w in result.get("warnings") or []]
        draft["warnings"] = known + [c for c in claims if c not in known]
    return used


# --- нажатия кнопок -----------------------------------------------------------------------


# --- B-3: повтор прошлой акции ------------------------------------------------------------


def repeat_menu(bot, chat) -> str:
    """`/wiederholen`: три последние прошедшие акции кнопками «🔁 <название>»."""
    from django.db.models import F

    from .models import Promotion
    from .views import REPEATABLE_STATUSES

    promos, seen = [], set()
    candidates = Promotion.objects.filter(status__in=REPEATABLE_STATUSES).order_by(
        F("ends_at").desc(nulls_last=True), "-created_at"
    )
    for promo in candidates[: REPEAT_LIMIT * 5]:
        key = (promo.title_text or "").casefold()
        if key in seen:
            continue  # каждый повтор — новая прошедшая акция; одинаковые кнопки не нужны
        seen.add(key)
        promos.append(promo)
        if len(promos) == REPEAT_LIMIT:
            break
    if not promos:
        _send(bot, chat, _("Noch keine vergangene Aktion zum Wiederholen."))
        return "repeat_empty"
    rows = [
        [{"text": "🔁 " + (p.title_text or "—")[:40], "callback_data": _cbdata(f"tp:rp:{p.pk}")}]
        for p in promos
    ]
    title = _("Welche Aktion wiederholen?")
    if _business_line():
        title = f"{title}\n{_business_line()}"
    _send(bot, chat, title, {"inline_keyboard": rows})
    return "repeat_menu"


def draft_from_promotion(promo, tenant) -> dict:
    """Черновик-повтор: то же предложение (`quick.initial_from`), срок — неделя."""
    from apps.core import city_categories as cc

    from . import quick

    # Срок — как у веб «↻ Wiederholen» (`initial_from` ставит неделю).
    initial = {
        "customer_response": quick.default_response(tenant),
        "city_category": cc.suggest_for_business_type(getattr(tenant, "business_type", "")),
        **quick.initial_from(promo),
    }
    data = {}
    for key, value in initial.items():
        if key == "city_tags":
            data[key] = [str(v) for v in value]
        elif isinstance(value, bool):
            data[key] = "1" if value else ""
        else:
            data[key] = str(value)
    data.update(photo_ids=[], warnings=[])
    return data


def _repeat(bot, tenant, schema, chat, pk) -> str:
    from .views import REPEATABLE_STATUSES

    promo = source_promo(pk)
    if promo is None or promo.status not in REPEATABLE_STATUSES:
        _send(bot, chat, _("Diese Aktion gibt es nicht mehr."))
        return "repeat_missing"
    draft = draft_from_promotion(promo, tenant)
    draft["bot"] = _bot_kind(bot)
    token = store_draft(schema, chat, draft)
    remember_last(schema, chat, token)
    form = form_for(draft, tenant)
    text, markup = render_preview(draft, tenant, form, token)
    _send(bot, chat, text, markup)
    return "preview"


def handle_callback(bot, callback: dict, tenant) -> str:
    """✅/❌ под превью. В вебхуке — только проверка прав и ❌; ✅ (скачивание фото,
    сохранение) уходит в Celery: иначе запрос висел бы минуты и Telegram слал бы повтор."""
    from apps.telegram import services

    cid = str(callback.get("id") or "")
    sender = callback.get("from") or {}
    message = callback.get("message") or {}
    chat = str((message.get("chat") or {}).get("id") or "")
    services.answer_callback_query(bot.token, cid)
    with translation.override(bot_locale(sender, tenant)):
        owner = owner_chat(tenant)
        if not owner or str(sender.get("id")) != owner or chat != owner:
            services.answer_callback_query(bot.token, cid, _("Nicht erlaubt."))
            return "denied"
        return _dispatch_callback(bot, callback, tenant, connection.schema_name)


def handle_platform_callback(bot, schema: str, callback: dict, inner: str) -> str:
    """T-8.10h H-4: кнопка превью общего бота (`pb:` уже разрешён в схему превью).
    Плоский callback общего бота → вложенный формат, права — по таблице связей."""
    from django_tenants.utils import schema_context

    from apps.telegram import bots, services
    from apps.tenants.models import Tenant

    cid = str(callback.get("id") or "")
    chat = str(callback.get("chat_id") or "")
    sender = {"id": callback.get("from_id"), "language_code": callback.get("language_code")}
    with schema_context(schema):
        tenant = Tenant.objects.filter(schema_name=schema).first()
        with translation.override(bot_locale(sender, tenant)):
            if not owner_ok(tenant, chat, bots.PLATFORM):
                services.answer_callback_query(bot.token, cid, _("Nicht erlaubt."))
                return "denied"
            services.answer_callback_query(bot.token, cid)
            nested = {
                "id": cid,
                "from": sender,
                "message": {"chat": {"id": chat}, "message_id": callback.get("message_id")},
                "data": inner,
            }
            with platform_scope(schema, chat, tenant):
                return _dispatch_callback(bot, nested, tenant, schema)


def _dispatch_callback(bot, callback: dict, tenant, schema: str) -> str:
    from apps.telegram import services

    cid = str(callback.get("id") or "")
    sender = callback.get("from") or {}
    message = callback.get("message") or {}
    chat = str((message.get("chat") or {}).get("id") or "")
    data = str(callback.get("data") or "")
    m = CALLBACK_RE.match(data)
    rp = None if m else REPEAT_CALLBACK_RE.match(data)
    if not m and not rp:
        return "skip"
    reason = gate(tenant)
    if reason:
        _send(bot, chat, reason)
        return "gated"
    if rp:
        from apps.core import ratelimit

        # Повтор считается тем же лимитом черновиков, что сообщения (30/ч на чат).
        if ratelimit.hit("tg-promo", f"{schema}:{chat}", limit=RATE_LIMIT, window=3600):
            _send(bot, chat, _("Zu viele Entwürfe — bitte später erneut versuchen."))
            return "limited"
        # Меню убрать: двойной тап не плодит два черновика-повтора.
        services.edit_message_reply_markup(bot.token, chat, message.get("message_id"))
        return _repeat(bot, tenant, schema, chat, rp.group(1))
    action, token = m.groups()
    if action in ("ph", "px"):
        return _photo_button(bot, tenant, schema, chat, token, action)
    if action == "wh":
        return _where(bot, tenant, schema, chat, token)
    if action == "no":
        drop_draft(schema, chat, token)
        services.edit_message_reply_markup(bot.token, chat, message.get("message_id"))
        _send(bot, chat, _("Verworfen."))
        return "dropped"
    return enqueue_confirm(bot, schema, chat, token, message, sender, cid)


WHERE_LIMIT = 20  # проверок «где акция» на чат в час


def _where(bot, tenant, schema, chat, token) -> str:
    """📍 — отчёт «где видна акция» заново (каналы публикуются фоном — статус меняется)."""
    from django.core.exceptions import ValidationError

    from apps.core import ratelimit

    from . import where
    from .models import Promotion

    if ratelimit.hit("tg-where", f"{schema}:{chat}", limit=WHERE_LIMIT, window=3600):
        _send(bot, chat, _("Zu viele Versuche. Bitte später erneut."))
        return "limited"
    pk = done_value(schema, token)
    promo = None
    if pk and pk != "pending":
        try:
            promo = Promotion.objects.filter(pk=pk).first()
        except (ValueError, ValidationError):
            promo = None
    if promo is None:
        _send(bot, chat, _("Nicht verfügbar."))
        return "where_missing"
    _send(bot, chat, "\n".join([promo.get_i18n("title")[:80], *where.report(tenant, promo)]))
    return "where"


def _where_markup(token: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {
                    "text": "📍 " + _("Wo erscheint die Aktion?"),
                    "callback_data": _cbdata(f"tp:wh:{token}"),
                }
            ]
        ]
    }


def _photo_button(bot, tenant, schema, chat, token, action) -> str:
    """📷 — следующие фото идут в этот черновик; 🗑 — фото убрать (превью заново)."""
    from . import quick

    draft = load_draft(schema, chat, token)
    if draft is None:
        _send(bot, chat, _("Der Entwurf ist abgelaufen. Bitte die Aktion erneut senden."))
        return "expired"
    if action == "ph":
        remember_last(schema, chat, token)
        cache.set(_arm_key(schema, chat), token, LAST_TTL)
        _send(
            bot,
            chat,
            _(
                "Schicken Sie jetzt bis zu %(n)s Fotos (auch als Album) — ohne Text. "
                "Sie kommen zu diesem Entwurf."
            )
            % {"n": quick.MAX_PHOTOS},
        )
        return "photo_wait"
    draft["photo_ids"] = []
    draft.pop("photo_from", None)
    cache.set(_draft_key(schema, chat, token), draft, DRAFT_TTL)
    remember_last(schema, chat, token)
    _resend_preview(bot, tenant, schema, chat, token, draft)
    return "photos_removed"


def enqueue_confirm(bot, schema, chat, token, message, sender, cid) -> str:
    from apps.telegram import bots

    from . import tasks

    try:
        tasks.telegram_owner_confirm.delay(
            # Счётчики апдейтов у ботов разные — пространство ключей общего бота отдельное.
            dedupe_key=(
                f"tgcb:{schema}:p:{cid or token}"
                if _bot_kind(bot) == bots.PLATFORM
                else f"tgcb:{schema}:{cid or token}"
            ),
            schema=schema,
            chat=chat,
            token=token,
            message_id=message.get("message_id"),
            language_code=str(sender.get("language_code") or "")[:8],
            bot_kind=_bot_kind(bot),
        )
    except Exception as exc:  # noqa: BLE001 — брокер недоступен
        logger.warning("tg promo confirm enqueue failed: %s", type(exc).__name__)
        _send(bot, chat, _("Gerade nicht möglich — bitte später erneut senden."))
        return "failed"
    return "queued"


def handle_confirm(
    schema, chat, token, message_id, language_code="", bot_kind: str = "tenant"
) -> str:
    """Тело Celery-задачи ✅. Права и подписка перепроверяются: задача могла ждать."""
    from django_tenants.utils import schema_context

    from apps.telegram import bots
    from apps.tenants.models import Tenant

    with schema_context(schema):
        tenant = Tenant.objects.filter(schema_name=schema).first()
        bot = bots.for_kind(bot_kind)
        if bot is None or not owner_ok(tenant, chat, bot_kind):
            return "skip"
        if bot_kind == bots.PLATFORM:
            with platform_scope(schema, chat, tenant):
                return confirm_as_task(bot, tenant, schema, chat, token, message_id, language_code)
        return confirm_as_task(bot, tenant, schema, chat, token, message_id, language_code)


def confirm_as_task(bot, tenant, schema, chat, token, message_id, language_code="") -> str:
    with translation.override(bot_locale({"language_code": language_code}, tenant)):
        reason = gate(tenant)
        if reason:
            _send(bot, chat, reason)
            return "gated"
        try:
            return _confirm(bot, tenant, schema, chat, token, {"message_id": message_id})
        except Exception as exc:  # noqa: BLE001 — без трейсбэка: в нём данные владельца
            logger.warning("tg promo confirm failed: %s", type(exc).__name__)
            _send(bot, chat, _("Das hat nicht geklappt — bitte im Formular prüfen (✏️)."))
            return "error"


def source_promo(pk):
    from django.core.exceptions import ValidationError

    from .models import Promotion

    try:
        return Promotion.objects.filter(pk=pk).first()
    except (ValueError, ValidationError):
        return None


def _promo_url(promo) -> str:
    from apps.telegram.services import tenant_base_url

    path = reverse("storefront-promotion", args=[promo.pk], urlconf="config.urls_tenant")
    return tenant_base_url() + path


def photos_from_telegram(token: str, photo_ids) -> tuple[list, bool]:
    """Фото черновика → загрузки для `save_photos` (без EXIF). → (uploads, failed)."""
    from django.core.files.base import ContentFile

    from apps.ai.images import reencode
    from apps.telegram import services

    uploads, failed = [], False
    for i, file_id in enumerate(photo_ids or ()):
        data = services.download_file(token, file_id)
        if not data:
            failed = True
            continue
        try:
            clean = reencode(data, max_side=2000, quality=88)
        except Exception:  # noqa: BLE001 — не картинка / слишком велика
            failed = True
            continue
        uploads.append(ContentFile(clean, name=f"telegram-{i}.jpg"))
    return uploads, failed


def _confirm(bot, tenant, schema, chat, token, message) -> str:
    if not claim(schema, token):
        value = done_value(schema, token)
        if value and value != "pending":
            from .models import Promotion

            promo = Promotion.objects.filter(pk=value).first()
            if promo is None:  # акцию удалили — черновика тоже нет
                _send(bot, chat, _("Entwurf abgelaufen — bitte neu senden."))
                return "expired"
            if promo.status == "active":
                _send(bot, chat, _("Schon veröffentlicht: %(url)s") % {"url": _promo_url(promo)})
            else:
                _send(bot, chat, _("Schon als Entwurf gespeichert."))
            return "already"
        _send(bot, chat, _("Wird gerade gespeichert …"))
        return "busy"
    try:
        return _confirm_claimed(bot, tenant, schema, chat, token, message)
    except BaseException:
        # Любой сбой после claim — снять замок, иначе черновик «сохраняется» вечно.
        if done_value(schema, token) == "pending":
            release(schema, token)
        raise


def _confirm_claimed(bot, tenant, schema, chat, token, message) -> str:
    from apps.telegram import services

    from . import limits, quick

    draft = load_draft(schema, chat, token)
    if draft is None:
        release(schema, token)
        _send(bot, chat, _("Entwurf abgelaufen — bitte neu senden."))
        return "expired"
    form = form_for(draft, tenant)
    if not form.is_valid():
        release(schema, token)
        _send(bot, chat, _("Bitte im Formular prüfen (✏️)."))
        return "invalid"
    photo_bot = bot
    if draft.get("photo_ids") and draft.get("bot", "tenant") != _bot_kind(bot):
        from apps.telegram import bots

        photo_bot = bots.for_kind(draft.get("bot")) or bot
    uploads, failed = photos_from_telegram(photo_bot.token, draft.get("photo_ids"))
    images = []
    if uploads:
        try:
            images = quick.save_photos(uploads)
        except Exception:  # noqa: BLE001 — акция без фото лучше, чем никакой
            failed, images = True, []
    elif draft.get("photo_from"):
        source = source_promo(draft["photo_from"])
        images = quick.copy_images(source)
        wanted = [i for i in (getattr(source, "images", None) or []) if isinstance(i, dict)]
        failed = len(images) < len([i for i in wanted if i.get("path")])
    try:
        with transaction.atomic():
            promo = form.build()
            promo, activated = quick.publish_built(
                form, promo, images, tenant=tenant, actor=owner_user(tenant)
            )
    except Exception:
        from apps.catalog.images import delete_stored_image

        for ref in images:
            delete_stored_image(ref)  # откат транзакции — файлы не сироты
        raise
    mark_done(schema, token, promo.pk)
    drop_draft(schema, chat, token)
    services.edit_message_reply_markup(bot.token, chat, message.get("message_id"))
    lines = [_business_line()] if _business_line() else []
    markup = None
    if activated:
        lines.append(_("✅ Live: %(url)s") % {"url": _promo_url(promo)})
        try:
            from . import where

            lines += where.report(tenant, promo)[1:]  # своя страница — уже строкой выше
        except Exception as exc:  # noqa: BLE001 — отчёт необязателен, публикация уже есть
            logger.warning("tg promo where failed: %s", type(exc).__name__)
        markup = _where_markup(token)
    else:
        limit = limits.active_limit(tenant)
        lines.append(_("Als Entwurf gespeichert."))
        if limit is not None:
            lines.append(limits.limit_message(limit))
    if failed:
        lines.append(_("Foto konnte nicht übernommen werden."))
    _send(bot, chat, "\n".join(lines), markup)
    return "published" if activated else "draft"
