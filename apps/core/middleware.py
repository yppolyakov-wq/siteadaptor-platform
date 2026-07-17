"""Гейтинг модулей кабинета (Track D / D0a): неактивный модуль → 404.

Зеркало apps.billing.middleware.SubscriptionGatingMiddleware, но по реестру
apps.core.modules: путь матчится на модуль по самому длинному url-префиксу;
если модуль для тенанта неактивен (выключен владельцем / не входит в тариф) —
404, как будто раздела нет. Core-модули активны всегда. Публичную витрину,
public-схему и пути вне реестра не трогаем.
"""

from django.http import Http404, HttpResponseForbidden

from . import modules
from .i18n_cabinet import CABINET_PREFIXES, resolve_cabinet_locale
from .roles import has_cabinet_access
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


class CabinetLocaleMiddleware:
    """T1 (FB-12): активирует язык КАБИНЕТА для кабинет-путей, независимо от языка
    витрины (её выбирает клиент). Стоит после LocaleMiddleware → перекрывает его выбор
    только в кабинете. Витрину/публичные пути не трогает.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(CABINET_PREFIXES):
            from django.utils import translation

            loc = resolve_cabinet_locale(request)
            translation.activate(loc)
            request.LANGUAGE_CODE = loc
        return self.get_response(request)


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
    _PREFIXES = (*CABINET_PREFIXES, "/willkommen/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tenant = getattr(request, "tenant", None)
        on_tenant = tenant is not None and getattr(tenant, "schema_name", "public") != "public"
        if (
            on_tenant
            and request.path.startswith(self._PREFIXES)
            and getattr(request.user, "is_authenticated", False)
            and not has_cabinet_access(request.user)
        ):
            return HttpResponseForbidden("Kein Zugriff auf dieses Konto.")
        return self.get_response(request)


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
    `/willkommen/` (алиас мастера онбординга). Все под `@login_required`, ни одна не
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
        "/willkommen/",
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
