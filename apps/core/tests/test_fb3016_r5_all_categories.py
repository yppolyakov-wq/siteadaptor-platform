"""FB-30.16 R5a: страница «Alle Kategorien» — свои общие блоки страниц категорий.
Пока не сохранена, показывает блоки каталога; первое сохранение пишет копию (решение
владельца); витрина категорий без своей схемы берёт её блоки и вид."""

import pytest

from apps.catalog import catalog_parts as cp
from apps.core import site_schema
from apps.core.modules import default_disabled_for
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
TEXT = {"key": "text", "id": "t-cat", "data": {"title": "Aus dem Katalog", "body": "x"}}


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _shop(**cfg):
    return TenantFactory(
        business_type="online_shop",
        disabled_modules=list(default_disabled_for("online_shop")),
        site_config=cfg,
    )


def test_selector_offers_all_categories_and_catalog_no_longer_carries_category_settings():
    tenant = _shop()
    cfg = siteconfig.normalize(tenant.site_config)
    codes = [r.code for _l, rows in site_schema.type_groups(tenant, cfg) for r in rows]
    assert "category" in codes and "catalog" in codes
    assert "category_page_style" not in site_schema.setting_codes(tenant, "catalog")
    assert "catalog_subcats" in site_schema.setting_codes(tenant, "category")


def test_unsaved_page_shows_the_catalog_blocks_and_first_save_copies_them():
    tenant = _shop(page_blocks={"catalog": [TEXT, {"key": "main"}]})
    b = Browser(tenant)
    html = b.get("?seite=category")
    assert "t-cat" in html, "до сохранения — блоки каталога"
    b.post(seite="category", op="catview", ref="categories", value="regale")
    b.post(seite="category", op="save")
    tenant.refresh_from_db()
    blocks = siteconfig.normalize(tenant.site_config)["page_blocks"]
    assert [r.get("id") for r in blocks["category"] if r.get("id")] == ["t-cat"], "копия"
    assert cp.effective({"page_blocks": blocks}, "category").categories == "regale"
    assert cp.effective({"page_blocks": blocks}, "catalog").categories == "", "каталог не тронут"


def test_category_pages_use_the_shared_blocks_until_they_have_their_own():
    cfg = {
        "page_blocks": {"catalog": [TEXT], "category": [{"key": "main"}, {**TEXT, "id": "t-all"}]}
    }
    assert siteconfig.shared_category_host(siteconfig.normalize(cfg)) == "category"
    assert siteconfig.shared_category_host({}) == "catalog"


def test_review_empty_all_categories_stays_saved_and_adopt_copies_the_shared_blocks():
    cfg = siteconfig.normalize({"page_blocks": {"catalog": [TEXT], "category": []}})
    assert cfg["page_blocks"]["category"] == []
    assert siteconfig.shared_category_host(cfg) == "category"
    cfg = siteconfig.normalize(
        {
            "page_blocks": {
                "catalog": [TEXT],
                "category": [{**TEXT, "id": "t-all", "data": {"title": "Alle", "body": "x"}}],
            }
        }
    )
    items = site_schema.category_items(cfg, "catalog:brot", [], "adopt")
    # копия получает новые id; источник — «Alle Kategorien», не каталог
    assert [i["data"]["title"] for i in items if i.get("id")] == ["Alle"]


def test_review_panel_before_first_save_shows_the_template_view():
    tenant = _shop(
        site_defaults={"category_page_style": "regale"},
        page_blocks={"catalog": [{"key": "categories", "style": "tabs"}, {"key": "main"}]},
    )
    cfg = siteconfig.normalize(tenant.site_config)
    row = next(b for b in site_schema.blocks_for(cfg, "category") if b["key"] == "categories")
    assert row["catview"]["value"] == "regale"
