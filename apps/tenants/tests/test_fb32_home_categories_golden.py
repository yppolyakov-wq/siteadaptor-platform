"""FB-32 S5b R0: характеризация секции «Kategorien» главной ДО новых видов (Regale, Index,
Wegweiser). Нынешние пять видов (`""`, square, tall, wide, compact) обязаны остаться
байт-в-байт — сверка с этими снимками (`docs/fb32-unified-blocks-plan-2026-11-17.md`, S5b).

Обновить (только осознанно): FB32_GOLDEN=update uv run pytest <этот файл>
"""

import os
from datetime import timedelta
from importlib import import_module
from pathlib import Path

import pytest
from django.conf import settings as dj_settings
from django.test import RequestFactory
from django.utils import timezone

from apps.catalog.tests import test_fb3016_catalog_golden as _g
from apps.catalog.tests.factories import CategoryFactory, ProductFactory
from apps.promotions import public_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
GOLDEN = Path(__file__).parent / "golden_fb32"
UPDATE = os.environ.get("FB32_GOLDEN") == "update"
STYLES = ("", "square", "tall", "wide", "compact")


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _data():
    base = timezone.now() - timedelta(days=30)
    img = [{"url": "/media/categories/c.png", "is_primary": True}]
    for i, (slug, name) in enumerate(
        (("brot", "Brot"), ("kuchen", "Kuchen"), ("kaffee", "Kaffee"), ("torten", "Torten"))
    ):
        cat = CategoryFactory(slug=slug, name={"de": name}, images=img if i % 2 == 0 else [])
        p = ProductFactory(name={"de": f"{name} 1"}, category=cat, base_price=3 + i)
        type(p).objects.filter(pk=p.pk).update(created_at=base + timedelta(hours=i))


def _section(style):
    _data()
    row = {"key": "categories", "enabled": True, **({"style": style} if style else {})}
    request = RequestFactory().get("/")
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = TenantFactory.build(
        name="Laden X", business_type="bakery", site_config={"sections": [row]}
    )
    html = public_views.storefront_home(request).content.decode()
    start = html.find('data-edit="section_titles.categories"')
    assert start != -1, "секции «Kategorien» нет"
    start = html.rfind("<section", 0, start)
    end = html.find("</section>", start) + len("</section>")
    return _g._normalize(html[start:end])


@pytest.mark.parametrize("style", STYLES)
def test_home_categories_section_looks_as_before(style):
    got = _section(style)
    path = GOLDEN / f"home-categories-{style or 'standard'}.html"
    if UPDATE or not path.exists():
        if not UPDATE:
            pytest.fail(f"нет снимка {path.name}: FB32_GOLDEN=update")
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(got)
        return
    assert got == path.read_text(), f"секция «Kategorien» изменилась: {path.name}"


# ── S5b: виды каталога на главной ────────────────────────────────────────────────


def _home(style):
    row = {"key": "categories", "enabled": True, "style": style}
    request = RequestFactory().get("/")
    request.session = import_module(dj_settings.SESSION_ENGINE).SessionStore()
    request.tenant = TenantFactory.build(
        name="Laden X", business_type="bakery", site_config={"sections": [row]}
    )
    return public_views.storefront_home(request).content.decode()


def test_regale_index_wegweiser_render_the_catalog_partials_on_home():
    _data()
    html = _home("regale")
    assert 'data-cat-style="regale"' in html and 'data-shelf="brot"' in html
    assert "Brot 1" in html, "полка показывает товары"
    html = _home("index")
    assert 'data-cat-style="index"' in html and "/sortiment/kuchen/" in html
    html = _home("wegweiser")
    assert 'data-cat-style="wegweiser"' in html and 'id="ww-home-deps-h"' in html
    assert 'id="ww-deps-h"' not in html, "свой id заголовка — без дубля с каталогом"
    section = html[html.find('data-edit="section_titles.categories"') :]
    section = section[: section.find("</section>")]
    assert "data-grid-view" not in section, "у видов каталога переключателя сетки нет"


def test_home_regale_queries_do_not_grow_with_departments(django_assert_max_num_queries):
    from apps.catalog import category_views
    from apps.catalog.models import Category

    _data()
    roots = list(Category.objects.filter(parent__isnull=True))
    with django_assert_max_num_queries(4 + len(roots)):
        shelves = category_views.shelves(roots)
    assert len(shelves) == 4


def test_section_style_registry_and_list_block_keep_their_scope():
    from apps.core import block_views
    from apps.tenants import siteconfig

    assert {"regale", "index", "wegweiser"} <= set(siteconfig.SECTION_STYLES["categories"])
    assert siteconfig.LIST_STYLES["categories"] == siteconfig.SECTION_STYLES["categories"]
    off = {u["key"] for u in block_views.unavailable(block_views.HOME)}
    assert off == {"tabs", "side"}, "на главной недоступны только «Reiter» и «Seitenspalte»"


# ── FB-32: виды каталога у блока «Liste» (источник «Kategorien») ─────────────────


def test_list_block_draws_catalog_views_with_the_shared_builder():
    from django.template.loader import render_to_string

    from apps.core import list_blocks

    _data()
    request = RequestFactory().get("/")
    request.tenant = TenantFactory.build(business_type="bakery", site_config={})
    for style, marker in (
        ("regale", 'data-shelf="brot"'),
        ("index", "/sortiment/kuchen/"),
        ("wegweiser", 'id="ww-lb-b7-h"'),
    ):
        block = {"source": "categories", "style": style}
        assert list_blocks.resolve({}, block)["cat_view"], style
        html = render_to_string(
            "storefront/sections/_block_list.html",
            {"block": block, "block_id": "b7", "request": request},
        )
        assert f'data-cat-style="{style}"' in html and marker in html, style


def test_list_block_tile_forms_have_no_catalog_view_and_skip_db_work():
    from apps.core import list_blocks

    _data()
    for style in ("", "square", "compact"):
        lb = list_blocks.resolve({}, {"source": "categories", "style": style})
        assert lb["cat_view"] == {}, style


def test_list_block_panel_hides_layout_fields_for_catalog_views(rf):
    from apps.core import list_panel

    request = rf.get("/")
    request.tenant = TenantFactory.build(business_type="bakery", site_config={})

    def names(style):
        groups = list_panel.groups(request, {}, {"source": "categories", "style": style})
        return {f["name"] for g in groups for f in g["fields"]}

    assert {"out", "cols", "rows"} <= names("square")
    assert not {"out", "cols", "rows"} & names("wegweiser")
    assert "style" in names("wegweiser")


def test_list_block_catalog_view_heading_id_is_never_empty():
    from django.template.loader import render_to_string

    _data()
    request = RequestFactory().get("/")
    request.tenant = TenantFactory.build(business_type="bakery", site_config={})
    block = {"source": "categories", "style": "wegweiser"}
    html = render_to_string(
        "storefront/sections/_block_list.html", {"block": block, "request": request}
    )
    assert 'id="ww-lb--h"' not in html and 'id="ww-lb-categories-h"' in html


def test_picked_categories_keep_subcategory_products_on_their_shelves():
    from apps.catalog.models import Category
    from apps.core import list_blocks

    _data()
    root = Category.objects.get(slug="brot")
    child = CategoryFactory(slug="brot-hell", name={"de": "Hell"}, parent=root)
    ProductFactory(name={"de": "Helles Brot"}, category=child, base_price=2)
    block = {"source": "categories", "style": "regale", "category": "brot", "pick": [root.pk]}
    shelves = list_blocks.resolve({}, block)["cat_view"]["shelves"]
    names = [str(p.name) for s in shelves for p in s["items"]]
    assert any("Helles" in n for n in names), names
