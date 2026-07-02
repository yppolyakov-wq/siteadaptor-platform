"""UB1-3 C0: характеризационные замки структуры каталога — порядок блоков
(header → чипы категорий → фасет-форма → подкатегории → сорт → грид → Show more)
и empty-state ДО/ПОСЛЕ свода products.html на каркас listing.html."""

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


def _body(params=None):
    request = RequestFactory().get("/sortiment/", params or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(name="Bäckerei X", address="Hauptstr. 1")
    return public_views.product_list(request).content.decode()


def test_catalog_blocks_order_snapshot():
    """Порядок блоков страницы: заголовок → чипы категорий → фасет-форма (цена) →
    сорт → грид → cursor-«Show more». Разброс цен включает price-фильтр; 25+
    товаров дают вторую страницу курсора."""
    cat = CategoryFactory(slug="brot", name={"de": "Brot"})
    ProductFactory(name={"de": "Billigbrot"}, category=cat, base_price="1.50")
    ProductFactory(name={"de": "Teuerbrot"}, category=cat, base_price="99.00")
    for i in range(25):
        ProductFactory(name={"de": f"Brot {i}"}, category=cat)
    body = _body()
    i_h1 = body.index('data-edit="catalog_title"')
    i_chips = body.index("px-3 py-1.5 rounded-full")  # первый чип категорий
    i_form = body.index("data-catalog-filters")  # GET-форма цена/бейдж/наличие
    i_sort = body.index('name="sort"')
    i_grid = body.index('data-sf-section="catalog"')
    i_more = body.index("cursor=")  # ссылка «Show more» с курсором
    assert i_h1 < i_chips < i_form < i_sort < i_grid < i_more


def test_catalog_subcats_first_between_facets_and_grid():
    """Подкатегории-первыми: карточки подкатегорий стоят между фасетами и гридом."""
    parent = CategoryFactory(slug="brot", name={"de": "Brot"})
    CategoryFactory(slug="roggen", name={"de": "Roggen"}, parent=parent)
    ProductFactory(name={"de": "Roggenbrot"}, category=parent)
    body = _body(params={"kategorie": "brot"})
    i_subcats = body.index("min-h-[4rem]")  # карточка подкатегории
    i_grid = body.index('data-sf-section="catalog"')
    assert i_subcats < i_grid
    assert "Roggen" in body


def test_catalog_empty_states():
    """Пустой каталог → «No products yet.»; категория только с подкатегориями →
    подсказка выбора подкатегории (грида нет)."""
    body = _body()
    assert "No products yet." in body
    assert 'data-sf-section="catalog"' not in body

    parent = CategoryFactory(slug="leer", name={"de": "Leer"})
    CategoryFactory(slug="unter", name={"de": "Unter"}, parent=parent)
    body2 = _body(params={"kategorie": "leer"})
    assert "Choose a subcategory above." in body2
    assert 'data-sf-section="catalog"' not in body2
