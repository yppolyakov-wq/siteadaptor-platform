"""FB-30.16 R4: блоки каталога в «Seitenaufbau» — «Kategorien» прикреплён к ★, вид
категорий и вид товаров меняются операциями панели и доходят до витрины."""

import pytest

from apps.catalog import catalog_parts as cp
from apps.core import site_schema
from apps.tenants import siteconfig


def _with_subcategories():
    from apps.catalog.tests.factories import CategoryFactory

    parent = CategoryFactory(slug="r4-brot", name={"de": "Brot"})
    CategoryFactory(slug="r4-weizen", name={"de": "Weizen"}, parent=parent)


def _items():
    return siteconfig.main_list_sequence("catalog", [])


def test_catalog_shows_a_categories_row_right_above_the_list():
    """R4/R5b (осознанно расширен): шапка первой, «Kategorien» прямо над ★, сеты под ★."""
    rows = _items()
    assert [r["key"] for r in rows] == ["page_head", "categories", "main", "combos"]
    own = {"key": "text", "id": "t1"}
    rows = siteconfig.main_list_sequence("catalog", [{"key": "main"}, own])
    assert [r.get("id") or r["key"] for r in rows] == [
        "page_head",
        "categories",
        "main",
        "combos",
        "t1",
    ]
    rows = siteconfig.main_list_sequence("catalog", [own, {"key": "categories"}, {"key": "main"}])
    assert [r.get("id") or r["key"] for r in rows] == [
        "page_head",
        "t1",
        "categories",
        "main",
        "combos",
    ]
    rows = siteconfig.main_list_sequence("catalog", [{"key": "combos", "style": "above"}])
    assert [r["key"] for r in rows] == ["page_head", "combos", "categories", "main"]
    assert [r["key"] for r in siteconfig.main_list_sequence("services", [])] == ["main"]


def test_category_view_op_sets_the_view_and_pinned_row_does_not_move():
    items = _items()
    site_schema.mutate(items, "catalog", "catview", "categories", value="regale")
    assert cp.effective({"page_blocks": {"catalog": items}}, "catalog").categories == "regale"
    for op in ("toggle", "up", "down", "width"):
        with pytest.raises(site_schema.SchemaError):
            site_schema.mutate(_items(), "catalog", op, "categories", value="half")
    with pytest.raises(site_schema.SchemaError):
        site_schema.mutate(_items(), "catalog", "catview", "categories", value="gold")


def test_auto_beats_the_template_code():
    items = _items()
    site_schema.mutate(items, "catalog", "catview", "categories", value="auto")
    cfg = {
        "page_blocks": {"catalog": siteconfig.normalize_page_blocks({"catalog": items})["catalog"]}
    }
    assert cp.effective(cfg, "catalog", code="regale").categories == ""


def test_main_view_op_sets_style_and_grid_hint_and_raster_beats_the_code():
    items = _items()
    site_schema.mutate(items, "catalog", "mainview", "main", value="mosaik")
    marker = next(i for i in items if i["key"] == "main")
    assert marker["style"] == "mosaik" and marker["grid"] == "cols4"
    site_schema.mutate(items, "catalog", "mainview", "main", value="raster")
    cfg = {"page_blocks": siteconfig.normalize_page_blocks({"catalog": items})}
    parts = cp.effective(cfg, "catalog", code="mosaik")
    assert parts.products == "" and parts.grid == ""
    with pytest.raises(site_schema.SchemaError):
        site_schema.mutate(
            siteconfig.main_list_sequence("services", []),
            "services",
            "mainview",
            "main",
            value="mosaik",
        )


@pytest.mark.django_db
def test_screen_panels_change_the_shop(settings):
    """Экран: блок «Kategorien» и ★ каталога открывают плитки вида; выбор через черновик и
    «Speichern» доходит до витрины; плиток «Seitenvorlage» в ★ больше нет."""
    from apps.core.modules import default_disabled_for
    from apps.core.tests.test_fb27_r2_draft import Browser
    from apps.tenants.tests.factories import TenantFactory

    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(
        business_type="online_shop", disabled_modules=list(default_disabled_for("online_shop"))
    )
    _with_subcategories()
    b = Browser(tenant)
    html = b.get("?seite=catalog")
    assert "block=categories" in html and "Kategorien" in html
    cat = b.get("?seite=catalog&block=categories")
    assert 'data-schema-view-tiles="catview"' in cat and 'value="regale"' in cat
    main = b.get("?seite=catalog&block=main")
    assert 'data-schema-view-tiles="mainview"' in main
    assert 'data-schema-setting-box="catalog_page_style"' not in main
    b.post(seite="catalog", op="catview", ref="categories", value="tabs")
    b.post(seite="catalog", op="mainview", ref="main", value="mosaik")
    resp, msgs = b.post(seite="catalog", op="save")
    tenant.refresh_from_db()
    cfg = siteconfig.normalize(tenant.site_config)
    parts = cp.effective(cfg, "catalog")
    assert parts.categories == "tabs" and parts.products == "mosaik", msgs


def test_review_hidden_row_comes_back_and_template_choice_drops_views():
    items = [{"key": "categories", "style": "regale", "enabled": False}, {"key": "main"}]
    site_schema.mutate(items, "catalog", "catview", "categories", value="tabs")
    assert items[0]["enabled"] is True
    cfg = {
        "catalog_page_style": "mosaik",
        "page_blocks": {
            "catalog": [{"key": "categories", "style": "tabs"}, {"key": "main", "style": "raster"}]
        },
    }
    from apps.core import page_settings

    out = page_settings.apply_override(cfg, "catalog_page_style", "regale")
    assert cp.effective(siteconfig.normalize(out), "catalog", code="regale") == cp.from_code(
        "regale"
    )


@pytest.mark.django_db
def test_review_draft_counts_a_view_change(settings):
    from apps.core.modules import default_disabled_for
    from apps.core.tests.test_fb27_r2_draft import Browser
    from apps.tenants.tests.factories import TenantFactory

    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(
        business_type="online_shop", disabled_modules=list(default_disabled_for("online_shop"))
    )
    _with_subcategories()
    b = Browser(tenant)
    b.post(seite="catalog", op="catview", ref="categories", value="regale")
    html = b.get("?seite=catalog")
    assert "Änderungen: 1" in html or "Änderung: 1" in html or "1 Änderung" in html


def test_r5b_head_and_sets_rows_change_their_axis_only():
    items = _items()
    site_schema.mutate(items, "catalog", "catview", "page_head", value="titelbild")
    site_schema.mutate(items, "catalog", "catview", "combos", value="above")
    cfg = {"page_blocks": siteconfig.normalize_page_blocks({"catalog": items})}
    parts = cp.effective(cfg, "catalog", code="regale")
    assert parts.head == "titelbild" and parts.sets == "above" and parts.categories == "regale"
    with pytest.raises(site_schema.SchemaError):
        site_schema.mutate(_items(), "catalog", "catview", "page_head", value="above")


@pytest.mark.django_db
def test_r5b_sets_row_only_when_sets_exist():
    cfg = siteconfig.normalize({})
    keys = [b["key"] for b in site_schema.blocks_for(cfg, "catalog")]
    assert "page_head" in keys and "combos" not in keys


@pytest.mark.django_db
def test_review_r5b_unavailable_view_is_refused_server_side(settings):
    """Без подкатегорий «Regale» недоступен — и в обход плиток POST'ом тоже."""
    from apps.core.modules import default_disabled_for
    from apps.core.tests.test_fb27_r2_draft import Browser
    from apps.tenants.tests.factories import TenantFactory

    settings.ROOT_URLCONF = "config.urls_tenant"
    tenant = TenantFactory(
        business_type="online_shop", disabled_modules=list(default_disabled_for("online_shop"))
    )
    b = Browser(tenant)
    _resp, msgs = b.post(seite="catalog", op="catview", ref="categories", value="regale")
    b.post(seite="catalog", op="save")
    tenant.refresh_from_db()
    parts = cp.effective(siteconfig.normalize(tenant.site_config), "catalog")
    assert parts.categories == "", msgs
