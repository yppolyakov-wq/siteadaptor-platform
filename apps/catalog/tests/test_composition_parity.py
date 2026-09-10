"""STU-18d (d-pre): характеризационные замки КОМПОЗИЦИЙ страницы каталога.

Композиции («С обложкой», «Полки», «Вкладки», «Витрина», «Журнал», «Мозаика»,
«Компактно», «Сначала сеты») сегодня реализованы НЕ переиспользуемо: это ветки
`{% if category_page_style == … %}` внутри `templates/storefront/products.html`
плюс каскад по `data-cat-layout`. Чтобы включить их на девяти других листингах,
их надо вынести в каркас `listing.html` — а вынос обязан оставить каталог таким
же, каким он был.

Замок снимает ОТПЕЧАТОК каждой композиции ДО рефактора: какой маркер обязан быть
в разметке и в каком порядке относительно грида. Прецедент — UB1-3
(`test_listing_parity.py`): сверяем структуру и порядок, а не байты, иначе замок
краснел бы на любой перестановке пробелов.
"""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.tests.factories import CategoryFactory, ProductFactory
from apps.promotions import public_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _render(style: str, tag: str = "brot") -> str:
    """Страница КАТЕГОРИИ с заданной композицией (у категории есть подкатегории).

    Слаг параметризован: один тест сравнивает несколько композиций, а слаг
    категории уникален — без этого прогон падает на constraint, а не на сути.
    """
    parent = CategoryFactory(slug=tag, name={"de": "Brot"}, page_style=style)
    for suffix, label in (("weizen", "Weizen"), ("roggen", "Roggen")):
        child = CategoryFactory(slug=f"{tag}-{suffix}", name={"de": label}, parent=parent)
        ProductFactory(name={"de": f"{label}brot"}, category=child)
    ProductFactory(name={"de": "Hausbrot"}, category=parent)

    request = RequestFactory().get(f"/sortiment/{tag}/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(name="Bäckerei X", address="Hauptstr. 1")
    return public_views.product_list(request, slug=tag).content.decode()


#: Отпечаток композиции: маркер, который обязан быть в разметке ИМЕННО у неё.
#: Пусто — композиция ничего не добавляет к стандартной сетке (её вид даёт каскад
#: по `data-cat-layout`, и отпечатком служит сам атрибут).
FINGERPRINTS = {
    "": "",
    "kopfbild": "",
    "sets": "",
    "regale": "",
    "tabs": "data-category-tabs",
    "schaufenster": "",
    "navigator": "",
    "magazin": "",
    "mosaik": "data-cat-bento",
    "kompakt": "",
}


@pytest.mark.parametrize("style", sorted(FINGERPRINTS))
def test_composition_is_declared_on_the_page_root(style):
    """Композиция доезжает до разметки атрибутом `data-cat-layout`.

    Это единственный общий канал: каскад в app.css рисует полки, мозаику и компакт
    по нему. Если после выноса в каркас атрибут исчезнет, витрина сменится молча.
    """
    body = _render(style)
    if style:
        assert f'data-cat-layout="{style}"' in body, f"композиция {style} не объявлена в корне"
    else:
        assert "data-cat-layout=" not in body, "у «Стандарта» атрибута быть не должно"


@pytest.mark.parametrize("style,marker", [(s, m) for s, m in FINGERPRINTS.items() if m])
def test_composition_renders_its_own_markup(style, marker):
    """У композиции есть СВОЯ разметка, а не только класс: вкладки — навигация,
    мозаика — бенто-грид. После выноса в каркас маркер обязан остаться."""
    assert marker in _render(style), f"{style}: разметка композиции пропала ({marker})"


def test_grid_stays_below_the_composition_chrome():
    """Порядок: хром композиции (вкладки) идёт ДО сетки товаров.

    Порядок — то, что легче всего потерять при переносе блоков в каркас: сетка
    выше вкладок выглядит как поломка вёрстки, а тесты разметки этого не видят.
    """
    body = _render("tabs")
    assert body.index("data-category-tabs") < body.index('data-grid="catalog"')


#: Композиции, которые меняют РАЗМЕТКУ (а не только каскад по `data-cat-layout`).
#: Снято с текущего кода — это и есть отпечаток: после выноса в каркас набор
#: обязан остаться тем же. Композиция, выпавшая отсюда, стала чисто-CSS (значит
#: её разметку потеряли); появившаяся — наоборот, обзавелась лишней.
CHANGES_MARKUP = {
    "kopfbild",
    "sets",
    "regale",
    "tabs",
    "schaufenster",
    "navigator",
    "magazin",
    "mosaik",
    "kompakt",
}  # замер: СВОЮ разметку добавляют все девять, а не только «очевидные»


def _skeleton(style: str, tag: str) -> str:
    """Разметка БЕЗ самого атрибута композиции — чтобы сравнивать содержимое."""
    return _render(style, tag).replace(f'data-cat-layout="{style}"', "")


def test_which_compositions_change_markup_is_pinned():
    """Какие композиции добавляют свою разметку, а какие живут одним каскадом.

    Ради этого замок и пишется ДО рефактора: при выносе композиций в каркас
    `listing.html` легче всего потерять именно разметочную часть — визуально это
    заметит только владелец, а тесты классов её не видят.
    """
    base = _skeleton("", "std")
    changed = {
        style
        for style in (
            "kopfbild",
            "sets",
            "regale",
            "tabs",
            "schaufenster",
            "navigator",
            "magazin",
            "mosaik",
            "kompakt",
        )
        if _skeleton(style, f"c-{style}") != base
    }
    assert changed == CHANGES_MARKUP, (
        f"состав композиций с собственной разметкой изменился: "
        f"добавились {sorted(changed - CHANGES_MARKUP)}, пропали {sorted(CHANGES_MARKUP - changed)}"
    )
