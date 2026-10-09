"""LB-4c: одни виды везде — блок «Liste» умеет виды секций главной.

План — `docs/lb4-home-lists-archetypes-plan-2026-10-04.md` §6/§11. Замки ДО кода:
реестр видов блока = реестр видов секции его источника (`SECTION_STYLES`), вид хранится
presence-minimal и только у источника, у которого он есть; блок рисует ту же композицию,
что секция (прайс-лист с ЕГО фильтром, spotlight/banner/rows акций, строки категорий,
формы плиток); Студия предлагает вид по источнику; копия встроенного списка уносит вид.
"""

import itertools
import re
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.models import Category, Product
from apps.core.tests.test_list_block_sources import _block, _builder_html, _home, _row, _tenant
from apps.core.tests.test_stu12_groups import TPL, _post_builder, _segment
from apps.promotions.models import Promotion
from apps.tenants import siteconfig

pytestmark = pytest.mark.django_db

_N = itertools.count()


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _block_html(body, block_id):
    i = body.index(f'id="lb-{block_id}"')
    return body[i : body.index("</section>", i)]


def _cat(name, slug, order, parent=None):
    return Category.objects.create(
        name={"de": name}, slug=slug, sort_order=order, is_active=True, parent=parent
    )


def _product(name, cat, price="3.00"):
    return Product.objects.create(
        name={"de": name}, base_price=Decimal(price), category=cat, is_active=True
    )


def _promo(title, days_left=10, pct=20):
    return Promotion.objects.create(
        title={"de": title},
        status="active",
        discount_percent=pct,
        ends_at=timezone.now() + timedelta(days=days_left),
    )


# ───────────────────────────── данные ─────────────────────────────


def test_block_styles_are_the_styles_of_the_sources_section():
    assert siteconfig.LIST_STYLES == {
        "products": siteconfig.SECTION_STYLES["products"],
        "promotions": siteconfig.SECTION_STYLES["promotions"],
        "categories": siteconfig.SECTION_STYLES["categories"],
    }


def test_block_keeps_a_style_only_of_its_own_source():
    clean = lambda **d: siteconfig._clean_cblock_data("list", d)  # noqa: E731
    assert clean(source="products", style="preisliste_karte")["style"] == "preisliste_karte"
    assert "style" not in clean(source="products", style="spotlight")
    assert clean(source="promotions", style="rows")["style"] == "rows"
    assert clean(source="categories", style="compact")["style"] == "compact"
    assert "style" not in clean(source="services", style="preisliste")
    assert "style" not in clean(source="products")  # presence-minimal


def test_builtin_row_keeps_its_style_on_the_row_not_in_data():
    raw = {"key": "products", "style": "preisliste", "data": {"style": "preisliste_foto"}}
    row = next(
        s for s in siteconfig.normalize({"sections": [raw]})["sections"] if s["key"] == "products"
    )
    assert row["style"] == "preisliste"
    assert "data" not in row


# ───────────────────────────── рендер ─────────────────────────────


def test_price_list_block_shows_only_its_category_as_a_price_list():
    brot = _cat("Brot", "brot", 1)
    kuchen = _cat("Kuchen", "kuchen", 2)
    _product("Roggenbrot", brot)
    _product("Apfelkuchen", kuchen)
    block = _block(source="products", category="kuchen", style="preisliste")
    html = _block_html(_home(_tenant([block])), block["id"])
    assert "data-price-list" in html
    assert "Apfelkuchen" in html and "Roggenbrot" not in html
    assert 'href="/sortiment/kuchen/"' in html  # «Ganze Speisekarte» — с тем же фильтром


def test_price_list_block_offers_the_visitor_view_toggle_with_its_own_key():
    _product("Roggenbrot", _cat("Brot", "brot", 1))
    block = _block(source="products", style="preisliste_foto")
    html = _block_html(_home(_tenant([block])), block["id"])
    assert "data-plv-btn" in html
    assert f'data-plv-key="lb-{block["id"]}"' in html  # своя память вида, не общая с секцией


def test_promo_block_spotlight_banner_and_rows():
    for i in range(5):
        _promo(f"Deal {i}", days_left=1 if i == 0 else 20)
    spot = _block(source="promotions", style="spotlight")
    banner = _block(source="promotions", style="banner")
    rows = _block(source="promotions", style="rows")
    body = _home(_tenant([spot, banner, rows]))
    s = _block_html(body, spot["id"])
    assert "data-promo-spotlight" in s and "data-promo-side" in s
    assert "data-promo-ending" in s  # чипы «Ending soon» — из выборки блока
    b = _block_html(body, banner["id"])
    assert "data-promo-hero" in b and "data-promo-side" not in b  # первая — широкой картой
    assert "data-promo-rows" in _block_html(body, rows["id"])


def test_categories_block_compact_rows_and_tile_shapes():
    brot = _cat("Brot", "brot", 1)
    brot.images = [{"id": "a", "url": "/media/categories/a.png", "is_primary": True}]
    brot.save(update_fields=["images"])  # форма плитки — у фото-плитки (без фото — чип)
    _product("Roggenbrot", brot, price="3.20")
    compact = _block(source="categories", style="compact")
    square = _block(source="categories", style="square")
    body = _home(_tenant([compact, square]))
    rows = _block_html(body, compact["id"])
    assert "Brot" in rows and "3,20" in rows  # строка «фото · имя · ab-цена»
    assert "aspect-square" in _block_html(body, square["id"])


# ───────────────────────────── Студия ─────────────────────────────


def test_editor_offers_the_style_of_each_source():
    block = _block(source="products", style="preisliste_karte")
    row = _row(_builder_html(_tenant([block])), block["id"])
    i = row.index(f'name="cb_{block["id"]}_style"')
    select = row[i : row.index("</select>", i)]
    assert re.search(r'value="preisliste_karte"[^>]*selected', select)
    assert (
        'value="spotlight"' in select and 'value="compact"' in select
    )  # опции других источников — в DOM (W0)
    assert 'data-lb-src="products promotions categories"' in row[:i]


def test_style_reaches_save_and_the_live_draft():
    draft = set(re.findall(r'"(\w+)"', _segment(TPL.read_text("utf-8"), "var CB_DATA_FIELDS", "]")))
    assert "style" in draft
    tenant = _tenant(
        [{"key": "list", "id": "st1", "enabled": True, "data": {"source": "products"}}]
    )
    cfg = _post_builder(
        tenant,
        {
            "cb_id": "st1",
            "cb_type_st1": "list",
            "enabled_cb_st1": "on",
            "order_cb_st1": "1",
            "cb_st1_source": "products",
            "cb_st1_style": "preisliste_kompakt",
        },
    )
    block = next(s for s in cfg["sections"] if s.get("id") == "st1")
    assert block["data"]["style"] == "preisliste_kompakt"


def test_copy_of_a_builtin_list_keeps_its_style():
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(
        slug="lb4ccopy",
        name="LB4C",
        disabled_modules=[],
        site_config={"sections": [{"key": "products", "enabled": True, "style": "preisliste"}]},
    )
    cfg = _post_builder(tenant, {"action": "copy_builtin:products"})
    keys = [s["key"] for s in cfg["sections"]]
    block = cfg["sections"][keys.index("products") + 1]
    assert block["key"] == "list" and block["data"]["style"] == "preisliste"
