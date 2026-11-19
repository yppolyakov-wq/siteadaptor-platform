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

# FB-31.7 B3b: модуль проверяет отрисовку по старым кодам шаблонов (до B4) — см. conftest
LEGACY_CODES = True

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
    # FB-33 M2d: строка «Seitentitel» — сразу под фото-шапкой (заголовок страницы)
    rows = [r for r in site_schema.blocks_for(cfg, "promos") if r["key"] != "page_title"]
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


def test_review_grouping_change_alone_counts_as_a_draft_change():
    from apps.core import aufbau_draft

    saved = {"items": [{"key": "main"}]}
    draft = {"items": [{"key": "main", "grouping": "ohne"}]}
    assert aufbau_draft.changes(saved, draft) == 1


def test_review_object_panel_shows_what_the_storefront_draws():
    promo = Promotion.objects.create(
        title={"de": "Brot"}, status="active", promo_type="discount", page_style="plakat"
    )
    host = f"promo:{promo.pk.hex}"
    cfg = siteconfig.normalize({"page_blocks": {host: [{"key": "text", "id": "t1", "data": {}}]}})
    rows = site_schema.blocks_for(cfg, f"promo@{host}")
    offer = next(r for r in rows if r["key"] == "offer")
    assert offer["catview"]["value"] == "plakat", "свой шаблон акции, как на витрине"


def test_review_detail_template_setting_is_replaced_on_its_own_row():
    assert "promo_detail_style" not in site_schema.setting_codes(_shop(), "promo")


def test_review_prospekt_view_does_not_need_groups():
    tenant = _shop()  # без групп
    b = Browser(tenant)
    b.post(seite="promos", op="mainview", ref="main", value="prospekt")
    b.post(seite="promos", op="save")
    assert {"key": "main", "style": "prospekt"} in _saved(tenant)


# ── R6b: выбор страниц групп акций ──


def test_selector_has_all_groups_and_each_live_group():
    _groups()
    tenant = _shop()
    cfg = siteconfig.normalize(tenant.site_config)
    labels = {lab: [r.label for r in rows] for lab, rows in site_schema.type_groups(tenant, cfg)}
    assert "Alle Angebotsgruppen" in labels["Aktionen"]
    assert sorted(labels["Angebotsgruppen"]) == ["Räumung", "Wochenangebote"]


def test_ghost_group_host_is_refused():
    _groups()
    real = siteconfig.promo_group_host("Wochenangebote")
    assert site_schema.host_for(f"promo_group@{real}") == real
    ghost = siteconfig.promo_group_host("Gibt es nicht")
    assert site_schema.host_for(f"promo_group@{ghost}") == ""


def test_all_groups_first_save_copies_the_overview_blocks_and_sets_views():
    _groups()
    text = {"key": "text", "id": "t-o", "data": {"title": "Aus Aktionen", "body": "x"}}
    tenant = _shop(
        page_blocks={"promos": [{"key": "groups", "style": "tabs"}, text, {"key": "main"}]}
    )
    b = Browser(tenant)
    assert "t-o" in b.get("?seite=promo_group"), "до сохранения — блоки обзора"
    b.post(seite="promo_group", op="catview", ref="page_head", value="countdown")
    b.post(seite="promo_group", op="mainview", ref="main", value="vergleich")
    b.post(seite="promo_group", op="save")
    rows = _saved(tenant, "promo_group")
    assert [r.get("id") for r in rows if r.get("id")] == ["t-o"], "копия своих блоков"
    assert {"key": "page_head", "enabled": True, "style": "countdown"} in rows
    assert {"key": "main", "style": "vergleich"} in rows
    assert not any(r.get("key") == "groups" for r in rows), "строки обзора группе чужие"


def test_own_group_row_reads_the_group_view():
    _groups()
    host = siteconfig.promo_group_host("Wochenangebote")
    cfg = siteconfig.normalize({"promo_groups": {"Wochenangebote": {"style": "prospekt"}}})
    rows = site_schema.blocks_for(cfg, f"promo_group@{host}", host=host)
    head = next(r for r in rows if r["key"] == "page_head")
    assert head["catview"]["value"] == "prospekt"


def test_group_settings_live_on_their_own_rows():
    tenant = _shop()
    assert "promo_group_style" not in site_schema.setting_codes(tenant, "promo_group")
    assert not site_schema.SETTINGS_FOLLOWERS


def test_own_group_page_opens_and_saves_its_own_view():
    _groups()
    host = siteconfig.promo_group_host("Räumung")
    tenant = _shop()
    b = Browser(tenant)
    assert 'data-schema-block="page_head"' in b.get(f"?seite=promo_group@{host}")
    b.post(seite=f"promo_group@{host}", op="catview", ref="page_head", value="prospekt")
    b.post(seite=f"promo_group@{host}", op="save")
    assert {"key": "page_head", "enabled": True, "style": "prospekt"} in _saved(tenant, host)


def test_review_paused_group_keeps_its_own_schema_reachable():
    _groups()
    Promotion.objects.filter(group="Räumung").update(status="paused")
    host = siteconfig.promo_group_host("Räumung")
    assert site_schema.host_for(f"promo_group@{host}") == host, "сезонная группа не пропадает"


def test_review_own_group_emptied_stays_saved():
    host = siteconfig.promo_group_host("X")
    assert siteconfig.normalize_page_blocks({host: []}) == {host: []}
