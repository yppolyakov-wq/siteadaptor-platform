"""FB-33 M5a: страница 404 витрины — хост блоков `not_found` (решение владельца K4,
`docs/fb33-stack8-plan-2026-11-22.md` §1 A и §4).

Умолчание: ключа `page_blocks["not_found"]` нет → «Suche» и «Beliebt» (плитки верхнего уровня
меню); ключ есть и пуст → блоков нет («задано пусто» ≠ «не задано»). У блоков по умолчанию
постоянные id — сохранённое состояние страницы одно и то же в любом запросе (черновик
«Seitenaufbau» не «меняется» сам) — и нет хранимого текста: подписи — `gettext` при показе.

Блоки с полями ввода и «Liste» на 404 не ставятся: страница отдаётся анониму на любом битом
адресе, без cookie; в кэш она попадает одной записью без пути (M5a-2,
`pagecache.cached_not_found`). Модуль без БД.
"""

from __future__ import annotations

from apps.core import confirmation_page

HOST = "not_found"
#: блоки, которых на 404 нет: с полями ввода (набор подтверждения, не копия) и «Liste» —
#: кнопка корзины несёт CSRF-токен (cookie анониму на любом битом адресе), а выборка товаров
#: шла бы на каждый запрос бота (ревью безопасности стопки 8)
FORM_BLOCKS = confirmation_page.FORM_BLOCKS | confirmation_page.SAFE_POST_BLOCKS
SEARCH_ID = "nf-search"
POPULAR_ID = "nf-popular"
#: блоки страницы, пока владелец её не правил (в сыром виде; хранимую форму даёт `default_rows`)
DEFAULT_ROWS = (
    {"key": "site_search", "id": SEARCH_ID, "enabled": True, "data": {}},
    {"key": "quick_links", "id": POPULAR_ID, "enabled": True, "data": {"set": "menu"}},
)


def default_rows() -> list:
    """Блоки по умолчанию в той же форме, в какой их хранит `normalize` (свежая копия)."""
    from apps.tenants import siteconfig

    return [siteconfig._clean_cblock(dict(row)) for row in DEFAULT_ROWS]


def rows(config) -> list:
    """Блоки страницы 404: сохранённые либо умолчание (`siteconfig.page_rows`)."""
    from apps.tenants import siteconfig

    return siteconfig.page_rows(config if isinstance(config, dict) else {}, HOST)
