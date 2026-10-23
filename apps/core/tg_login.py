"""T-8.30: вход в «Mein Laden» из Telegram Mini App — сессия ТОЛЬКО в лёгкие экраны.

План — docs/t8-30-miniapp-plan-2026-10-20.md §1.4–1.5 (решения владельца Р-2/Р-3/Р-5).

- Одноразовый токен передачи (Redis ``tg_login:<schema>:<sha256>``, 60 с) выпускает
  страница Mini App на публичном хосте после проверки подписи Telegram. Внутри — ``user_pk``
  и Telegram-id, не e-mail: токен входа по почте и этот не принимаются друг за друга.
- ``/tg/start/<token>/``: GET показывает автосабмит-форму (не расходует), POST расходует,
  ещё раз проверяет владельца и связь, логинит и ПОСЛЕ логина ставит флаг сессии
  ``tg_lite = {uid, exp}`` (12 ч, абсолютный срок).
- Любой другой вход (e-mail, пароль) снимает флаг — полный доступ даёт только он.
- Граница доступа — ``TelegramLiteScopeMiddleware``: разрешено только ``TG_LITE_VIEWS``.
"""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
import time

from django.contrib.auth import get_user_model
from django.contrib.auth import login as auth_login
from django.contrib.auth.signals import user_logged_in
from django.core.cache import cache
from django.db import connection
from django.http import Http404
from django.shortcuts import redirect, render

from apps.core import ratelimit
from apps.core.models import Membership

logger = logging.getLogger(__name__)

SESSION_KEY = "tg_lite"
TTL = 60
SESSION_TTL = 12 * 3600  # Р-3
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{30,60}$")

# Р-2: лёгкие экраны и то, что они вызывают. Всё остальное в кабинете — страница
# «в Telegram недоступно» (вход по e-mail). Q1 плана: полные формы акции и товара входят —
# на них ведут «Bearbeiten» и «Fotos ergänzen». Денег, команды, права, настроек,
# интеграций, своего бота, доменов, импорта и Studio здесь нет и быть не должно.
TG_LITE_VIEWS = frozenset(
    {
        # Start / Geschäft / Teilen / Sichtbar + служебное
        "dashboard",
        "lite-business",
        "lite-share",
        "lite-visibility",
        "lite-requests",  # KA-12 E8.9: заявки списком (карточка со сметой — вне Telegram)
        "owner-confirm-resend",
        "set-cabinet-lang",
        "account_logout",
        "tg-start",
        "tg-lite-info",
        # Angebot
        "sellable-manage",
        "sellable-visibility",
        "sellable-sold-out",  # KA-12 E3.4
        "sortiment-view",
        "catalog:product-create",
        "catalog:product-edit",
        "catalog:product-image-delete",
        "catalog:product-image-primary",
        "catalog:product-delete",
        # подформы карточки товара (Q1: полная форма) — варианты и опции
        "catalog:variant-add",
        "catalog:variant-update",
        "catalog:variant-delete",
        "catalog:modifier-group-add",
        "catalog:modifier-group-update",
        "catalog:modifier-group-delete",
        "catalog:modifier-option-add",
        "catalog:modifier-option-update",
        "catalog:modifier-option-delete",
        # Aktionen
        "promotions:promotion-list",
        "promotions:promotion-quick",
        "promotions:promotion-quick-done",
        "promotions:promotion-preview",
        "promotions:promotion-flyer",
        "promotions:promotion-transition",
        "promotions:promotion-create",
        "promotions:promotion-edit",
        "promotions:promotion-image-delete",
        "promotions:promotion-image-primary",
        "promotions:promotion-text-check",
        "promotions:promotion-text-check-ai",
        "promotions:promotion-text-check-ai-result",
        "promotions:promotion-quick-ai",
        "promotions:promotion-quick-ai-result",
        "promotions:today-dismiss",
        "promotions:shop-poster",
        # T-8.30e: касса — отложенное и погашение кода у прилавка (Q2)
        "promotions:reservation-list",
        "promotions:reservation-action",
        "promotions:redeem",
        "promotions:redeem-detail",
        "promotions:redeem-action",
        "promotions:voucher-redeem",  # QR ваучера/подарочного сертификата у прилавка
        # T-8.32b: «Nachrichten» лёгкого кабинета (пакет «Aktionen» и Mini App)
        "inbox:list",
        "inbox:thread",
        "inbox:thread-poll",
        "inbox:thread-typing",
        "inbox:unread-count",
        "inbox:reply-draft",
        "inbox:reply-draft-result",
    }
)


def _key(schema: str, token: str) -> str:
    return f"tg_login:{schema}:{hashlib.sha256(token.encode()).hexdigest()}"


def issue(schema: str, user_pk: int, uid: int, *, lang: str = "", grace: str = "") -> str:
    """``grace`` — отпечаток initData: сессия, открытая этим токеном, гасится повтором."""
    token = secrets.token_urlsafe(32)
    payload = {"user_pk": int(user_pk), "uid": int(uid), "lang": lang, "grace": grace}
    cache.set(_key(schema, token), payload, TTL)
    return token


def _valid(token) -> bool:
    return isinstance(token, str) and bool(_TOKEN_RE.match(token))


def peek(schema: str, token: str) -> dict | None:
    return cache.get(_key(schema, token)) if _valid(token) else None


def consume(schema: str, token: str) -> dict | None:
    """Атомарно: забирает только тот, кто удалил ключ (второй параллельный POST — None)."""
    if not _valid(token):
        return None
    key = _key(schema, token)
    payload = cache.get(key)
    if payload is None or not cache.delete(key):
        return None
    return payload


def owner_user(user_pk):
    """Активный пользователь с ролью владельца в ТЕКУЩЕЙ схеме или None."""
    if not user_pk:
        return None
    if not Membership.objects.filter(
        user_id=user_pk, user__is_active=True, role=Membership.ROLE_OWNER
    ).exists():
        return None
    return get_user_model().objects.filter(pk=user_pk, is_active=True).first()


def telegram_allowed(uid, tenant, user_pk=None) -> bool:
    """Связь с общим ботом жива и обработка не ограничена (Art. 18).

    T-8.30f: с ``user_pk`` — связь ещё и закреплена за этим пользователем кабинета (или за
    никем — легаси): перепривязали к другому — сессия прежнего заканчивается."""
    from django.db.models import Q

    from apps.platform_bot import links, rights

    if rights.is_restricted(uid):
        return False
    qs = links._active(uid).filter(tenant=tenant)  # is_owner — тем же запросом
    if user_pk is not None:
        qs = qs.filter(Q(user_pk__isnull=True) | Q(user_pk=user_pk))
    return qs.exists()


_SESS_PREFIX = "tgapp:sess:"
_SESS_TTL = 360  # окно повтора initData (MAX_AGE 300 + запас)


def remember_session(grace: str, session_key) -> None:
    """Сессия, открытая по этой initData: повторный вход её гасит (ревью T-8.30f)."""
    if not grace or not session_key:
        return
    key = _SESS_PREFIX + grace
    keys = [k for k in (cache.get(key) or []) if k != session_key][-4:]
    cache.set(key, [*keys, session_key], _SESS_TTL)


def revoke_sessions(grace: str) -> None:
    from importlib import import_module

    from django.conf import settings

    if not grace:
        return
    store = import_module(settings.SESSION_ENGINE).SessionStore
    for session_key in cache.get(_SESS_PREFIX + grace) or []:
        store(session_key).delete()
    cache.delete(_SESS_PREFIX + grace)


def _clamp_lang(lang: str) -> str:
    from apps.core.i18n_cabinet import cabinet_language_codes

    lang = (lang or "").split("-")[0].lower()
    return lang if lang in cabinet_language_codes() else ""


def tg_start(request, token):
    # Схема бизнеса этого хоста (её же ставит TenantMainMiddleware в соединение).
    schema = getattr(getattr(request, "tenant", None), "schema_name", connection.schema_name)
    if request.method == "POST":
        if ratelimit.hit("tg-start", ratelimit.client_ip(request), limit=30, window=3600):
            raise Http404
        payload = consume(schema, token)
        user = owner_user(payload.get("user_pk")) if payload else None
        if user is None or not telegram_allowed(payload["uid"], request.tenant, user.pk):
            raise Http404
        auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        # ПОСЛЕ логина: приёмник user_logged_in снимает флаг при любом входе.
        request.session[SESSION_KEY] = {
            "uid": payload["uid"],
            "exp": int(time.time()) + SESSION_TTL,
        }
        request.session.set_expiry(SESSION_TTL)
        if payload.get("grace"):
            request.session.save()  # ключ сессии нужен сейчас — повтор initData её гасит
            remember_session(payload["grace"], request.session.session_key)
        lang = _clamp_lang(payload.get("lang", ""))
        if lang:
            from apps.core.i18n_cabinet import SESSION_KEY as LANG_KEY

            request.session[LANG_KEY] = lang
        return redirect("dashboard")
    if peek(schema, token) is None:
        return render(request, "account/tg_start.html", {"invalid": True}, status=404)
    return render(request, "account/tg_start.html", {})


def tg_lite_info(request):
    """Экран в Telegram недоступен / сессия закончилась — объяснение + вход по e-mail."""
    from django.utils import translation

    from apps.core.i18n_cabinet import resolve_cabinet_locale

    reason = request.GET.get("grund", "")
    # Путь не кабинетный — язык кабинета (из сессии/Accept-Language) включаем сами.
    with translation.override(resolve_cabinet_locale(request)):
        return render(
            request,
            "account/tg_lite_info.html",
            {"reason": reason if reason in ("abgelaufen", "beendet") else ""},
        )


def drop_flag_on_login(sender, request, user, **kwargs):
    """Любой вход снимает ограничение (e-mail-вход в том же окне = полный кабинет);
    `tg_start` ставит флаг заново уже после своего входа."""
    session = getattr(request, "session", None)
    if session is not None and session.pop(SESSION_KEY, None):
        session.set_expiry(None)  # 12 ч Telegram-сессии к e-mail-входу не относятся


def connect():
    user_logged_in.connect(drop_flag_on_login, dispatch_uid="core.tg_login.drop_flag")


def is_tg_session(request) -> bool:
    from django.conf import settings

    # Без куки сессии не трогаем: иначе каждый анонимный запрос читал бы сессию.
    if not (getattr(request, "COOKIES", None) or {}).get(settings.SESSION_COOKIE_NAME):
        return False
    session = getattr(request, "session", None)
    return bool(session is not None and session.get(SESSION_KEY))
