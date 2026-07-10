"""Гейтинг модулей кабинета (Track D / D0a): неактивный модуль → 404.

Зеркало apps.billing.middleware.SubscriptionGatingMiddleware, но по реестру
apps.core.modules: путь матчится на модуль по самому длинному url-префиксу;
если модуль для тенанта неактивен (выключен владельцем / не входит в тариф) —
404, как будто раздела нет. Core-модули активны всегда. Публичную витрину,
public-схему и пути вне реестра не трогаем.
"""

from django.http import Http404

from . import modules
from .i18n_cabinet import CABINET_PREFIXES, resolve_cabinet_locale


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
