"""FB-27 R1: экран «Seitenaufbau» — схема страницы рядами, выбор типа по бизнесу.

Решения владельца (2026-11-11): типы страниц только те, что есть у бизнеса, главное
первым; блоки — схемой рядами (узкие соседи в одном ряду); скрытые отдельно; скрыть и
удалить — разные действия; Студия — кнопкой «Auf der Seite bearbeiten».
"""

from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import page_settings, site_schema
from apps.core.modules import default_disabled_for
from apps.core.site_schema_views import site_schema_view
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _request(method, tenant, data=None, query=""):
    req = getattr(RequestFactory(), method)("/dashboard/site/aufbau/" + query, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return req


def _biz(business_type):
    """Тенант с модулями своего типа бизнеса (фабрика по умолчанию включает все)."""
    return TenantFactory(
        business_type=business_type, disabled_modules=list(default_disabled_for(business_type))
    )


def _codes(tenant):
    cfg = siteconfig.normalize(tenant.site_config)
    return [r.code for _label, rows in site_schema.type_groups(tenant, cfg) for r in rows]


@pytest.mark.parametrize("business_type", ["online_shop", "hotel", "friseur", "events"])
def test_only_page_types_of_this_business_are_offered(business_type):
    tenant = _biz(business_type)
    codes = _codes(tenant)
    assert codes[0] == "home"
    for code in codes:
        base = code.split("@", 1)[0]
        assert page_settings.type_active(tenant, base), (business_type, code)
    inactive = [
        c
        for c in ("services", "stays", "events", "catalog", "blog", "anfrage")
        if not page_settings.type_active(tenant, c)
    ]
    assert not set(inactive) & set(codes), (business_type, inactive)


def test_one_option_per_block_host():
    """«Katalog» и «Kategorie» правили одни и те же блоки двумя пунктами."""
    tenant = _biz("online_shop")
    codes = _codes(tenant)
    assert "catalog" in codes and "category" not in codes


def test_main_group_of_the_business_comes_first():
    hotel = _biz("hotel")
    cfg = siteconfig.normalize(hotel.site_config)
    groups = site_schema.type_groups(hotel, cfg)
    assert [r.code for r in groups[0][1]] == ["home"]
    assert any(r.code == "stays" for r in groups[1][1]), [g[0] for g in groups]


def test_text_pages_are_options_of_the_same_select():
    from apps.core.models import ContentPage

    tenant = _biz("online_shop")
    ContentPage.objects.create(slug="zahlung", title="Zahlungsarten", body="x", is_published=True)
    codes = _codes(tenant)
    assert "text" in codes and "text@seite:zahlung" in codes


def test_narrow_neighbours_share_a_row_and_hidden_blocks_are_listed_apart():
    cfg = siteconfig.normalize(
        {
            "page_blocks": {
                "info": [
                    {"id": "a1", "key": "text", "enabled": True, "width": "w12", "data": {}},
                    {"id": "a2", "key": "image", "enabled": True, "width": "w12", "data": {}},
                    {"id": "a3", "key": "text", "enabled": True, "data": {}},
                    {"id": "a4", "key": "text", "enabled": False, "data": {}},
                ]
            }
        }
    )
    layout = site_schema.schema_layout(site_schema.blocks_for(cfg, "text"))
    rows = [[b["ref"] for b in row] for row in layout["rows"]]
    assert ["a1", "a2"] in rows and ["a3"] in rows
    assert [b["ref"] for b in layout["hidden"]] == ["a4"]
    assert not any("a4" in row for row in rows)
    half = next(b for row in layout["rows"] for b in row if b["ref"] == "a1")
    assert half["width_label"] == "½"


def test_schema_rows_match_storefront_grouping():
    """Ряды схемы — та же группировка, что рисует витрина (`group_block_rows`)."""
    blocks = [
        {"id": f"b{i}", "key": "text", "enabled": True, "width": w, "data": {}}
        for i, w in enumerate(["w13", "w13", "w13", "contained", "w23", "w13"])
    ]
    cfg = siteconfig.normalize({"page_blocks": {"info": blocks}})
    stored = [b for b in cfg["page_blocks"]["info"] if b.get("id")]
    expected = [
        [x["id"] for x in g["row"]] if g.get("key") == "_row" else [g["id"]]
        for g in siteconfig.group_block_rows(stored)
    ]
    layout = site_schema.schema_layout(site_schema.blocks_for(cfg, "text"))
    got = [[b["ref"] for b in row] for row in layout["rows"] if not row[0]["fixed"]]
    assert got == expected


def test_screen_is_a_schema_with_select_and_no_embedded_page():
    tenant = _biz("online_shop")
    html = site_schema_view(_request("get", tenant)).content.decode()
    assert '<select name="seite"' in html and "<optgroup" in html
    assert "<iframe" not in html
    assert "data-schema-row" in html
    assert "Auf der Seite bearbeiten" in html
    assert "data-schema-pages" not in html  # строки пилюль больше нет


def test_selected_block_opens_panel_with_separate_hide_and_remove():
    tenant = _biz("online_shop")
    site_schema.apply(tenant, "text", "add", block_type="text")
    cfg = siteconfig.normalize(tenant.site_config)
    ref = next(b["ref"] for b in site_schema.blocks_for(cfg, "text") if b["cblock"])
    html = site_schema_view(
        _request("get", tenant, query=f"?seite=text&block={ref}")
    ).content.decode()
    assert "data-schema-panel" in html
    assert 'value="toggle"' in html and "Ausblenden" in html
    assert "entfernen=1" in html and 'value="delete"' not in html  # удаление — отдельным шагом
    confirm = site_schema_view(
        _request("get", tenant, query=f"?seite=text&block={ref}&entfernen=1")
    ).content.decode()
    assert 'value="delete"' in confirm and "Endgültig entfernen" in confirm


def test_action_keeps_the_block_selected():
    tenant = _biz("online_shop")
    site_schema.apply(tenant, "text", "add", block_type="text")
    cfg = siteconfig.normalize(tenant.site_config)
    ref = next(b["ref"] for b in site_schema.blocks_for(cfg, "text") if b["cblock"])
    resp = site_schema_view(_request("post", tenant, {"seite": "text", "op": "toggle", "ref": ref}))
    assert resp.status_code == 302
    assert "seite=text" in resp["Location"] and f"block={ref}" in resp["Location"]


def _without(module):
    return TenantFactory(
        business_type="online_shop",
        disabled_modules=sorted({*default_disabled_for("online_shop"), module}),
    )


def test_inactive_type_cannot_be_opened_by_address():
    tenant = _without("stays")
    assert not page_settings.type_active(tenant, "stays")
    html = site_schema_view(_request("get", tenant, query="?seite=stays")).content.decode()
    assert 'option value="home" selected' in html


def test_inactive_type_cannot_be_edited_by_post():
    """Экран не предлагает тип — значит и POST в обход экрана его не правит."""
    tenant = _without("stays")
    with pytest.raises(site_schema.SchemaError):
        site_schema.apply(tenant, "stays", "add", block_type="text")
    resp = site_schema_view(
        _request("post", tenant, {"seite": "stays", "op": "add", "type": "text"})
    )
    assert resp.status_code == 302
    tenant.refresh_from_db()
    blocks = siteconfig.normalize(tenant.site_config).get("page_blocks") or {}
    assert not blocks.get("stay_rooms")


def test_move_skips_hidden_neighbours():
    """Скрытый блок между двумя видимыми не «съедает» нажатие «Nach oben»."""
    tenant = _biz("online_shop")
    refs = [site_schema.apply(tenant, "text", "add", block_type="text") for _ in range(3)]
    site_schema.apply(tenant, "text", "toggle", ref=refs[1])
    site_schema.apply(tenant, "text", "up", ref=refs[2])
    cfg = siteconfig.normalize(tenant.site_config)
    visible = [
        b["ref"] for b in site_schema.blocks_for(cfg, "text") if b["enabled"] and b["cblock"]
    ]
    assert visible == [refs[2], refs[0]]
    first = next(b for b in site_schema.blocks_for(cfg, "text") if b["ref"] == refs[2])
    assert first["can_up"] is False and first["can_down"] is True


def test_new_block_is_selected_after_adding():
    tenant = _biz("online_shop")
    resp = site_schema_view(
        _request("post", tenant, {"seite": "text", "op": "add", "type": "text"})
    )
    assert "block=" in resp["Location"] and resp["Location"].endswith("#schema-panel")


def test_type_select_costs_no_query_per_text_page(django_assert_max_num_queries):
    from apps.core.models import ContentPage

    tenant = _biz("online_shop")
    for i in range(12):
        ContentPage.objects.create(slug=f"s{i}", title=f"Seite {i}", body="x", is_published=True)
    cfg = siteconfig.normalize(tenant.site_config)
    with django_assert_max_num_queries(8):
        site_schema.type_groups(tenant, cfg)


def test_page_type_changes_by_button_not_on_change():
    """WCAG 3.2.2: стрелки в списке на Windows шлют change — автоперехода нет."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    assert "submit()" not in (root / "static/js/aufbau.js").read_text()
    html = site_schema_view(_request("get", _biz("online_shop"))).content.decode()
    assert "Öffnen" in html
