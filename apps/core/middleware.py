"""Гейтинг модулей кабинета (Track D / D0a): неактивный модуль → 404.

Зеркало apps.billing.middleware.SubscriptionGatingMiddleware, но по реестру
apps.core.modules: путь матчится на модуль по самому длинному url-префиксу;
если модуль для тенанта неактивен (выключен владельцем / не входит в тариф) —
404, как будто раздела нет. Core-модули активны всегда. Публичную витрину,
public-схему и пути вне реестра не трогаем.
"""

from django.http import Http404, HttpResponseForbidden
from django.utils.cache import patch_vary_headers
from django.utils.translation import gettext as _

from . import modules
from .i18n_cabinet import CABINET_PREFIXES, resolve_cabinet_locale
from .roles import (
    OWNER_FLOOR_PREFIXES,
    has_cabinet_access,
    is_owner,
)
from .session_schema import SESSION_SCHEMA_KEY


class SessionSchemaGuardMiddleware:
    """HIGH-10: сбросить сессию, пришедшую на схему ≠ схеме её логина.

    Django-сессия штампуется схемой на логине (apps.core.session_schema). Если
    кука пришла на другую схему (например при ошибочно расширенном
    SESSION_COOKIE_DOMAIN), `_auth_user_id` совпал бы с чужим владельцем
    (pk-коллизия auth_user) — поэтому разлогиниваем. Легаси-сессии без штампа не
    трогаем (host-only cookie их и так изолирует; штамп появится при след. логине).
    Должен стоять ПОСЛЕ AuthenticationMiddleware (нужен request.user/сессия).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            from django.db import connection

            stamped = request.session.get(SESSION_SCHEMA_KEY)
            if stamped is not None and stamped != connection.schema_name:
                from django.contrib.auth import logout

                logout(request)  # сессия из другой схемы → сброс (далее @login_required)
        return self.get_response(request)


class PendingStorefrontMiddleware:
    """KA-D4 (решение владельца 2026-10-23): витрина бизнеса с неподтверждённой почтой
    (`Tenant.email_pending`, быстрая регистрация / бот) посетителям не показывается —
    503 «bald online» + noindex. Пропускаем: кабинет, вход по ссылке, Mini App и
    вебхуки Telegram, служебные пути, любые POST (вебхуки платёжки), и самого владельца
    / сотрудника (превью своей витрины). Каталог города такие бизнесы и так скрывает
    (`aggregator.visibility`)."""

    OPEN_PREFIXES = (
        *CABINET_PREFIXES,
        "/accounts/",
        "/anmelden/",
        "/start/",
        "/tg/",
        "/health",
        "/media/",
        "/static/",
        "/robots.txt",
        "/lang/",
        "/stays/ical/",  # календарь для OTA-каналов (не фид цен — тот скрыт)
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant = getattr(request, "tenant", None)
        if (
            tenant is None
            or getattr(tenant, "schema_name", "public") == "public"
            or not getattr(tenant, "email_pending", False)
            or request.method not in ("GET", "HEAD")
            or request.path.startswith(self.OPEN_PREFIXES)
            or has_cabinet_access(getattr(request, "user", None))
        ):
            return self.get_response(request)
        from django.shortcuts import render

        response = render(request, "storefront/coming_soon.html", status=503)
        response["X-Robots-Tag"] = "noindex, nofollow"
        response["Retry-After"] = "3600"
        return response


class StorefrontLocaleClampMiddleware:
    """SF-1.8: кламп языка ВИТРИНЫ к локалям тенанта.

    LocaleMiddleware негоциирует по ВСЕМУ settings.LANGUAGES: браузер с pl/fr/…
    (в реестре есть, у тенанта не включён, каталога locale/ нет) получал витрину
    из сырых msgid — гарантированный языковой салат; Accept-Language: en давал
    английскую витрину немецкому бизнесу, включившему только de. Правило: язык
    вне `tenant.active_locales` → `default_locale` тенанта. Явный выбор
    посетителя (cookie переключателя, L1 валидирует по active_locales) в
    список входит и клампом не трогается. Кабинет-пути правит
    CabinetLocaleMiddleware (стоит следом), public-схема (платформа/порталы) —
    не наша: не трогаем.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant = getattr(request, "tenant", None)
        if (
            tenant is not None
            and getattr(tenant, "schema_name", "public") != "public"
            and not request.path.startswith(CABINET_PREFIXES)
        ):
            from django.utils import translation

            allowed = list(getattr(tenant, "active_locales", None) or [])
            # Блок Б4: язык, переданный порталом города (`?hl=`), — только из включённых
            # у бизнеса; запоминаем его кукой переключателя (следующие страницы — на нём).
            hl = request.GET.get("hl", "")
            if hl and hl in allowed:
                translation.activate(hl)
                request.LANGUAGE_CODE = hl
                response = self.get_response(request)
                if request.method != "GET" or response.status_code != 200:
                    return response  # 404/ошибки/POST языковую куку не ставят
                from django.conf import settings

                response.set_cookie(
                    settings.LANGUAGE_COOKIE_NAME,
                    hl,
                    max_age=settings.LANGUAGE_COOKIE_AGE,
                    path=settings.LANGUAGE_COOKIE_PATH,
                    domain=settings.LANGUAGE_COOKIE_DOMAIN,
                    secure=settings.LANGUAGE_COOKIE_SECURE,
                    httponly=settings.LANGUAGE_COOKIE_HTTPONLY,
                    samesite=settings.LANGUAGE_COOKIE_SAMESITE,
                )
                return response
            active = translation.get_language() or ""
            if allowed and active not in allowed:
                default = getattr(tenant, "default_locale", "") or ""
                loc = default if default in allowed else allowed[0]
                translation.activate(loc)
                request.LANGUAGE_CODE = loc
        return self.get_response(request)


class CabinetLocaleMiddleware:
    """T1 (FB-12): активирует язык КАБИНЕТА для кабинет-путей, независимо от языка
    витрины (её выбирает клиент). Стоит после LocaleMiddleware → перекрывает его выбор
    только в кабинете. Витрину/публичные пути не трогает.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith(CABINET_PREFIXES):
            return self.get_response(request)
        from django.utils import translation

        loc = resolve_cabinet_locale(request)
        translation.activate(loc)
        request.LANGUAGE_CODE = loc
        response = self.get_response(request)
        # STU-16e: без выбора в сессии язык берётся из `Accept-Language` → ответ
        # зависит от заголовка, и промежуточный кэш обязан это учитывать.
        try:
            patch_vary_headers(response, ("Accept-Language",))
        except Exception:  # noqa: BLE001 — не-HTTP ответы (стримы/заглушки тестов)
            pass
        return response


class ModuleGatingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant = getattr(request, "tenant", None)
        if tenant is not None and getattr(tenant, "schema_name", "public") != "public":
            spec = modules.module_for_path(request.path)
            if spec is not None and not modules.is_module_active(tenant, spec.key):
                raise Http404("Module is not active for this business")
        return self.get_response(request)


class CabinetOwnerAccessMiddleware:
    """Гейт кабинета поверх `@login_required`: доступ только членам тенанта.

    `@login_required` пропускает ЛЮБОГО аутентифицированного пользователя схемы, а
    роль во вьюхах не проверяется. Здесь для кабинет-путей на схеме тенанта требуем
    явную `Membership` (fail-closed): аутентифицированный, но не член → 403.
    Аноним не трогаем — его штатно редиректит `@login_required` на логин.

    Закрывает эскалацию: даже если User появится в схеме тенанта иным путём (не
    через `create_business`), без Membership кабинет ему недоступен.
    """

    # Кабинет-пути владельца: CABINET_PREFIXES (dashboard + корневые разделы) плюс
    # алиас мастера онбординга. Витрину/публичные пути/логин НЕ трогаем.
    _PREFIXES = CABINET_PREFIXES
    # KA-12 E6.7c-4: права экранов — в process_view по реестру view_perms; здесь только
    # пол Inhaber-Vorbehalt (Abo/Recht/Geschäft/импорт с сайта) — до разрешения маршрута.
    _OWNER_FLOOR = OWNER_FLOOR_PREFIXES

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant = getattr(request, "tenant", None)
        on_tenant = tenant is not None and getattr(tenant, "schema_name", "public") != "public"
        if (
            on_tenant
            and request.path.startswith(self._PREFIXES)
            and getattr(request.user, "is_authenticated", False)
        ):
            if not has_cabinet_access(request.user):
                return HttpResponseForbidden(_("Kein Zugriff auf dieses Konto."))
            if request.path.startswith(self._OWNER_FLOOR) and not is_owner(request.user):
                return HttpResponseForbidden(_("Nur für Inhaber."))
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        """KA-12 E6.7b: право экрана из реестра ``view_perms`` (по имени маршрута —
        значит, и пути с uuid посередине). Чтение — GET/HEAD/OPTIONS, иначе запись."""
        tenant = getattr(request, "tenant", None)
        if (
            tenant is None
            or getattr(tenant, "schema_name", "public") == "public"
            or not request.path.startswith(self._PREFIXES)
            or not getattr(request.user, "is_authenticated", False)
        ):
            return None
        from . import view_perms

        match = getattr(request, "resolver_match", None)
        view_name = getattr(match, "view_name", "") or ""
        if not view_perms.allowed(request.user, view_name, request.method):
            return HttpResponseForbidden(_("Dafür fehlt Ihnen das Recht."))
        return None


class StorefrontFrameOptionsMiddleware:
    """H1.1: разрешить same-origin кадрирование витрины, чтобы live-preview iframe
    редактора мог переходить по ссылкам между storefront-страницами.

    Прод ставит ``X-Frame-Options: DENY`` глобально (XFrameOptionsMiddleware) — это
    блокирует показ внутренних storefront-страниц в iframe редактора (главная
    декорирована ``@xframe_options_sameorigin`` и грузится, а `/sortiment/`,
    `/termin/`, деталь товара и т.п. — нет → «refused to connect» при клике в
    режиме редактирования). Здесь для storefront-страниц выставляем ``SAMEORIGIN``,
    перебивая ``DENY``: редактор (тот же origin) может их кадрировать, а сторонние
    сайты — нет (защита от клик-джекинга сохраняется).

    Кабинет/логин остаются ``DENY``. Это НЕ только `/dashboard/` — часть разделов
    кабинета владельца смонтирована на корне субдомена ВНЕ `/dashboard/`
    (`config/urls_tenant.py`): `/catalog/` (CRUD товаров), `/imports/` (CSV),
    `/promotions/` (выдача/погашение ваучеров, лояльность), `/crm/` (данные клиентов),
    мастер онбординга. Все под `@login_required`, ни одна не
    участвует в превью редактора (`preview_pages` — только главная + лендинги
    архетипов) → им незачем кадрироваться, оставляем самый строгий ``DENY``.
    Клиентский ЛК `/konto/` (магик-линк) — это витрина (ссылка «Mein Konto» в шапке/
    подвале может кликаться в превью), поэтому он остаётся ``SAMEORIGIN``.

    Вьюхи с ``xframe_options_exempt`` (G10 iframe-виджет для ЧУЖИХ сайтов, `?embed=1`)
    не трогаем — им нужен полностью открытый кадр.

    Размещён ВЫШЕ ``XFrameOptionsMiddleware`` в MIDDLEWARE → его ``process_response``
    отрабатывает ПОСЛЕ → перебивает выставленный ``DENY``.
    """

    _BLOCK_PREFIXES = (
        "/dashboard/",
        "/accounts/",
        "/admin/",
        "/catalog/",
        "/imports/",
        "/promotions/",
        "/crm/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if getattr(response, "xframe_options_exempt", False):
            return response  # G10 embed-виджет — оставляем открытым для чужих сайтов
        if not request.path.startswith(self._BLOCK_PREFIXES):
            response["X-Frame-Options"] = "SAMEORIGIN"
        return response


class PackageScopeMiddleware:
    """T-8.32b: лёгкий пакет («Aktionen», «Eintrag») видит только свои экраны кабинета.

    Остальное под кабинетными префиксами — страница «In Ihrem Paket nicht enthalten» (403):
    не 404 (тот значит «модуль выключен»), не молчаливый 302 (закладка ломалась бы без
    объяснения). Fetch/POST — JSON 403. Витрину и вход не трогаем; аноним получает свой
    редирект на логин от вьюхи. Пакет Laden — без изменений (белого списка нет)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        from . import packages

        tenant = getattr(request, "tenant", None)
        if tenant is None or getattr(tenant, "schema_name", "public") == "public":
            return None
        if not request.path.startswith(CABINET_PREFIXES):
            return None
        if not getattr(getattr(request, "user", None), "is_authenticated", False):
            return None
        match = getattr(request, "resolver_match", None)
        name = getattr(match, "view_name", "") or ""
        if packages.view_allowed(tenant, name):
            return None
        return self._not_included(request, packages.package_of(tenant))

    @staticmethod
    def _not_included(request, package):
        from django.http import JsonResponse
        from django.shortcuts import render

        accept = request.headers.get("Accept", "")
        fetch = request.headers.get("Sec-Fetch-Mode") not in (None, "navigate", "nested-navigate")
        if (
            request.method != "GET"
            or "application/json" in accept
            or request.headers.get("X-Requested-With")
            or request.headers.get("HX-Request")
            or fetch
        ):
            return JsonResponse({"error": "package"}, status=403)
        return render(
            request,
            "tenant/package_not_included.html",
            {"package_label": package.label},
            status=403,
        )


class TelegramLiteScopeMiddleware:
    """T-8.30 (Р-2): сессия из Telegram Mini App видит ТОЛЬКО лёгкие экраны.

    Действует лишь при флаге сессии ``tg_lite`` (``apps.core.tg_login``). На каждый запрос
    проверяет срок (12 ч, абсолютный) и что связь с общим ботом жива, ограничения Art. 18
    нет, пользователь всё ещё владелец — иначе выход и «Mini App neu öffnen». Затем:
    разрешённый экран — пропуск; прочий экран кабинета — страница «в Telegram недоступно»
    (fetch — JSON 403); всё остальное (витрина, служебные экраны) видит анонима —
    deny-by-default для любого входа, о котором этот список не знает.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        from . import tg_login

        if not tg_login.is_tg_session(request):
            return None
        tenant = getattr(request, "tenant", None)
        if tenant is None or getattr(tenant, "schema_name", "public") == "public":
            return None
        match = getattr(request, "resolver_match", None)
        name = getattr(match, "view_name", "") or ""
        if name in ("tg-start", "tg-lite-info"):
            return None
        reason = self._revoked(request, tenant)
        if reason:
            from django.contrib.auth import logout

            logout(request)
            return self._info(request, reason)
        if name in tg_login.TG_LITE_VIEWS:
            return None
        if request.path.startswith(CABINET_PREFIXES):
            return self._info(request, "")
        from django.contrib.auth.models import AnonymousUser

        request.user = AnonymousUser()
        return None

    @staticmethod
    def _revoked(request, tenant) -> str:
        import time

        from . import tg_login

        flag = request.session.get(tg_login.SESSION_KEY) or {}
        try:
            uid = int(flag.get("uid"))
            exp = int(flag.get("exp"))
        except (TypeError, ValueError, AttributeError):
            return "beendet"
        if exp < time.time():
            return "abgelaufen"
        user = getattr(request, "user", None)
        # Пользователь уже загружен и активен — хватает одной проверки роли.
        if not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
            return "beendet"
        from .models import Membership

        if not Membership.objects.filter(user_id=user.pk, role=Membership.ROLE_OWNER).exists():
            return "beendet"
        if not tg_login.telegram_allowed(uid, tenant, user.pk):
            return "beendet"
        return ""

    @staticmethod
    def _info(request, reason: str):
        from django.http import JsonResponse
        from django.shortcuts import redirect
        from django.urls import reverse

        accept = request.headers.get("Accept", "")
        fetch = request.headers.get("Sec-Fetch-Mode") not in (None, "navigate", "nested-navigate")
        if (
            "application/json" in accept
            or request.headers.get("X-Requested-With")
            or request.headers.get("HX-Request")
            or fetch
        ):
            return JsonResponse({"error": "tg_lite"}, status=403)
        url = reverse("tg-lite-info")
        return redirect(f"{url}?grund={reason}" if reason else url)
