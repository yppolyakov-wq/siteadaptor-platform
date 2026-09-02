"""DL-14 (2026-09-02): «Verteilen» + авто-колонки по количеству + «Alle anzeigen».

Фидбэк владельца: «если товара мало (4 при сетке на 5) — либо сетку на 4, либо
растягивать по ширине (увеличивать отступ); так же с последним рядом списка»;
«при скрытии карточек на главной — кнопка „показать все“ в соответствующий каталог».
План: docs/dl14-spread-autocols-plan-2026-09-02.md.
"""

import importlib.util
import re
from importlib import import_module
from pathlib import Path

import pytest
from django.conf import settings as dj_settings
from django.test import RequestFactory

from apps.catalog.models import Category
from apps.catalog.tests.factories import ProductFactory
from apps.promotions import public_views
from apps.promotions.models import Promotion
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _get(view, path="/", tenant=None, **kw):
    request = RequestFactory().get(path)
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = tenant
    return view(request, **kw).content.decode()


# ── движок ──────────────────────────────────────────────────────────────────


def test_spread_tail_normalizes_and_grid_attr_defaults():
    assert siteconfig.normalize_layout({"tail": "spread"})["tail"] == "spread"
    assert "spread" in siteconfig._LAYOUT_TAILS
    # главная: дефолт trim; листинг (default_tail) — spread; ключ раскладки сильнее
    assert 'data-sf-tail="trim"' in siteconfig.grid_attr_string({})
    assert 'data-sf-tail="spread"' in siteconfig.grid_attr_string({}, default_tail="spread")
    assert 'data-sf-tail="fill"' in siteconfig.grid_attr_string(
        {"tail": "fill"}, default_tail="spread"
    )
    assert 'data-sf-tail="spread"' in siteconfig.grid_attr_string({"tail": "spread"})


def test_auto_cols_triplet_floor_and_clamp():
    # без count — 1:1; count ≥ колонок — 1:1
    assert siteconfig.auto_cols_triplet((2, 3, 5), None) == ((2, 3, 5), False)
    assert siteconfig.auto_cols_triplet((2, 3, 5), 0) == ((2, 3, 5), False)
    assert siteconfig.auto_cols_triplet((2, 3, 5), 5) == ((2, 3, 5), False)
    assert siteconfig.auto_cols_triplet((2, 3, 5), 9) == ((2, 3, 5), False)
    # 4 из 5 → десктоп 4; планшет 3 остаётся (4 ≥ 3)
    assert siteconfig.auto_cols_triplet((2, 3, 5), 4) == ((2, 3, 4), True)
    # пол: планшет 2, десктоп 3; телефон не меняется
    assert siteconfig.auto_cols_triplet((2, 3, 5), 2) == ((2, 2, 3), True)
    assert siteconfig.auto_cols_triplet((2, 3, 5), 1) == ((2, 2, 3), True)
    # пол не поднимает выше исходных колонок
    assert siteconfig.auto_cols_triplet((1, 2, 2), 1) == ((1, 2, 2), False)


def test_grid_attr_string_count_and_more():
    attrs = siteconfig.grid_attr_string({"preset": "cols5"}, count=4)
    assert 'data-sf-cols="2/3/4"' in attrs and 'data-sf-auto="1"' in attrs
    attrs = siteconfig.grid_attr_string({"preset": "cols5"}, count=20)
    assert 'data-sf-cols="2/3/5"' in attrs and "data-sf-auto" not in attrs
    # хардкоженный триплет тоже клампится
    attrs = siteconfig.grid_attr_string(None, cols="2/2/3", count=1)
    assert 'data-sf-cols="2/2/3"' in attrs  # пол 2/3 держит
    attrs = siteconfig.grid_attr_string(None, cols="2/3/4", count=3, more=True)
    assert 'data-sf-cols="2/3/3"' in attrs and 'data-sf-more="1"' in attrs
    # scroll/balance — своя механика, атрибутов нет
    assert siteconfig.grid_attr_string({"scroll": True}, count=2) == 'data-sf-slider="1"'  # DL-16.1


def test_css_block_carries_spread_auto_and_more_rules():
    css = (ROOT / "static" / "src" / "app.css").read_text(encoding="utf-8")
    spec = importlib.util.spec_from_file_location(
        "gen_fill_rows_css", ROOT / "scripts" / "gen_fill_rows_css.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    block = mod.generate()
    assert block in css  # замок свежести (как в DL-11)
    assert '[data-sf-tail="spread"]:not(.is-list):not([data-density]) { display: flex;' in css
    assert "justify-content: center" in css and "--sf-gap" in css  # DL-15 B
    for n in (2, 3, 4, 5, 6):
        assert (
            f'[data-sf-cols$="/{n}"]:not([data-density])[data-sf-tail="spread"] {{ --sf-n: {n}; }}'
            in css
        )
        assert (
            f'[data-sf-cols$="/{n}"]:not([data-density])[data-sf-auto] {{ grid-template-columns: repeat({n}, minmax(0, 1fr)); }}'
            in css
        )
    # trim без кнопки не трогает сетки с кнопкой; вариант с кнопкой показывает её
    assert ":not([data-sf-more]) > :nth-child(3n+1):nth-last-child(-n+2):not(:first-child)" in css
    assert (
        "[data-sf-more]:not(.is-list) > :nth-child(3n+1):nth-last-child(-n+3):not(:first-child):not(.sf-more)"
        in css
    )
    assert "~ .sf-more { display: flex; }" in css
    assert ".sf-more { display: none; grid-column: 1 / -1;" in css


def _grid_inner(html, key):
    """Содержимое элемента data-grid="<key>" (по балансу div-тегов)."""
    start = html.index(f'data-grid="{key}"')
    i = html.index(">", start) + 1
    depth, pos = 1, i
    while depth:
        m = re.search(r"<div\b|</div>", html[pos:])
        assert m, "незакрытый div"
        depth += 1 if m.group(0) == "<div" else -1
        pos += m.end()
    return html[i : pos - len("</div>")]


# ── главная ─────────────────────────────────────────────────────────────────


def test_home_grid_auto_cols_and_more_button():
    tenant = TenantFactory(schema_name="public", slug="dl14a", name="A", disabled_modules=[])
    tenant.site_config = siteconfig.normalize(
        {
            "sections": [
                {"key": "categories", "enabled": True},
                {"key": "promotions", "enabled": True},
            ]
        }
    )
    tenant.save()
    for i in range(2):
        Category.objects.create(name={"de": f"Kat {i}"}, slug=f"kat-{i}", is_active=True)
    html = _get(public_views.storefront_home, "/", tenant)
    grid = re.search(r'data-grid="categories"[^>]*', html).group(0)
    # cols4 дефолт (2/3/4) при 2 элементах → 2/2/3 + авто + кнопка «Alle anzeigen»
    assert 'data-sf-cols="2/2/3"' in grid and 'data-sf-auto="1"' in grid
    assert 'data-sf-more="1"' in grid and 'data-sf-tail="trim"' in grid
    assert "data-sf-more-btn" in html and 'href="/sortiment/"' in html
    # кнопка — ПОСЛЕДНИЙ ребёнок сетки (CSS считает ряды по nth-child без неё)
    inner = _grid_inner(html, "categories")
    assert inner.rstrip().endswith("</a>") and "data-sf-more-btn" in inner[-400:], inner[-400:]


def test_home_promotions_more_button_points_to_aktionen():
    tenant = TenantFactory(schema_name="public", slug="dl14b", name="B", disabled_modules=[])
    tenant.site_config = siteconfig.normalize(
        {"sections": [{"key": "promotions", "enabled": True}]}
    )
    tenant.save()
    for i in range(4):
        Promotion.objects.create(title={"de": f"P{i}"}, status="active")
    html = _get(public_views.storefront_home, "/", tenant)
    grid = re.search(r'data-grid="promotions"[^>]*', html).group(0)
    assert 'data-sf-more="1"' in grid
    assert re.search(r'href="/aktionen/"[^>]*data-sf-more-btn', html)


def test_home_spread_from_studio_key():
    tenant = TenantFactory(schema_name="public", slug="dl14c", name="C", disabled_modules=[])
    tenant.site_config = siteconfig.normalize(
        {"sections": [{"key": "categories", "enabled": True, "layout": {"tail": "spread"}}]}
    )
    tenant.save()
    for i in range(5):
        Category.objects.create(name={"de": f"Kat {i}"}, slug=f"kat-{i}", is_active=True)
    html = _get(public_views.storefront_home, "/", tenant)
    assert re.search(r'data-grid="categories"[^>]*data-sf-tail="spread"', html)


# ── листинги ────────────────────────────────────────────────────────────────


def test_catalog_listing_default_spread_without_filler_and_fill_by_key():
    tenant = TenantFactory(schema_name="public", slug="dl14d", name="D", disabled_modules=[])
    for i in range(4):
        ProductFactory(name={"de": f"Prod {i}"})
    html = _get(public_views.product_list, "/sortiment/", tenant)
    grid = re.search(r'data-grid="catalog"[^>]*', html).group(0)
    assert 'data-sf-tail="spread"' in grid
    # дефолт каталога — cols3 (2/2/3): 4 товара ≥ 3 колонок → авто-кламп не нужен
    assert 'data-sf-cols="2/2/3"' in grid and "data-sf-auto" not in grid
    assert "data-sf-filler" not in html
    # владелец выставил 5 колонок, товаров 4 → десктоп сжимается до 4 (пол 3), планшет 3
    tenant.site_config = {"catalog_layout": {"preset": "cols5"}}
    tenant.save()
    html = _get(public_views.product_list, "/sortiment/", tenant)
    grid = re.search(r'data-grid="catalog"[^>]*', html).group(0)
    assert 'data-sf-cols="2/3/4"' in grid and 'data-sf-auto="1"' in grid, grid
    # владелец выбрал плитку-подсказку (tail=fill в раскладке страницы) — она есть
    tenant.site_config = {"catalog_layout": {"preset": "cols4", "tail": "fill"}}
    tenant.save()
    html = _get(public_views.product_list, "/sortiment/", tenant)
    grid = re.search(r'data-grid="catalog"[^>]*', html).group(0)
    assert 'data-sf-tail="fill"' in grid and "data-sf-filler" in html


def test_aktionen_groups_spread_and_no_filler():
    tenant = TenantFactory(schema_name="public", slug="dl14e", name="E", disabled_modules=[])
    for i in range(4):
        Promotion.objects.create(title={"de": f"W{i}"}, status="active", group="Wochenangebote")
    html = _get(public_views.promotion_list, "/aktionen/", tenant)
    grid = re.search(r'data-grid="promo_list"[^>]*', html).group(0)
    assert 'data-sf-tail="spread"' in grid and 'data-sf-cols="2/2/3"' in grid
    assert "data-sf-filler" not in html


# ── Studio ──────────────────────────────────────────────────────────────────


def test_builder_saves_spread_tail(settings):
    from types import SimpleNamespace

    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware

    from apps.core import views

    tenant = TenantFactory(schema_name="public", slug="dl14f", name="F", site_config={})
    req = RequestFactory().post(
        "/dashboard/site/home/",
        {
            "order_products": "1",
            "enabled_products": "on",
            "layout_preset_products": "cols4",
            "tail_products": "spread",
        },
    )
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    assert views.home_builder_view(req).status_code == 302
    tenant.refresh_from_db()
    lay = siteconfig.section_layout(siteconfig.normalize(tenant.site_config), "products")
    assert lay.get("tail") == "spread"
