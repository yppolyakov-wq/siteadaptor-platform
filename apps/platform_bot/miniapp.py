"""T-8.30: Telegram Mini App «Mein Laden» — вход на публичном хосте.

План — docs/t8-30-miniapp-plan-2026-10-20.md §1.1–1.3. Страница ``/tg/app/`` берёт у
Telegram подписанный ``initData`` и шлёт его сюда; сервер проверяет подпись
(``webapp_auth.verify``), находит бизнесы этого Telegram-пользователя через связи общего
бота, владельца в схеме бизнеса и отдаёт одноразовую ссылку входа на поддомен
(``core.tg_login``). Сессии на публичном хосте не создаём.

``csrf_exempt`` осознанно: в Telegram Web страница живёт во фрейме чужого сайта, кука
CSRF туда не уходит. Аутентификация запроса — подпись Telegram (или серверный билет
выбора); сверху — проверка Origin, тип и размер тела, лимиты частоты.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
from urllib.parse import urlsplit

from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.core import ratelimit

from . import webapp_auth

logger = logging.getLogger(__name__)

TENANT_URLCONF = "config.urls_tenant"
TICKET_TTL = 120
# T-8.30f: повторное открытие той же страницы (перезагрузка, потерянный ответ) — до трёх
# входов на одну initData, только с того же IP; живым остаётся последний токен/билет.
GRACE_MAX = 3
GRACE_PREFIX = "tgapp:grace:"
MAX_LINKS = 20
FRAME_ANCESTORS = "frame-ancestors https://web.telegram.org"


_EXPIRED_MSG = gettext_lazy(
    "Sitzung abgelaufen — bitte schließen und „Mein Laden“ im Bot neu öffnen."
)


def _json(data: dict, status: int = 200):
    resp = JsonResponse(data, status=status)
    resp["Cache-Control"] = "no-store"
    return resp


def _error(code: str, message: str, status: int = 200, **extra):
    return _json({"error": code, "message": message, **extra}, status=status)


# --- сопоставление «Telegram → бизнес → владелец» -------------------------------------


def _owner_pk(tenant, link=None):
    """Владелец в схеме бизнеса — пользователь, закреплённый в самой связи (T-8.30f), и
    только пока он ещё владелец. Без него — единственный активный владелец, и только для
    связи из регистрации в боте (H-5: владельца создал сам бот). Связь из кабинета без
    пользователя — не угадываем (иначе чат бывшего владельца вошёл бы под новым)."""
    from apps.core import tg_login
    from apps.core.models import Membership

    pk = getattr(link, "user_pk", None)
    if not pk and link is not None and link.via != link.VIA_SIGNUP:
        # Легаси-связь кабинета без user_pk (бэкфилл её не взял) — тот же фолбэк на
        # зеркало, что в links.still_owner (убрать вместе с ним через релиз).
        cfg = getattr(tenant, "site_config", None)
        node = cfg.get("notify") if isinstance(cfg, dict) else None
        mirror = node.get("owner_user_pk") if isinstance(node, dict) else None
        pk = mirror if isinstance(mirror, int) and not isinstance(mirror, bool) else None
    if pk:
        return pk if tg_login.owner_user(pk) is not None else None
    if link is None or link.via != link.VIA_SIGNUP:
        return None
    owners = list(
        Membership.objects.filter(role=Membership.ROLE_OWNER, user__is_active=True).values_list(
            "user_id", flat=True
        )[:2]
    )
    return owners[0] if len(owners) == 1 else None


def handoff(link, uid: int, lang: str, issued: list | None = None, grace: str = ""):
    """→ ``{"next": url}`` или отказ с входом по e-mail. ``issued`` — сюда кладём ключ
    выпущенного токена (повтор гасит прежний)."""
    from django_tenants.utils import schema_context

    from apps.core import owner_login, tg_login

    from . import links

    tenant = link.tenant
    base = owner_login.tenant_url(tenant)
    with schema_context(tenant.schema_name):
        user_pk = _owner_pk(tenant, link)
        if user_pk is None or not links.still_owner(tenant):
            login = base + reverse("owner-login-link", urlconf=TENANT_URLCONF)
            return _error(
                "no_owner",
                _("Bitte melden Sie sich für dieses Geschäft per E-Mail an."),
                login_url=login,
            )
        token = tg_login.issue(tenant.schema_name, user_pk, uid, lang=lang, grace=grace)
        if issued is not None:
            issued.append(tg_login._key(tenant.schema_name, token))
    return _json({"next": base + reverse("tg-start", args=[token], urlconf=TENANT_URLCONF)})


def _ready_links(uid: int) -> list:
    from apps.tenants.models import Tenant

    from . import links

    return [
        link
        for link in links.active_links(uid)[:MAX_LINKS]
        if link.tenant.provisioning_status == Tenant.PROVISIONING_READY
    ]


def _lang(uid: int, init_lang: str) -> str:
    from . import rights

    return rights.preferred_locale(uid) or (init_lang or "")


def resolve(uid: int, init_lang: str = "", issued: list | None = None, grace: str = ""):
    from . import rights

    if rights.is_restricted(uid):
        return _error(
            "restricted",
            _("Die Verarbeitung ist eingeschränkt. Mit /freigeben im Bot wieder aufheben."),
        )
    found = _ready_links(uid)
    lang = _lang(uid, init_lang)
    if not found:
        return _first_run(uid)
    if len(found) == 1:
        return handoff(found[0], uid, lang, issued, grace)
    raw = secrets.token_urlsafe(24)
    if issued is not None:
        issued.append(_ticket_key(raw))
    cache.set(
        _ticket_key(raw),
        {"uid": uid, "links": [str(link.pk) for link in found], "lang": lang},
        TICKET_TTL,
    )
    return _json(
        {
            "choose": [{"id": str(link.pk), "name": link.tenant.name} for link in found],
            "ticket": raw,
        }
    )


def _first_run(uid: int):
    """T-8.30h: без готового бизнеса — не тупик. Регистрация идёт (почта не подтверждена
    или бизнес ещё создаётся) → `pending`; иначе `unlinked` с ботом и (T-8.30i)
    регистрацией в том же окне (`app_signup`) — «Neues Geschäft anlegen» /
    «Ich habe schon ein Geschäft»."""
    from . import config, links, signup, web_signup

    bot = config.username()
    from apps.tenants.models import Tenant

    creating = links.active_links(uid).filter(
        tenant__provisioning_status=Tenant.PROVISIONING_PENDING
    )
    if creating.exists() or signup.cache.get(signup._pending_key(uid)):
        return _error(
            "pending", _("Ihr Geschäft wird gerade angelegt — einen Moment bitte."), bot=bot
        )
    if links.pending_for(uid).exists():
        return _error(
            "pending",
            _("Bitte bestätigen Sie zuerst Ihre E-Mail — danach öffnet sich „Mein Laden“."),
            bot=bot,
        )
    from apps.tenants.quickstart import domain_base

    return _error(
        "unlinked",
        _("Noch kein Geschäft mit diesem Telegram verbunden."),
        bot=bot,
        signup=web_signup.allowed(uid),
        web_url=f"https://{domain_base()}/aktion-starten/",
    )


def _ticket_key(raw: str) -> str:
    return "tgapp:ticket:" + hashlib.sha256(raw.encode()).hexdigest()


def _take_ticket(raw: str):
    if not raw or len(raw) > 100:
        return None
    key = _ticket_key(raw)
    payload = cache.get(key)
    if payload is None or not cache.delete(key):
        return None
    return payload


# --- запрос ------------------------------------------------------------------------------


def _bad_request(request):
    """Origin (если есть) — только этот же хост; тело — форма, не больше 4 КБ."""
    origin = request.headers.get("Origin")
    if origin and urlsplit(origin).netloc != request.get_host():
        return _error("origin", "", status=403)
    ctype = (request.content_type or "").lower()
    if ctype != "application/x-www-form-urlencoded":
        return _error("content_type", "", status=415)
    try:
        size = int(request.headers.get("Content-Length") or 0)
    except ValueError:
        size = 0
    if size > webapp_auth.MAX_BYTES + 512:
        return _error("too_large", "", status=413)
    return None


def _bot_missing():
    from apps.telegram import bots

    return bots.platform_bot() is None


def _limited(request) -> bool:
    return ratelimit.hit("tgapp-ip", ratelimit.client_ip(request), limit=30, window=600)


@require_GET
@xframe_options_exempt
def app_entry(request):
    from . import config

    resp = render(
        request,
        "platform_bot/miniapp.html",
        {
            "auth_url": reverse("tg-app-auth"),
            "choose_url": reverse("tg-app-choose"),
            "signup_url": reverse("tg-app-signup"),
            "bot_username": config.username(),
        },
    )
    resp["Content-Security-Policy"] = FRAME_ANCESTORS
    resp["Cache-Control"] = "no-store"
    return resp


def _with_locale(init_lang: str, fn):
    """Сообщения отказа — на языке пользователя Telegram (если он в реестре кабинета)."""
    from apps.core.i18n_cabinet import cabinet_language_codes

    lang = (init_lang or "").split("-")[0].lower()
    if lang not in cabinet_language_codes():
        return fn()
    with translation.override(lang):
        return fn()


@csrf_exempt
@require_POST
def app_auth(request):
    from apps.core import tg_login

    from . import config

    bad = _bad_request(request)
    if bad is not None:
        return bad
    if _limited(request):
        return _error("rate", _("Zu viele Versuche. Bitte gleich noch einmal."), status=429)
    if _bot_missing():
        return _error("bot_off", _("Der Bot ist gerade nicht verfügbar."), status=503)
    try:
        data = webapp_auth.verify(
            request.POST.get("init_data", ""),
            config.token(),
            now=int(time.time()),
            allow_replay=True,
        )
    except webapp_auth.InitDataError as exc:
        logger.info("tg mini app: init data rejected (%s)", exc.code)  # только код
        if exc.code == "expired":
            return _error(exc.code, _EXPIRED_MSG, status=403)
        return _error(exc.code, _("Bitte öffnen Sie „Mein Laden“ im Bot erneut."), status=403)
    uid = data["uid"]
    if ratelimit.hit("tgapp-uid", str(uid), limit=10, window=600):
        return _error("rate", _("Zu viele Versuche. Bitte gleich noch einmal."), status=429)
    digest = data["digest"]
    grace_key = GRACE_PREFIX + digest
    ttl = webapp_auth.MAX_AGE + 60
    ip = hashlib.sha256(ratelimit.client_ip(request).encode()).hexdigest()
    lock = grace_key + ":lock"
    if not cache.add(lock, 1, 15):
        # Параллельный повтор той же initData: иначе оба выпустили бы живой токен.
        return _error("busy", _("Zu viele Versuche. Bitte gleich noch einmal."), status=409)
    try:
        if data["replay"]:
            # Повтор допускаем только с того же IP и не больше GRACE_MAX раз; решение
            # (связь, Art. 18, владелец) принимается заново — не из кэша.
            grace = cache.get(grace_key)
            if not isinstance(grace, dict) or grace.get("ip") != ip:
                return _error(
                    "replay", _("Bitte öffnen Sie „Mein Laden“ im Bot erneut."), status=403
                )
            try:
                n = cache.incr(grace_key + ":n")
            except ValueError:
                n = GRACE_MAX + 1
            if n > GRACE_MAX:
                return _error(
                    "replay", _("Bitte öffnen Sie „Mein Laden“ im Bot erneut."), status=403
                )
            for key in grace.get("last") or []:
                cache.delete(key)  # живой токен/билет на одну initData — всегда один
            # …и уже открытая по ней сессия (перехвативший initData не сохраняет вход).
            tg_login.revoke_sessions(digest)
        else:
            cache.set(grace_key + ":n", 1, ttl)
            grace = {"ip": ip, "last": []}
            cache.set(grace_key, grace, ttl)  # до resolve: ранний повтор видит grace
        issued: list = []
        resp = _with_locale(
            data["language_code"], lambda: resolve(uid, data["language_code"], issued, digest)
        )
        grace["last"] = issued
        cache.set(grace_key, grace, ttl)
        return resp
    finally:
        cache.delete(lock)


@csrf_exempt
@require_POST
def app_choose(request):
    from . import links

    bad = _bad_request(request)
    if bad is not None:
        return bad
    if _limited(request):
        return _error("rate", _("Zu viele Versuche. Bitte gleich noch einmal."), status=429)
    ticket = _take_ticket(request.POST.get("ticket", ""))
    link_id = request.POST.get("link", "")
    if ticket is None or link_id not in ticket.get("links", []):
        return _error("ticket", _("Bitte öffnen Sie „Mein Laden“ im Bot erneut."), status=403)
    uid = int(ticket["uid"])
    link = links.select(uid, link_id)
    if link is None:
        return _error("ticket", _("Bitte öffnen Sie „Mein Laden“ im Bot erneut."), status=403)
    return _with_locale(ticket.get("lang", ""), lambda: handoff(link, uid, ticket.get("lang", "")))


@csrf_exempt
@require_POST
def app_signup(request):
    """T-8.30i: «Neues Geschäft anlegen» — метка Telegram в сессии этого браузера.

    Ссылки нет: запрос шлёт сама страница Mini App (тот же адрес — проверка Origin, свой
    заголовок — чужой сайт его без CORS не пошлёт), подписью Telegram. Чужой бизнес к
    своему Telegram так не привязать: метка ложится в сессию ТОГО, кто открыл Mini App.
    """
    from . import config, web_signup

    bad = _bad_request(request)
    if bad is not None:
        return bad
    if request.headers.get("X-TG-App") != "1":
        return _error("origin", "", status=403)
    if _limited(request):
        return _error("rate", _("Zu viele Versuche. Bitte gleich noch einmal."), status=429)
    if _bot_missing():
        return _error("bot_off", _("Der Bot ist gerade nicht verfügbar."), status=503)
    try:
        data = webapp_auth.verify(
            request.POST.get("init_data", ""),
            config.token(),
            now=int(time.time()),
            allow_replay=True,  # та же initData уже прошла app_auth
        )
    except webapp_auth.InitDataError as exc:
        logger.info("tg mini app signup: init data rejected (%s)", exc.code)
        return _error(exc.code, _("Bitte öffnen Sie „Mein Laden“ im Bot erneut."), status=403)
    uid = data["uid"]
    if not web_signup.allowed(uid):
        return _error("signup_closed", "", status=403)
    web_signup.remember(request, uid=uid, lang=data["language_code"], name=data.get("name", ""))
    resp = _json({"next": "/aktion-starten/"})
    resp["Cache-Control"] = "no-store"
    return resp
