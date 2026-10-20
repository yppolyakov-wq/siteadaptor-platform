"""T-8.28: бот портала v2 — поиск, разделы, районы и «Folgen» прямо в чате.

Апдейт приходит из вебхука (`telegram_bot.webhook`) задачей Celery с дедупом по update_id.
Поиск — тот же движок, что страница портала (`search.resolve_intent` + `search.execute`
по пулу `portal_scope.pool`), поэтому тематический портал (T-8.14) и в чате показывает
только свою тему. Сам поиск ничего не хранит; чат жителя (`PortalChat`) появляется только
когда он подписывается и подтверждает это кнопкой (согласие на сообщения, UWG §7).
"""

from __future__ import annotations

import logging
import re
import secrets

from django.core.cache import cache
from django.http import QueryDict
from django.utils import formats, timezone, translation
from django.utils.translation import gettext as _

from apps.telegram.updates import locale_for

from .models import AggregatorListing, FollowSubscription, PortalBot, PortalChat, PortalUser

logger = logging.getLogger(__name__)

PAGE = 5  # карточек в сообщении
MAX_PAGES = 5
SECTION_BUTTONS = 8
STATE_TTL = 60 * 60  # «Mehr» и «Diese Suche folgen» живут час
ASK_TTL = 10 * 60  # кнопка подтверждения подписки / удаления
RATE_LIMIT = 20  # действий жителя в минуту на бот
MESSAGE_MAX = 3900  # запас до лимита Telegram 4096
GROUP_TYPES = ("group", "supergroup", "channel")
NEW_CHATS_PER_HOUR = 300  # новых жителей-подписчиков на бот в час (защита от наплыва)


class NewChatsLimited(Exception):
    pass


_CTRL = re.compile(r"[\x00-\x1f\x7f  ]+")
_TOKEN = r"[A-Za-z0-9_-]{6,24}"
_KEY = r"[a-z0-9-]{1,40}"
CALLBACKS = {
    "m": re.compile(r"^m$"),
    "s": re.compile(rf"^s:({_TOKEN}):([0-9])$"),
    "k": re.compile(rf"^k:({_KEY})$"),
    "d": re.compile(rf"^d:({_KEY})$"),
    "sec": re.compile(r"^sec$"),
    "dis": re.compile(r"^dis$"),
    "fb": re.compile(r"^fb:([0-9]{1,12})$"),
    "fk": re.compile(rf"^fk:({_KEY})$"),
    "fd": re.compile(rf"^fd:({_KEY})$"),
    "fq": re.compile(rf"^fq:({_TOKEN})$"),
    "fy": re.compile(rf"^fy:({_TOKEN})$"),
    "fn": re.compile(r"^fn$"),
    "ls": re.compile(r"^ls$"),
    "u": re.compile(r"^u:([0-9]{1,12})$"),
    "pd": re.compile(rf"^pd:(ask|no|yes:{_TOKEN})$"),
    # H-7i: язык (Art. 16) и отказ от всех подписок (Art. 21).
    "pl": re.compile(r"^pl:([a-z]{2})$"),
    "wx": re.compile(r"^wx$"),
}
COMMANDS = {
    "start": re.compile(r"^/start(?:@\w+)?(?:\s.*)?$", re.DOTALL),
    "bereiche": re.compile(r"^/(?:bereiche|sections)(?:@\w+)?\s*$", re.IGNORECASE),
    "stadtteile": re.compile(r"^/(?:stadtteile|districts)(?:@\w+)?\s*$", re.IGNORECASE),
    "folgen": re.compile(r"^/(?:folgen|follows)(?:@\w+)?\s*$", re.IGNORECASE),
    "datenschutz": re.compile(r"^/(?:datenschutz|privacy)(?:@\w+)?\s*$", re.IGNORECASE),
    "loeschen": re.compile(r"^/(?:daten_loeschen|delete_data)(?:@\w+)?\s*$", re.IGNORECASE),
    "export": re.compile(r"^/(?:meine_daten|my_data)(?:@\w+)?\s*$", re.IGNORECASE),
    "berichtigen": re.compile(r"^/(?:berichtigen|correct)(?:@\w+)?\s*$", re.IGNORECASE),
    "pause": re.compile(r"^/(?:pausieren|pause)(?:@\w+)?\s*$", re.IGNORECASE),
    "resume": re.compile(r"^/(?:fortsetzen|resume)(?:@\w+)?\s*$", re.IGNORECASE),
    "widerspruch": re.compile(r"^/(?:widerspruch|object)(?:@\w+)?\s*$", re.IGNORECASE),
}


def parse_callback(data: str) -> tuple[str, tuple] | None:
    """Строгий разбор callback_data: известный префикс + формат, иначе None."""
    data = str(data or "")
    if len(data.encode()) > 64:
        return None
    head = data.split(":", 1)[0]
    pattern = CALLBACKS.get(head)
    if pattern is None:
        return None
    match = pattern.match(data)
    return (head, match.groups()) if match else None


# --- отправка ------------------------------------------------------------------------------


def send(bot, chat, text: str, markup=None) -> bool:
    """Ответ без утечки токена (текст HTTPError содержит URL с токеном)."""
    from apps.telegram import services

    try:
        services.send_message(bot.token, chat, text[:MESSAGE_MAX], reply_markup=markup)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("portal bot send failed: %s", type(exc).__name__)
        return False


def _clean(value, limit: int = 120) -> str:
    return " ".join(_CTRL.sub(" ", str(value or "")).split())[:limit]


def _menu(portal) -> dict:
    rows = [
        [
            {"text": "🗂 " + _("Bereiche"), "callback_data": "sec"},
            {"text": "📍 " + _("Stadtteile"), "callback_data": "dis"},
        ],
        [{"text": "🔔 " + _("Meine Abos"), "callback_data": "ls"}],
    ]
    url = portal_url(portal)
    if url:
        rows.append([{"text": "🔎 " + _("Portal öffnen"), "web_app": {"url": url}}])
    return {"inline_keyboard": rows}


def portal_url(portal) -> str:
    from . import follow

    return f"{follow.base_url(portal)}/" if portal is not None else ""


# --- входная точка ---------------------------------------------------------------------------


def handle(bot_pk: int, update: dict) -> str:
    bot = PortalBot.objects.filter(pk=bot_pk, is_active=True).select_related("portal").first()
    if bot is None or not bot.token or not bot.portal.is_active:
        return "off"
    if "member" in update:
        return _member(bot, update["member"])
    if "callback" in update:
        callback = update["callback"]
        uid, chat = callback.get("from_id"), callback.get("chat_id")
        _answer(bot, callback)
        if not uid or chat != uid:
            return "skip"
        with translation.override(_lang(bot, uid, callback.get("language_code"))):
            if _limited(bot, uid):
                return "limited"
            _touch(bot, uid)
            return _callback(
                bot, uid, str(callback.get("data") or ""), callback.get("language_code")
            )
    message = update.get("message") or {}
    if message.get("chat_type") != "private" or message.get("is_bot"):
        return "skip"
    uid = message.get("from_id")
    if not uid or message.get("chat_id") != uid:
        return "skip"
    with translation.override(_lang(bot, uid, message.get("language_code"))):
        if _limited(bot, uid):
            return "limited"
        _touch(bot, uid)
        return _message(bot, uid, str(message.get("text") or ""), message.get("language_code"))


def _lang(bot, uid, language_code) -> str:
    """H-7i: язык из «/berichtigen» сильнее языка клиента Telegram."""
    from django.conf import settings

    chosen = (
        PortalChat.objects.filter(bot=bot, chat_id=int(uid), locale_chosen_at__isnull=False)
        .values_list("locale", flat=True)
        .first()
        if uid
        else ""
    )
    if chosen and chosen in getattr(settings, "CABINET_LANGUAGES", ()):
        return chosen
    return locale_for(language_code)


def _answer(bot, callback) -> None:
    from apps.telegram import services

    try:
        services.answer_callback_query(bot.token, callback.get("id") or "")
    except Exception as exc:  # noqa: BLE001
        logger.warning("portal bot answer failed: %s", type(exc).__name__)


def _limited(bot, uid) -> bool:
    from apps.core import ratelimit

    if ratelimit.hit("tgportal", f"{bot.pk}:{int(uid)}", limit=RATE_LIMIT, window=60):
        send(bot, uid, _("Zu viele Anfragen — bitte kurz warten."))
        return True
    return False


def _touch(bot, uid) -> None:
    PortalChat.objects.filter(bot=bot, chat_id=int(uid)).update(
        last_seen_at=timezone.now(), blocked_at=None
    )


def _member(bot, member: dict) -> str:
    from apps.telegram import services

    chat = member.get("chat_id")
    if member.get("chat_type") in GROUP_TYPES:
        try:
            services.leave_chat(bot.token, chat)
        except Exception as exc:  # noqa: BLE001
            logger.warning("portal bot leave failed: %s", type(exc).__name__)
        return "left"
    status = member.get("status")
    if status == "kicked":
        PortalChat.objects.filter(bot=bot, chat_id=chat).update(blocked_at=timezone.now())
        return "blocked"
    if status == "member":
        PortalChat.objects.filter(bot=bot, chat_id=chat).update(blocked_at=None)
        return "unblocked"
    return "skip"


def _message(bot, uid, text: str, lang) -> str:
    text = text.strip()
    if COMMANDS["start"].match(text):
        return _start(bot, uid)
    if COMMANDS["bereiche"].match(text):
        return _sections(bot, uid)
    if COMMANDS["stadtteile"].match(text):
        return _districts(bot, uid)
    if COMMANDS["folgen"].match(text):
        return _list_follows(bot, uid)
    if COMMANDS["datenschutz"].match(text):
        return _privacy(bot, uid)
    if COMMANDS["loeschen"].match(text):
        return _erase_ask(bot, uid)
    for key, handler in (
        ("export", _export),
        ("berichtigen", _correct),
        ("pause", _pause),
        ("resume", _resume),
        ("widerspruch", _object_ask),
    ):
        if COMMANDS[key].match(text):
            return handler(bot, uid)
    if not text or text.startswith("/"):
        send(bot, uid, _("Schreiben Sie, was Sie suchen — z. B. „Brot“ oder „Friseur Ohligs“."))
        return "help"
    return _search(bot, uid, {"q": text[:200], "kat": "", "d": ""}, page=0)


def _start(bot, uid) -> str:
    portal = bot.portal
    lines = [
        "👋 " + _("Willkommen bei %(name)s!") % {"name": _clean(portal.title_text)},
        _("Schreiben Sie, was Sie suchen — z. B. „Brot“ oder „Friseur Ohligs“."),
        _("Oder stöbern Sie nach Bereichen und Stadtteilen."),
    ]
    send(bot, uid, "\n".join(lines), _menu(portal))
    return "start"


def _callback(bot, uid, data: str, lang) -> str:
    parsed = parse_callback(data)
    if parsed is None:
        send(bot, uid, _("Diese Schaltfläche ist veraltet."), _menu(bot.portal))
        return "stale"
    head, args = parsed
    if head == "m":
        return _start(bot, uid)
    if head == "sec":
        return _sections(bot, uid)
    if head == "dis":
        return _districts(bot, uid)
    if head == "s":
        state = cache.get(_state_key(bot, uid, args[0]))
        if not state:
            send(bot, uid, _("Diese Schaltfläche ist veraltet."), _menu(bot.portal))
            return "stale"
        return _search(bot, uid, state, page=int(args[1]), token=args[0])
    if head == "k":
        return _search_section(bot, uid, args[0])
    if head == "d":
        return _search_district(bot, uid, args[0])
    if head in ("fb", "fk", "fd", "fq"):
        return _follow_ask(bot, uid, head, args[0], lang)
    if head == "fy":
        return _follow_confirm(bot, uid, args[0], lang)
    if head == "fn":
        send(bot, uid, _("Kein Abo angelegt."))
        return "follow_declined"
    if head == "ls":
        return _list_follows(bot, uid)
    if head == "u":
        return _unfollow(bot, uid, int(args[0]))
    if head == "pd":
        return _erase_callback(bot, uid, args[0])
    if head == "pl":
        return _set_language(bot, uid, args[0])
    if head == "wx":
        return _object_all(bot, uid)
    return "skip"


# --- поиск ---------------------------------------------------------------------------------


def _state_key(bot, uid, token: str) -> str:
    return f"pbot:q:{bot.pk}:{int(uid)}:{token}"


def run_search(portal, state: dict, *, offset: int = 0, track: bool = False):
    """(карточки страницы, есть_ещё) — тот же движок и пул, что страница портала."""
    from . import portal_home_blocks as home
    from . import portal_scope
    from . import search as engine

    city = portal.city or ""
    explicit = engine.SearchFilters(
        kats=(state["kat"],) if state.get("kat") else (),
        district=state.get("d") or "",
    )
    q = state.get("q") or ""
    q_eff, eff, _chips, _hints = engine.resolve_intent(q, explicit, city=city)
    kinds = home.kinds_for(home.default_kind("", q_eff, eff)) or AggregatorListing.OFFER_KINDS
    outcome = engine.execute(
        portal_scope.pool(portal, kinds=kinds),
        q_eff,
        eff,
        surface="telegram",
        track=track,
        city=city,
        portal_host=portal.host,
        log_query=q or None,
    )
    window = list(outcome.qs[offset : offset + PAGE + 1])
    return window[:PAGE], len(window) > PAGE


def _price(item) -> str:
    price = getattr(item, "new_price", None)
    if price is None:
        return ""
    return f"{formats.number_format(price, 2)} €"


def _card(item) -> str:
    from apps.core import districts

    url = item.with_channel("telegram", lang=translation.get_language() or "")
    head = _clean(item.title_text)
    meta = [p for p in (_price(item), _clean(item.price_condition_label, 60)) if p]
    where = _clean(item.business_name, 60)
    district = districts.label(item.city or "", item.district or "") if item.district else ""
    if district:
        where += f" · {district}"
    lines = [f"• {head}" + (f" — {' · '.join(meta)}" if meta else ""), f"  {where}"]
    if url.lower().startswith(("https://", "http://")):
        lines.append(f"  {url}")
    return "\n".join(lines)


def _search(bot, uid, state: dict, *, page: int, token: str | None = None) -> str:
    portal = bot.portal
    if page >= MAX_PAGES:
        send(bot, uid, _("Mehr finden Sie im Portal."), _menu(portal))
        return "max_pages"
    items, more = run_search(portal, state, offset=page * PAGE, track=page == 0)
    token = token or secrets.token_urlsafe(9)
    cache.set(_state_key(bot, uid, token), state, STATE_TTL)
    if not items:
        send(
            bot,
            uid,
            _("Dazu gibt es gerade nichts. Versuchen Sie ein anderes Wort oder einen Bereich."),
            {"inline_keyboard": [*_follow_query_row(token), *_menu(portal)["inline_keyboard"]]},
        )
        return "empty"
    text = "\n\n".join(_card(item) for item in items)
    rows = []
    seen = set()
    for item in items:  # «Folgen» у первых компаний выдачи
        if item.tenant_schema in seen or len(seen) >= 3:
            continue
        seen.add(item.tenant_schema)
        rows.append(
            [{"text": "🔔 " + _clean(item.business_name, 40), "callback_data": f"fb:{item.pk}"}]
        )
    if more:
        rows.append([{"text": "➡️ " + _("Mehr"), "callback_data": f"s:{token}:{page + 1}"}])
    rows += _follow_query_row(token)
    rows.append([{"text": "🏠 " + _("Menü"), "callback_data": "m"}])
    send(bot, uid, text, {"inline_keyboard": rows})
    return "results"


def _follow_query_row(token: str) -> list:
    return [[{"text": "🔔 " + _("Diese Suche folgen"), "callback_data": f"fq:{token}"}]]


def present_sections(portal) -> list[tuple[str, str]]:
    """Разделы, в которых на портале есть предложения (порядок справочника)."""
    from apps.core import city_categories as cc

    from . import portal_scope

    cats = set(
        portal_scope.pool(portal)
        .exclude(city_category="")
        .order_by()
        .values_list("city_category", flat=True)
        .distinct()
    )
    sections = {cc.category(k).section for k in cats if cc.category(k)}
    return [(s.key, str(s.label)) for s in cc.SECTIONS if s.key in sections]


def present_districts(portal) -> list[tuple[str, str]]:
    from apps.core import districts

    from . import portal_scope

    if not portal.city:
        return []
    used = set(
        portal_scope.pool(portal)
        .exclude(district="")
        .order_by()
        .values_list("district", flat=True)
        .distinct()
    )
    return [(slug, name) for slug, name in districts.choices_for(portal.city) if slug in used]


def _sections(bot, uid) -> str:
    choices = present_sections(bot.portal)[:SECTION_BUTTONS]
    if not choices:
        send(bot, uid, _("Dazu gibt es gerade nichts."), _menu(bot.portal))
        return "sections_empty"
    rows = [[{"text": label, "callback_data": f"k:{key}"}] for key, label in choices]
    send(bot, uid, "🗂 " + _("Bereiche"), {"inline_keyboard": rows})
    return "sections"


def _districts(bot, uid) -> str:
    choices = present_districts(bot.portal)
    if not choices:
        send(bot, uid, _("Dazu gibt es gerade nichts."), _menu(bot.portal))
        return "districts_empty"
    rows = [[{"text": name, "callback_data": f"d:{slug}"}] for slug, name in choices]
    send(bot, uid, "📍 " + _("Stadtteile"), {"inline_keyboard": rows})
    return "districts"


def _search_section(bot, uid, key: str) -> str:
    from apps.core import city_categories as cc

    if not cc.section(key):
        send(bot, uid, _("Diese Schaltfläche ist veraltet."))
        return "stale"
    result = _search(bot, uid, {"q": "", "kat": key, "d": ""}, page=0)
    send(
        bot,
        uid,
        _("Neue Angebote aus diesem Bereich hier bekommen?"),
        {"inline_keyboard": [[{"text": "🔔 " + _("Folgen"), "callback_data": f"fk:{key}"}]]},
    )
    return result


def _search_district(bot, uid, slug: str) -> str:
    from apps.core import districts

    if not bot.portal.city or districts.normalize(bot.portal.city, slug) != slug:
        send(bot, uid, _("Diese Schaltfläche ist veraltet."))
        return "stale"
    result = _search(bot, uid, {"q": "", "kat": "", "d": slug}, page=0)
    send(
        bot,
        uid,
        _("Neue Angebote aus diesem Stadtteil hier bekommen?"),
        {"inline_keyboard": [[{"text": "🔔 " + _("Folgen"), "callback_data": f"fd:{slug}"}]]},
    )
    return result


# --- «Folgen» ------------------------------------------------------------------------------


def _ask_key(bot, uid, nonce: str) -> str:
    return f"pbot:fol:{bot.pk}:{int(uid)}:{nonce}"


def _target(bot, uid, head: str, arg: str):
    """Цель подписки из кнопки — только в границах портала. None — недоступно."""
    from apps.core import city_categories as cc
    from apps.core import districts
    from apps.tenants.models import Tenant

    from . import follow, portal_scope

    portal = bot.portal
    city = districts.city_label(portal.city or "") if portal.city else ""
    if head == "fb":
        listing = portal_scope.pool(portal).filter(pk=int(arg)).first()
        if listing is None:
            return None
        return follow.business_target(
            Tenant.objects.filter(schema_name=listing.tenant_schema).first()
        )
    if head == "fk":
        return (
            follow.Target(FollowSubscription.TARGET_SECTION, arg, city)
            if city and cc.section(arg)
            else None
        )
    if head == "fd":
        slug = districts.normalize(portal.city or "", arg) if city else ""
        return (
            follow.Target(FollowSubscription.TARGET_DISTRICT, slug, city) if slug == arg else None
        )
    if head == "fq":
        state = cache.get(_state_key(bot, uid, arg))
        if not state:
            return None
        params = QueryDict(mutable=True)
        for key, value in (
            ("q", state.get("q")),
            ("kat", state.get("kat")),
            ("stadtteil", state.get("d")),
        ):
            if value:
                params[key] = value
        params["art"] = "suche"
        return (
            follow.query_target(params, portal=portal)
            if params.get("q") or len(params) > 1
            else None
        )
    return None


def _target_label(target) -> str:
    try:
        return _clean(target.label, 80)
    except Exception:  # noqa: BLE001
        return ""


def _follow_ask(bot, uid, head: str, arg: str, lang) -> str:
    target = _target(bot, uid, head, arg)
    if target is None:
        send(bot, uid, _("Das kann man hier leider nicht abonnieren."))
        return "follow_unavailable"
    nonce = secrets.token_urlsafe(9)
    payload = {
        "k": target.kind,
        "t": target.key,
        "c": target.city,
        "q": [list(p) for p in target.query],
    }
    cache.set(_ask_key(bot, uid, nonce), payload, ASK_TTL)
    frequency = (
        _("sofort, sobald es etwas Neues gibt")
        if target.kind == FollowSubscription.TARGET_BUSINESS
        else _("einmal täglich")
    )
    text = "\n".join(
        [
            "🔔 " + _("Folgen: %(name)s") % {"name": _target_label(target) or target.kind_label},
            _(
                "Wir schicken Ihnen neue Angebote hier im Chat — %(frequency)s. "
                "Beenden jederzeit mit /folgen."
            )
            % {"frequency": frequency},
        ]
    )
    rows = [
        [{"text": "✅ " + _("Ja, folgen"), "callback_data": f"fy:{nonce}"}],
        [{"text": "❌ " + _("Nein"), "callback_data": "fn"}],
    ]
    send(bot, uid, text, {"inline_keyboard": rows})
    return "follow_asked"


def chat_user(bot, uid, lang="") -> PortalChat:
    """Чат жителя (создаётся при первой подписке) — вместе с `PortalUser` без почты."""
    from django.db import transaction

    from apps.core import ratelimit

    chat = PortalChat.objects.filter(bot=bot, chat_id=int(uid)).select_related("user").first()
    if chat is not None:
        return chat
    if ratelimit.hit("tgportal-new", f"{bot.pk}", limit=NEW_CHATS_PER_HOUR, window=3600):
        raise NewChatsLimited
    with transaction.atomic():
        user = PortalUser.objects.create(email=None, locale=locale_for(lang))
        chat, created = PortalChat.objects.get_or_create(
            bot=bot, chat_id=int(uid), defaults={"user": user, "locale": locale_for(lang)}
        )
        if not created:  # гонка двух нажатий: второй пользователь лишний
            user.delete()
    return chat


def _follow_confirm(bot, uid, nonce: str, lang) -> str:
    from . import follow, follow_query

    key = _ask_key(bot, uid, nonce)
    payload = cache.get(key)
    if not payload or not cache.delete(key):
        send(bot, uid, _("Diese Schaltfläche ist veraltet."))
        return "stale"
    query = tuple(tuple(p) for p in payload.get("q") or ())
    target = follow.Target(payload["k"], payload["t"], payload.get("c", ""), query=query)
    if target.kind == FollowSubscription.TARGET_QUERY and follow_query.key(query) != target.key:
        send(bot, uid, _("Diese Schaltfläche ist veraltet."))
        return "stale"
    try:
        chat = chat_user(bot, uid, lang)
    except NewChatsLimited:
        send(bot, uid, _("Zu viele Anfragen — bitte kurz warten."))
        return "limited"
    frequency = (
        FollowSubscription.FREQ_INSTANT
        if target.kind == FollowSubscription.TARGET_BUSINESS
        else FollowSubscription.FREQ_DAILY
    )
    try:
        follow.follow_now(
            chat.user,
            target,
            frequency=frequency,
            portal=bot.portal,
            source_host=f"tg:@{bot.bot_username}"[:253],
            channel=FollowSubscription.CHANNEL_TELEGRAM,
        )
    except follow.FollowLimitReached:
        send(
            bot, uid, _("Sie haben schon die maximale Zahl an Abos. Beenden Sie eines mit /folgen.")
        )
        return "follow_limit"
    send(bot, uid, "✅ " + _("Abo angelegt. Neue Angebote kommen hier im Chat."), _menu(bot.portal))
    return "followed"


def _list_follows(bot, uid) -> str:
    from . import follow

    chat = PortalChat.objects.filter(bot=bot, chat_id=int(uid)).select_related("user").first()
    subs = follow.user_follows(chat.user) if chat else []
    if not subs:
        send(bot, uid, _("Sie haben noch keine Abos. Suchen Sie etwas und tippen Sie auf 🔔."))
        return "follows_empty"
    rows = [
        [{"text": "✖ " + _clean(follow.describe(sub), 50), "callback_data": f"u:{sub.pk}"}]
        for sub in subs[:20]
    ]
    send(bot, uid, "🔔 " + _("Ihre Abos — tippen zum Beenden:"), {"inline_keyboard": rows})
    return "follows"


def _unfollow(bot, uid, sub_pk: int) -> str:
    from . import follow

    sub = FollowSubscription.objects.filter(
        pk=sub_pk, user__portal_chat__bot=bot, user__portal_chat__chat_id=int(uid)
    ).first()
    if sub is None:
        send(bot, uid, _("Diese Schaltfläche ist veraltet."))
        return "stale"
    label = _clean(follow.describe(sub), 80)
    sub.delete()  # PortalUser с чатом остаётся до /daten_loeschen или срока хранения
    send(bot, uid, _("Abo beendet: %(name)s") % {"name": label})
    return "unfollowed"


# --- приватность --------------------------------------------------------------------------


def _privacy(bot, uid) -> str:
    from . import follow

    chat = PortalChat.objects.filter(bot=bot, chat_id=int(uid)).select_related("user").first()
    count = len(follow.user_follows(chat.user)) if chat else 0
    lines = [
        "🔒 " + _("Datenschutz"),
        _(
            "Suchen speichern wir nicht mit Ihrer Person. Wenn Sie etwas abonnieren, speichern "
            "wir Ihre Telegram-ID, Ihre Sprache und die Abos."
        ),
        _("Gespeicherte Abos: %(count)s") % {"count": count},
        _("Ihre Rechte: /meine_daten, /berichtigen, /pausieren, /widerspruch, /daten_loeschen."),
        _("Mehr: %(url)s") % {"url": _privacy_url()},
    ]
    markup = {"inline_keyboard": [[{"text": "🗑 " + _("Daten löschen"), "callback_data": "pd:ask"}]]}
    send(bot, uid, "\n".join(lines), markup)
    return "privacy"


def _privacy_url() -> str:
    """Datenschutzerklärung живёт на основном домене платформы (у портала своей нет)."""
    from apps.tenants.quickstart import domain_base

    return f"https://{domain_base()}/datenschutz/#telegram-portal"


def _erase_key(bot, uid) -> str:
    return f"pbot:erase:{bot.pk}:{int(uid)}"


def _erase_ask(bot, uid) -> str:
    if not PortalChat.objects.filter(bot=bot, chat_id=int(uid)).exists():
        send(bot, uid, _("Es sind keine Daten mehr gespeichert."))
        return "nothing"
    nonce = secrets.token_urlsafe(9)
    cache.set(_erase_key(bot, uid), nonce, ASK_TTL)
    rows = [
        [{"text": "✅ " + _("Ja, löschen"), "callback_data": f"pd:yes:{nonce}"}],
        [{"text": "❌ " + _("Abbrechen"), "callback_data": "pd:no"}],
    ]
    send(bot, uid, "🗑 " + _("Alle Ihre Daten in diesem Bot löschen?"), {"inline_keyboard": rows})
    return "erase_asked"


def _erase_callback(bot, uid, arg: str) -> str:
    if arg == "ask":
        return _erase_ask(bot, uid)
    if arg == "no":
        cache.delete(_erase_key(bot, uid))
        send(bot, uid, _("Nichts gelöscht."))
        return "erase_cancelled"
    nonce = arg[len("yes:") :]
    expected = cache.get(_erase_key(bot, uid))
    if not expected or nonce != expected or not cache.delete(_erase_key(bot, uid)):
        send(bot, uid, _("Abgelaufen. Bitte /daten_loeschen erneut senden."))
        return "erase_expired"
    return erase(bot, uid)


def erase(bot, uid) -> str:
    """Art. 17: чат, житель, его подписки и сводки (каскадом). Поиск ничего не хранил."""
    chat = PortalChat.objects.filter(bot=bot, chat_id=int(uid)).select_related("user").first()
    if chat is not None:
        chat.user.delete()  # каскадом: PortalChat, FollowSubscription, FollowDigest
    send(bot, uid, "✅ " + _("Gelöscht. Es sind keine Daten mehr gespeichert."))
    return "erased"


# --- права субъекта данных (H-7i) -----------------------------------------------------------

EXPORT_LIMIT = 3  # выгрузок в сутки


def _own_chat(bot, uid):
    return PortalChat.objects.filter(bot=bot, chat_id=int(uid)).select_related("user").first()


def export_data(bot, uid) -> dict:
    from . import follow

    chat = _own_chat(bot, uid)
    if chat is None:
        return {"telegram_user_id": int(uid), "stored": False}
    return {
        "controller": _clean(bot.portal.title_text),
        "telegram_user_id": int(uid),
        "language": chat.locale,
        "email": chat.user.email or None,
        "created_at": chat.created_at.isoformat() if chat.created_at else None,
        "last_seen_at": chat.last_seen_at.isoformat() if chat.last_seen_at else None,
        "paused_at": chat.paused_at.isoformat() if chat.paused_at else None,
        "subscriptions": [
            {
                "what": _target_label_sub(sub),
                "frequency": sub.frequency,
                "confirmed_at": sub.confirmed_at.isoformat() if sub.confirmed_at else None,
            }
            for sub in follow.user_follows(chat.user)
        ],
        "exported_at": timezone.now().isoformat(),
    }


def _target_label_sub(sub) -> str:
    from . import follow

    try:
        return _target_label(follow.target_from_follow(sub)) or sub.target_kind
    except Exception:  # noqa: BLE001 — выгрузка не падает из-за одной подписки
        return sub.target_kind


def _export(bot, uid) -> str:
    import json

    from apps.core import ratelimit
    from apps.telegram import services

    if ratelimit.hit("tgportal-export", f"{bot.pk}:{int(uid)}", limit=EXPORT_LIMIT, window=86400):
        send(bot, uid, _("Zu viele Anfragen — bitte kurz warten."))
        return "limited"
    data = export_data(bot, uid)
    if not data.get("subscriptions") and data.get("stored") is False:
        send(bot, uid, _("Es sind keine Daten mehr gespeichert."))
        return "nothing"
    count = len(data.get("subscriptions") or [])
    send(
        bot,
        uid,
        "\n".join(
            [
                "📄 " + _("Ihre Daten in diesem Bot"),
                _("Gespeicherte Abos: %(count)s") % {"count": count},
                _("Die Datei unten wird von Telegram gespeichert, solange Sie den Chat behalten."),
            ]
        ),
    )
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    try:
        services.send_document(bot.token, uid, "meine-daten.json", payload)
    except Exception as exc:  # noqa: BLE001 — текст ошибки несёт URL с токеном
        logger.warning("portal bot export failed: %s", type(exc).__name__)
        send(bot, uid, _("Die Datei konnte nicht gesendet werden. Bitte später erneut."))
        return "export_failed"
    return "exported"


def _correct(bot, uid) -> str:
    from django.conf import settings

    langs = list(getattr(settings, "CABINET_LANGUAGES", ()) or ["de"])
    rows = [[{"text": code.upper(), "callback_data": f"pl:{code}"} for code in langs]]
    send(
        bot,
        uid,
        "\n".join(
            [
                "✏️ " + _("Daten berichtigen"),
                _("Sprache der Nachrichten wählen. Abos ändern oder beenden: /folgen"),
            ]
        ),
        {"inline_keyboard": rows},
    )
    return "correct_menu"


def _set_language(bot, uid, code: str) -> str:
    from django.conf import settings

    if code not in getattr(settings, "CABINET_LANGUAGES", ()):
        return "skip"
    updated = PortalChat.objects.filter(bot=bot, chat_id=int(uid)).update(
        locale=code, locale_chosen_at=timezone.now()
    )
    if updated:
        PortalUser.objects.filter(portal_chat__bot=bot, portal_chat__chat_id=int(uid)).update(
            locale=code
        )
    with translation.override(code):
        if not updated:
            send(bot, uid, _("Ohne Abo speichere ich nichts — die Sprache folgt Telegram."))
            return "nothing"
        send(bot, uid, "✅ " + _("Sprache gespeichert."))
    return "locale_set"


def _pause(bot, uid) -> str:
    updated = PortalChat.objects.filter(bot=bot, chat_id=int(uid)).update(paused_at=timezone.now())
    if not updated:
        send(bot, uid, _("Es sind keine Daten mehr gespeichert."))
        return "nothing"
    send(
        bot,
        uid,
        "⏸ "
        + _(
            "Zusammenfassungen in Telegram pausiert. Ihre Abos bleiben gespeichert. "
            "Weiter: /fortsetzen"
        ),
    )
    return "paused"


def _resume(bot, uid) -> str:
    PortalChat.objects.filter(bot=bot, chat_id=int(uid)).update(paused_at=None)
    send(bot, uid, "▶ " + _("Zusammenfassungen laufen wieder."))
    return "resumed"


def _object_ask(bot, uid) -> str:
    rows = [[{"text": "✋ " + _("Alle Abos beenden"), "callback_data": "wx"}]]
    send(
        bot,
        uid,
        "\n".join(
            [
                "✋ " + _("Widerspruch"),
                _(
                    "Ich beende alle Abos in Telegram — Sie bekommen hier keine Nachrichten "
                    "mehr. Alle Daten löschen: /daten_loeschen"
                ),
            ]
        ),
        {"inline_keyboard": rows},
    )
    return "objection_asked"


def _object_all(bot, uid) -> str:
    from .models import FollowSubscription

    chat = _own_chat(bot, uid)
    # Только подписки ЭТОГО канала: подписки сайта (e-mail) отменяются ссылкой в письме.
    count = (
        FollowSubscription.objects.filter(
            user=chat.user, channel=FollowSubscription.CHANNEL_TELEGRAM
        ).delete()[0]
        if chat
        else 0
    )
    send(bot, uid, "✅ " + _("Alle Abos beendet (%(count)s).") % {"count": count})
    return "objected"


# --- команды бота ----------------------------------------------------------------------------


def commands() -> list[dict]:
    return [
        {"command": "bereiche", "description": _("Angebote nach Bereichen")},
        {"command": "stadtteile", "description": _("Angebote nach Stadtteilen")},
        {"command": "folgen", "description": _("Meine Abos")},
        {"command": "datenschutz", "description": _("Was wir speichern")},
        {"command": "meine_daten", "description": _("Meine Daten anzeigen")},
        {"command": "pausieren", "description": _("Zusammenfassungen pausieren")},
        {"command": "daten_loeschen", "description": _("Meine Daten löschen")},
    ]


# --- сроки хранения -----------------------------------------------------------------------

BLOCKED_KEEP_DAYS = 30
IDLE_KEEP_DAYS = 180


def purge_chats(now=None) -> int:
    """Житель заблокировал бота > 30 дней или 180 дней без подписок и активности — удалить
    (вместе с ним каскадом уходят подписки и сводки)."""
    from datetime import timedelta

    from django.db.models import Q

    now = now or timezone.now()
    stale = PortalChat.objects.filter(user__email__isnull=True).filter(
        Q(blocked_at__lt=now - timedelta(days=BLOCKED_KEEP_DAYS))
        | Q(user__follows__isnull=True)
        & Q(created_at__lt=now - timedelta(days=IDLE_KEEP_DAYS))
        & (Q(last_seen_at__isnull=True) | Q(last_seen_at__lt=now - timedelta(days=IDLE_KEEP_DAYS)))
    )
    # Партия 5000 за проход; остаток — следующий суточный прогон.
    user_ids = list(stale.values_list("user_id", flat=True).distinct()[:5000])
    PortalUser.objects.filter(pk__in=user_ids, email__isnull=True).delete()
    return len(user_ids)
