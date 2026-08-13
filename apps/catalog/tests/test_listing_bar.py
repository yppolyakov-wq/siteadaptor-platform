"""DS-10: единая строка инструментов листинга [Фильтры · Сортировка · Вид];
поиск убран из тулбара (он в шапке сайта, DS-6/DS-10).

Замки написаны по рискам разведки и находкам адверсариального ревью: срез
строки берётся по РЕАЛЬНЫМ границам разметки (маркер строки → обёртка сетки),
иначе ассерты ловят инлайн-скрипты `_base.html` и становятся вакуумными.
"""

from importlib import import_module

import pytest
from django.conf import settings as dj_settings
from django.test import RequestFactory

from apps.catalog.models import Category, Product
from apps.promotions import public_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

#: Явный маркер конца строки инструментов (обёртка сетки не годится: при
#: нулевой выдаче блок listing_grid не рендерится вовсе).
_BAR_END = "<!--/listing-bar-->"


def _catalog(tenant, query=""):
    request = RequestFactory().get(f"/sortiment/{query}")
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = tenant
    return public_views.product_list(request).content.decode()


def _bar(html):
    """Ровно строка инструментов — от её маркера до обёртки листинга."""
    start = html.find("data-listing-bar")
    assert start > 0, "строка инструментов не отрендерена"
    end = html.find(_BAR_END, start)
    assert end > start, "не найден конец строки (обёртка сетки/прайса)"
    return html[start:end]


def _seed(n=3, *, badges=True):
    cat = Category.objects.create(name={"de": "Brot"}, slug="ds10-brot")
    for i in range(n):
        Product.objects.create(
            name={"de": f"Ware {i}"},
            base_price=f"{3 + i}.00",
            category=cat,
            is_active=True,
            badge="beliebt" if badges and i == 0 else "",
        )
    return cat


def test_no_search_field_in_listing_toolbar():
    """Поиск живёт в шапке — в строке инструментов листинга его нет."""
    _seed()
    html = _catalog(TenantFactory.build())
    bar = _bar(html)
    assert 'type="search"' not in bar
    assert "sf-hsearch" in html  # поиск шапки на месте


def test_filters_sort_and_view_share_one_row():
    """Три инструмента — внутри ОДНОГО контейнера строки, в порядке
    [Фильтры][Сортировка][Вид], и вся строка выше сетки."""
    _seed()
    bar = _bar(_catalog(TenantFactory.build()))
    i_filter = bar.find("data-filter-toggle")
    i_sort = bar.find('name="sort"')
    i_view = bar.find("data-grid-view")
    assert i_filter >= 0, "кнопка фильтров не в строке"
    assert i_sort > i_filter, "сортировка не в строке/не после фильтров"
    assert i_view > i_sort, "переключатель вида не в строке/не после сортировки"
    # ровно один экземпляр каждого — перенос include между блоками не задвоил
    assert bar.count("data-filter-toggle=") == 1
    assert bar.count('<select id="id_listing_sort"') == 1
    assert bar.count('data-grid-view="grid"') == 1


def test_filter_button_survives_empty_result():
    """Риск разведки: строка гейтилась show_listing_toolbar (= items or q), и при
    нулевой выдаче кнопка «Фильтры» исчезала — снять фильтр было нечем."""
    _seed()
    bar = _bar(_catalog(TenantFactory.build(), "?preis_bis=0"))
    assert "data-filter-toggle" in bar
    assert 'name="sort"' not in bar  # сортировать нечего — селекта нет


def test_no_filter_button_without_panel():
    """Кнопка рендерится только там, где есть панель того же ключа (иначе
    затемнение без ящика + залоченный скролл)."""
    _seed()
    html = _catalog(TenantFactory.build(site_config={"catalog_show_filters": False}))
    assert "data-filter-toggle" not in _bar(html)
    assert 'data-filter-panel="catalog"' not in html


def test_sort_carries_query_and_facets():
    """Смена сортировки не сбрасывает ни поиск из шапки, ни активный фасет."""
    _seed()
    bar = _bar(_catalog(TenantFactory.build(), "?q=Ware&badge=beliebt"))
    assert 'name="q" value="Ware"' in bar
    assert 'name="badge" value="beliebt"' in bar


def test_header_search_still_filters_catalog():
    """?q= из шапки продолжает сужать выдачу (движок UB не тронут)."""
    _seed()
    tenant = TenantFactory.build()
    assert "Ware 1" in _catalog(tenant)
    assert "Ware 1" not in _catalog(tenant, "?q=Ware 0")


def test_sort_form_submittable_without_js():
    """Автосабмит селекта — на JS; без него нужна обычная кнопка (её роль играла
    кнопка «Search», удалённая вместе с полем поиска)."""
    _seed()
    bar = _bar(_catalog(TenantFactory.build()))
    assert "<noscript>" in bar and 'type="submit"' in bar


def test_view_switcher_hidden_in_price_list_mode():
    """В прайс-виде сетки data-grid нет — кнопки вида были бы мертвы."""
    _seed()
    html = _catalog(TenantFactory.build(site_config={"catalog_layout": {"preset": "preisliste"}}))
    assert "data-price-list" in html
    assert "data-grid-view" not in _bar(html)


def test_facet_panel_starts_hidden_with_noscript_fallback():
    """Панель отдаётся скрытой (CSS DS-6 делает видимую панель fixed-ящиком —
    до init() она вспыхивала поверх контента); без JS её показывает noscript."""
    _seed()
    html = _catalog(TenantFactory.build())
    i = html.find('data-filter-panel="catalog"')
    assert i > 0
    tag = html[html.rfind("<form", 0, i) : html.find(">", i)]
    assert "hidden" in tag
    assert "<noscript><style>[data-filter-panel]" in html


def test_header_search_targets_primary_listing_of_archetype():
    """DS-10: поле поиска убрано из тулбаров ВСЕХ листингов, поэтому 🔍 шапки
    обязан искать в листинге главного модуля архетипа — иначе у отеля/салона
    поиск уводит в пустой каталог (регрессия, найденная ревью)."""
    from apps.core.context import modules_nav

    # фабрика включает ВСЕ модули — оставляем ровно primary архетипа, иначе
    # _PRIORITY выберет events у кого угодно.
    cases = {
        "hotel": ("/unterkunft/", ["events", "booking"]),
        "friseur": ("/termin/", ["events", "stays"]),
        "events": ("/veranstaltung/", []),
    }
    for business_type, (url, off) in cases.items():
        request = RequestFactory().get("/")
        request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
        request.tenant = TenantFactory.build(business_type=business_type, disabled_modules=off)
        ctx = modules_nav(request)
        assert ctx["storefront_search_url"] == url, (business_type, ctx["storefront_search_url"])
    # каталожный архетип — как раньше
    request = RequestFactory().get("/")
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = TenantFactory.build(
        business_type="bakery", disabled_modules=["events", "stays", "booking"]
    )
    assert modules_nav(request)["storefront_search_url"] == "/sortiment/"
