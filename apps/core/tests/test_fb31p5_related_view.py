"""FB-31 P5 R7: вид «Ähnliche Produkte» — Automatisch · Raster · Slider, колонки, «Höchstens»
(решение владельца, `docs/fb31-p5-detail-plan-2026-11-16.md` §11, §13)."""

import re

import pytest

from apps.core import page_settings, site_schema
from apps.core.modules import default_disabled_for
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.core.tests.test_fb31p5_detail_golden import _req
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _page(cfg, related=8):
    from apps.catalog.tests.factories import CategoryFactory, ProductFactory
    from apps.promotions import public_views

    cat = CategoryFactory()
    p = ProductFactory(name={"de": "Bauernbrot"}, category=cat)
    for i in range(related):
        ProductFactory(name={"de": f"Brot {i}"}, category=cat)
    resp = public_views.product_detail(_req(f"/sortiment/{p.pk}/", cfg), pk=p.pk)
    return resp.content.decode(), None


def _strip(html):
    return "data-related-strip" in html


def _cards(html):
    start = html.find("More from this category")
    if start == -1:
        start = html.find("Mehr aus dieser Kategorie")
    assert start != -1, "раздела «Ähnliche» нет"
    return len(set(re.findall(r"Brot \d+", html[start:])))


# ── как сейчас (без выбора владельца — сайт прежний) ──


def test_without_a_choice_more_than_a_row_is_a_strip_and_a_row_is_a_grid():
    html, _ = _page({}, related=8)
    assert _strip(html), "8 похожих при 4 колонках — лента (DL-16.6)"
    html, _ = _page({}, related=3)
    assert not _strip(html)


def test_normalized_layout_has_no_new_keys_without_a_choice():
    lay = siteconfig.normalize({})["detail_related_layout"]
    assert "raster" not in lay and "max" not in lay and "scroll" not in lay


# ── хранение ──


def test_raster_and_max_survive_normalize_and_junk_is_dropped():
    norm = siteconfig.normalize
    lay = norm({"detail_related_layout": {"preset": "cols3", "raster": True, "max": 12}})
    assert lay["detail_related_layout"]["raster"] is True
    assert lay["detail_related_layout"]["max"] == 12
    junk = norm({"detail_related_layout": {"raster": "x", "max": 99}})["detail_related_layout"]
    assert junk.get("raster") is True or "raster" not in junk
    assert "max" not in junk
    both = norm({"detail_related_layout": {"raster": True, "scroll": True}})
    assert (
        both["detail_related_layout"].get("scroll")
        and "raster" not in both["detail_related_layout"]
    ), "оба — побеждает Slider"
    eight = norm({"detail_related_layout": {"max": 8}})["detail_related_layout"]
    assert "max" not in eight, "8 — как раньше, не хранится"
    assert siteconfig.related_mode(lay["detail_related_layout"]) == "raster"
    assert siteconfig.related_mode(both["detail_related_layout"]) == "slider"
    assert siteconfig.related_mode({}) == "auto"


def test_cabinet_writer_keeps_the_new_fields():
    cfg = page_settings.apply_override({}, "product_related", "cols3", {"raster": True, "max": "4"})
    lay = siteconfig.normalize(cfg)["detail_related_layout"]
    assert lay["cols"] == 3 and lay["raster"] is True and lay["max"] == 4
    again = page_settings.apply_override(cfg, "product_related", "cols3", None)
    assert siteconfig.normalize(again)["detail_related_layout"]["raster"] is True


def test_form_payload_reads_mode_and_max():
    payload = page_settings.output_payload({"out_mode": "raster", "out_max": "12"}, "out")
    assert payload == {"raster": True, "max": "12"}
    assert page_settings.output_payload({"out_mode": "auto"}, "out") == {}


# ── витрина ──


def test_raster_never_strips_and_shows_every_card():
    cfg = {"detail_related_layout": {"preset": "cols3", "raster": True}}
    html, _ = _page(cfg, related=8)
    assert not _strip(html)
    assert _cards(html) == 8, "Raster: «Höchstens 8» — все 8, неполный ряд не обрезается"


def test_slider_strips_even_within_a_row_and_max_limits():
    html, _ = _page({"detail_related_layout": {"scroll": True}}, related=3)
    assert "data-sf-slider" in html
    html, _ = _page({"detail_related_layout": {"max": 4}}, related=8)
    assert _cards(html) == 4 and not _strip(html), "4 при 4 колонках — один ряд сеткой"
    html, _ = _page({"detail_related_layout": {"max": 12}}, related=10)
    assert _cards(html) == 10 and _strip(html)


# ── «Seitenaufbau»: настройка на строке раздела ──


def _shop(**cfg):
    return TenantFactory(
        business_type="online_shop",
        disabled_modules=list(default_disabled_for("online_shop")),
        site_config=cfg,
    )


def test_setting_lives_on_the_related_row_not_on_the_page_row():
    tenant = _shop()
    cfg = siteconfig.normalize(tenant.site_config)
    page = [
        r["s"].code
        for g in site_schema.settings_groups(tenant, "product", cfg)
        for r in g["settings"]
    ]
    assert "product_related" not in page and "product_detail_layout" in page
    row = [
        r["s"].code
        for g in site_schema.settings_groups(tenant, "product", cfg, row="related")
        for r in g["settings"]
    ]
    assert row == ["product_related"]
    assert "block=related" in site_schema.settings_url("product", "product_related")
    html = Browser(tenant).get("?seite=product&block=related")
    assert "data-schema-related-view" in html and 'name="out_max"' in html


def test_owner_picks_raster_three_columns_twelve_and_saves():
    tenant = _shop()
    b = Browser(tenant)
    resp, _ = b.post(
        seite="product",
        ref="related",
        op="setting",
        setting="product_related",
        value="cols3",
        out_mode="raster",
        out_max="12",
    )
    assert resp.status_code == 302
    b.post(seite="product", op="save")
    tenant.refresh_from_db()
    lay = siteconfig.normalize(tenant.site_config)["detail_related_layout"]
    assert lay["cols"] == 3 and lay["raster"] is True and lay["max"] == 12


def test_draft_with_only_the_mode_changed_is_a_change():
    tenant = _shop(detail_related_layout={"preset": "cols4"})
    b = Browser(tenant)
    b.post(
        seite="product",
        ref="related",
        op="setting",
        setting="product_related",
        value="cols4",
        out_mode="raster",
    )
    b.post(seite="product", op="save")
    tenant.refresh_from_db()
    assert siteconfig.normalize(tenant.site_config)["detail_related_layout"].get("raster")


def test_review_special_preset_survives_a_mode_only_change():
    # ревью R7: вид «Liste» (колонок-кнопок нет) — смена одного «Wie» не роняет форму и
    # не подменяет вид сетки; ручные колонки не подменяются пресетом
    tenant = _shop(detail_related_layout={"preset": "list"})
    html = Browser(tenant).get("?seite=product&block=related")
    assert 'name="value" value="list"' in html
    view = site_schema.related_view(siteconfig.normalize(tenant.site_config))
    assert view["related_cols"] == "" and view["related_preset"] == "list"
    b = Browser(tenant)
    b.post(
        seite="product",
        ref="related",
        op="setting",
        setting="product_related",
        value="list",
        out_mode="raster",
        out_max="4",
    )
    b.post(seite="product", op="save")
    tenant.refresh_from_db()
    lay = siteconfig.normalize(tenant.site_config)["detail_related_layout"]
    assert lay["preset"] == "list" and lay["raster"] is True and lay["max"] == 4


def test_review_old_page_row_link_leads_to_the_related_row():
    from apps.core.site_schema_views import site_schema_view

    b = Browser(_shop())
    req = b._request("get", query="?seite=product&block=__page&offen=product_related")
    resp = site_schema_view(req)
    assert resp.status_code == 302 and "block=related" in resp["Location"]
