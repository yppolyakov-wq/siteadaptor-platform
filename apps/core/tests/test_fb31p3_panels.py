"""FB-31 P3 R5: страницы акций в «Seitenaufbau» — закреплённые строки шапки, групп и
«Angebot» с плитками вида, вид и абзацы ★ «Aktionen» (как блоки каталога FB-30.16)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core import site_schema
from apps.core.modules import default_disabled_for
from apps.core.tests.test_fb27_r2_draft import Browser
from apps.promotions.models import Promotion
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _shop(**cfg):
    return TenantFactory(
        business_type="online_shop",
        disabled_modules=list(default_disabled_for("online_shop")),
        site_config=cfg,
    )


def _groups():
    for g in ("Wochenangebote", "Räumung"):
        Promotion.objects.create(
            title={"de": g},
            group=g,
            status="active",
            promo_type="discount",
            price_override=Decimal("2.49"),
            compare_at_price=Decimal("3.49"),
            ends_at=timezone.now() + timedelta(days=3),
        )


def _saved(tenant, host="promos"):
    tenant.refresh_from_db()
    return (siteconfig.normalize(tenant.site_config).get("page_blocks") or {}).get(host) or []


def test_overview_rows_are_pinned_in_storefront_order():
    cfg = siteconfig.normalize({"promo_page_style": "tabs"})
    rows = site_schema.blocks_for(cfg, "promos")
    keys = [r["key"] for r in rows]
    assert keys[:3] == ["page_head", "groups", "main"], "шапка первой, группы над ★"
    head, groups, main = rows[:3]
    assert head["pinned"] and head["catview"]["value"] == "aus"
    assert groups["catview"]["value"] == "tabs", "вид из шаблона"
    assert main["mainview"]["value"] == "raster" and main["groupview"]["value"] == "auto"
    assert str(groups["label"]) == "Angebotsgruppen"


def test_owner_picks_views_and_they_are_saved_as_rows():
    _groups()
    tenant = _shop()
    b = Browser(tenant)
    b.post(seite="promos", op="catview", ref="groups", value="tabs")
    b.post(seite="promos", op="catview", ref="page_head", value="titelbild")
    b.post(seite="promos", op="mainview", ref="main", value="prospekt")
    b.post(seite="promos", op="maingroup", ref="main", value="ohne")
    b.post(seite="promos", op="save")
    rows = _saved(tenant)
    assert {"key": "groups", "enabled": True, "style": "tabs"} in rows
    assert {"key": "page_head", "enabled": True, "style": "titelbild"} in rows
    assert {"key": "main", "style": "prospekt", "grouping": "ohne"} in rows


def test_foreign_and_unavailable_views_are_refused():
    tenant = _shop()  # без групп: навигационные виды недоступны
    b = Browser(tenant)
    for op, ref, value in (
        ("catview", "groups", "wegweiser"),
        ("mainview", "main", "mosaik"),
        ("maingroup", "main", "x"),
        ("catview", "groups", "tabs"),
    ):
        b.post(seite="promos", op=op, ref=ref, value=value)
    b.post(seite="promos", op="save")
    assert _saved(tenant) == []


def test_pinned_rows_cannot_move_or_hide():
    b = Browser(_shop())
    for op in ("up", "down", "toggle"):
        b.post(seite="promos", op=op, ref="groups")
    b.post(seite="promos", op="save")
    assert _saved(b.tenant) == []


def test_detail_has_the_pinned_offer_row_first():
    tenant = _shop(site_defaults={"promo_detail_style": "kompakt"})
    rows = site_schema.blocks_for(siteconfig.normalize(tenant.site_config), "promo")
    assert rows[0]["key"] == "offer" and rows[0]["catview"]["value"] == "kompakt"
    b = Browser(tenant)
    b.post(seite="promo", op="catview", ref="offer", value="plakat")
    b.post(seite="promo", op="save")
    assert _saved(tenant, "promo_detail") == [{"key": "offer", "enabled": True, "style": "plakat"}]


def test_template_settings_are_replaced_by_the_blocks():
    codes = site_schema.setting_codes(_shop(), "promos")
    assert "promo_page_style" not in codes and "promo_detail_style" not in codes
