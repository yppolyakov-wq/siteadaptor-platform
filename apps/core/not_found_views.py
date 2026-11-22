"""FB-33 M5a: страница 404 витрины с блоками владельца и её превью для «Seitenaufbau».

`storefront_404` — `handler404` из `config.urls_tenant`. Django берёт обработчик из текущего
urlconf, а до разбора адреса это ROOT_URLCONF (тот же модуль): `Http404` из middleware на
платформе и портале тоже приходит сюда (ревью плана, R1). Поэтому страницу с блоками получает
только посетитель витрины бизнеса (`_wants_blocks`), всем остальным — прежняя standalone-
страница `templates/404.html` (`django.views.defaults.page_not_found`). Она же — запасной
путь при любом сбое рендера: 404 не должна превращаться в 500.

Страница отдаётся анониму на любом битом адресе: сессию не пишет, cookie не ставит, в кэш
страниц не попадает (код не 200), вне индекса, без canonical и JSON-LD.
"""

from __future__ import annotations

import logging

from django.http import Http404
from django.shortcuts import render
from django.views.defaults import page_not_found

from apps.core import not_found_page, page_settings
from apps.core.i18n_cabinet import CABINET_PREFIXES

logger = logging.getLogger(__name__)

TEMPLATE = "storefront/not_found.html"
#: пути, где хром витрины неуместен: кабинет и файлы (битая картинка — не страница)
PLAIN_PREFIXES = (*CABINET_PREFIXES, "/media/", "/static/")
BLOCK_METHODS = ("GET", "HEAD")


def _wants_blocks(request) -> bool:
    """Отдавать ли страницу с блоками: только витрина бизнеса, обычный запрос страницы."""
    tenant = getattr(request, "tenant", None)
    if tenant is None or getattr(tenant, "schema_name", "public") == "public":
        return False  # платформа, неизвестный хост
    if getattr(request, "portal", None) is not None:
        return False  # городской портал
    if request.method not in BLOCK_METHODS or request.headers.get("HX-Request"):
        return False  # ответ на форму или фрагмент — не страница
    if request.path.startswith(PLAIN_PREFIXES):
        return False
    from apps.core.storefront_state import hidden_reasons

    # витрина ещё закрыта (почта не подтверждена, сайт не опубликован) — без её хрома
    return not hidden_reasons(tenant)


def _page(request, status: int, is_preview: bool = False):
    context = {
        # R7: тип страницы для Студии — явно: у битого адреса нет `resolver_match`, и
        # панель иначе показала бы блоки главной
        "storefront_page_type": not_found_page.HOST,
        "storefront_page_ref": "",
        "is_preview": is_preview,
    }
    return render(request, TEMPLATE, context, status=status)


def storefront_404(request, exception=None):
    """`handler404` витрины: страница с блоками либо прежняя простая (и при любом сбое)."""
    if not _wants_blocks(request):
        return page_not_found(request, exception)
    try:
        response = _page(request, 404)
    except Exception:  # noqa: BLE001 — сбой блока не делает из 404 ошибку 500
        logger.warning(
            "storefront 404: block page failed, plain page served (%s %s)",
            getattr(request.tenant, "schema_name", ""),
            request.path,
            exc_info=True,
        )
        return page_not_found(request, exception)
    response["X-Robots-Tag"] = "noindex"
    return response


def not_found_preview(request):
    """Превью для «Seitenaufbau»: та же страница с кодом 200. Только члену команды с правом
    сайта, остальным — 404 (адрес не сообщает, что он существует); вне индекса и кэша."""
    if not page_settings._may_preview(request):
        raise Http404
    # как у прочих витринных страниц: `?preview=1` — пустое место блоков видно в превью
    response = _page(request, 200, is_preview=request.GET.get("preview") == "1")
    response["X-Robots-Tag"] = "noindex, nofollow"
    response["Cache-Control"] = "private, no-store"
    return response
