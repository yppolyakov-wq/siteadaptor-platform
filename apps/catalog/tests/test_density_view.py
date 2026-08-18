"""KAT-4/KAT-5: контрол плотности «− N +» посетителю + смена вида каталога без
перезагрузки. Серверные замки: гейты рендера контрола, зона подмены
data-listing-root, делегированный сорт (инлайн-биндинг в swap-зоне запрещён —
после fetch-подмены он бы умер). Поведение JS — стенд Playwright."""

from importlib import import_module

import pytest
from django.conf import settings as dj_settings
from django.test import RequestFactory

from apps.catalog.tests.factories import ProductFactory
from apps.promotions import public_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _req(path="/", site_config=None):
    request = RequestFactory().get(path)
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = TenantFactory.build(site_config=site_config or {})
    return request


def test_catalog_density_control_in_card_view_only():
    ProductFactory()
    html = public_views.product_list(_req("/sortiment/")).content.decode()
    assert 'data-dc-mode="grid" data-dc-key="catalog"' in html
    # стартовое значение = колонки владельца (дефолт catalog_layout cols3 → 3)
    assert 'data-dc-default="3"' in html
    # прайс-вид: карточной сетки нет → контрола плотности сетки нет
    html2 = public_views.product_list(_req("/sortiment/?ansicht=preisliste")).content.decode()
    assert 'data-dc-mode="grid"' not in html2


def test_listing_root_swap_zone_single_and_no_inline_scripts():
    ProductFactory()
    html = public_views.product_list(_req("/sortiment/")).content.decode()
    # маркап-форма атрибута (голый маркер ловил бы строки JS-селекторов — урок MEN-24)
    assert html.count("data-listing-root>") == 1
    # KAT-5: внутри swap-зоны нет инлайн-биндинга сорта (он делегирован в
    # _grid_view_script; инлайн умирал бы после первой fetch-подмены)
    root = html.split("data-listing-root", 1)[1]
    assert "js-sort-select h-9" in root  # селект на месте…
    assert 'querySelectorAll(".js-sort-select")' not in root  # …а биндинг — нет


def test_home_price_section_has_plv_density_control():
    ProductFactory()
    cfg = {"sections": [{"key": "products", "enabled": True, "style": "preisliste"}]}
    html = public_views.storefront_home(_req("/", site_config=cfg)).content.decode()
    assert 'data-dc-mode="plv" data-dc-key="products"' in html


def test_delegated_sort_handler_in_base_script():
    ProductFactory()
    html = public_views.product_list(_req("/sortiment/")).content.decode()
    # делегированный обработчик живёт вне swap-зоны (партиал в _base)
    assert 'closest(".js-sort-select")' in html
