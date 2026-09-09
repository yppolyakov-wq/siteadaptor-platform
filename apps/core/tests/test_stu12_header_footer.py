"""STU-12c: шапка и подвал кликабельны — колонка «Kopf- & Fußzeile» (2B-снято, F6A).

ТЗ `docs/stu12-studio-simplification-plan-2026-09-09.md` §2 (12c): `<header>`/`<footer>`
витрины несут `data-sf-section` на ВСЕХ страницах → клик на канве открывает область
`menu` = пресет шапки + Feste Kopfzeile + CTA-Button (`nav.cta`, presence-сентинел) +
Logo + Menüpunkte (верхний уровень `menus.top.items`, hidden `menus_json` в #home-form;
Save пишет `menus` ТОЛЬКО при валидном JSON) + Fußzeile. Черновик несёт `menus`/`nav_cta`,
а шапка витрины под ?preview=1 читает ЧЕРНОВИК (раньше `top_meta`/`resolve_menu` читали
только сохранённый конфиг — стиль шапки «вживую» до Save не менялся).
"""

import json
import pathlib
from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import context as core_context
from apps.core import views
from apps.promotions import public_views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

TPL = pathlib.Path("templates/tenant/site_home.html")
BASE = pathlib.Path("templates/storefront/_base.html")

MENUS = {
    "top": {
        "style": "classic",
        "sticky": True,
        "items": [
            {
                "label": "Angebote",
                "type": "page",
                "target": "home",
                "enabled": True,
                "icon": "",
                "children": [],
            },
            {
                "label": "Katalog",
                "type": "archetype",
                "target": "catalog",
                "enabled": True,
                "icon": "",
                "children": [],
            },
        ],
    },
    "bottom": {"enabled": False, "items": []},
}


def _req(method, path, tenant, data=None, content_type=None):
    if content_type:
        req = getattr(RequestFactory(), method)(path, data, content_type=content_type)
    else:
        req = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return req


def _builder(tenant):
    return views.home_builder_view(_req("get", "/dashboard/site/home/", tenant)).content.decode()


def _segment(body, start_marker, end_marker):
    i = body.index(start_marker)
    return body[i : body.index(end_marker, i)]


def _post_builder(tenant, data):
    resp = views.home_builder_view(_req("post", "/dashboard/site/home/", tenant, data))
    assert resp.status_code == 302
    tenant.refresh_from_db()
    return siteconfig.normalize(tenant.site_config)


def test_storefront_header_and_footer_carry_section_markers():
    base = BASE.read_text()
    assert 'data-sf-section="header"' in _segment(base, "<header", ">")
    assert 'data-sf-section="footer"' in _segment(base, "<footer", ">")
    tenant = TenantFactory(slug="sthf1", name="StHf1")
    html = public_views.storefront_home(_req("get", "/", tenant)).content.decode()
    assert 'data-sf-section="header"' in html and 'data-sf-section="footer"' in html


def test_canvas_click_on_header_or_footer_opens_the_menu_column():
    tpl = TPL.read_text()
    handler = _segment(tpl, 'var key = sec.getAttribute("data-sf-section");', "if (opened) return;")
    assert 'key === "header" || key === "footer"' in handler
    assert '__sfShowArea("menu")' in handler or 'showArea("menu")' in handler
    # подпись колонки — «Kopf- & Fußzeile» с крошкой «gilt auf allen Seiten»
    assert "Kopf- & Fußzeile" in tpl and "gilt auf allen Seiten" in tpl


def test_menu_column_carries_cta_logo_items_and_footer():
    tenant = TenantFactory(slug="sthf2", name="StHf2", site_config={"menus": MENUS})
    body = _builder(tenant)
    area = _segment(body, 'data-bld-area="menu"', 'data-bld-area="library"')
    assert 'name="nav_cta"' in area and 'name="nav_cta_present" value="1"' in area
    assert 'id="menus_json"' in area and 'name="menus_json"' in area
    assert "data-menu-items" in area and 'id="menu-add-item"' in area
    assert "__sfShowArea('logo-media')" in area  # Logo → Medien/Logo
    assert "data-stu-footer-links" in area  # указатели подвала переехали сюда
    assert "data-stu-footer-links" not in _segment(
        body, 'data-bld-area="theme"', 'data-bld-area="banner"'
    )
    # hidden JSON внутри #home-form, с текущим деревом
    form = _segment(body, 'id="home-form"', "</form>")
    assert 'id="menus_json"' in form
    import html as _html
    import re as _re

    payload = json.loads(
        _html.unescape(_re.search(r'id="menus_json" value="([^"]*)"', form).group(1))
    )
    assert [i["label"] for i in payload["top"]["items"]] == ["Angebote", "Katalog"]


def test_save_writes_menus_only_when_json_is_valid():
    tenant = TenantFactory(slug="sthf3", name="StHf3", site_config={"menus": MENUS})
    base = {"order_hero": "1", "enabled_hero": "on"}
    # без menus_json — меню цело
    cfg = _post_builder(tenant, {**base, "nav_style": "centered"})
    assert [i["label"] for i in cfg["menus"]["top"]["items"]] == ["Angebote", "Katalog"]
    # битый JSON — меню цело
    cfg = _post_builder(tenant, {**base, "menus_json": "{bad json"})
    assert [i["label"] for i in cfg["menus"]["top"]["items"]] == ["Angebote", "Katalog"]
    # валидный — переименование/порядок/видимость записаны, дети/цели целы
    new = json.loads(json.dumps(MENUS))
    new["top"]["items"].reverse()
    new["top"]["items"][0]["label"] = "Sortiment"
    new["top"]["items"][1]["enabled"] = False
    cfg = _post_builder(tenant, {**base, "menus_json": json.dumps(new), "nav_style": "minimal"})
    items = cfg["menus"]["top"]["items"]
    assert [i["label"] for i in items] == ["Sortiment", "Angebote"]
    assert items[0]["target"] == "catalog" and items[1]["enabled"] is False
    assert cfg["menus"]["top"]["style"] == "minimal"  # зеркало стиля поверх присланного дерева


def test_nav_cta_round_trip_and_presence_guard():
    tenant = TenantFactory(slug="sthf4", name="StHf4")
    base = {"order_hero": "1", "enabled_hero": "on"}
    cfg = _post_builder(tenant, {**base, "nav_cta_present": "1", "nav_cta": "on"})
    assert cfg["nav"].get("cta") is True
    cfg = _post_builder(tenant, base)  # без сентинела — не трогаем
    assert cfg["nav"].get("cta") is True
    cfg = _post_builder(tenant, {**base, "nav_cta_present": "1"})  # снят
    assert "cta" not in cfg["nav"]
    body = _builder(TenantFactory(slug="sthf4b", name="B", site_config={"nav": {"cta": True}}))
    assert (
        'name="nav_cta" checked' in body or 'name="nav_cta"\n' in body or 'nav_cta" checked' in body
    )


def test_draft_carries_menus_and_cta_and_header_renders_the_draft():
    tenant = TenantFactory(slug="sthf5", name="StHf5", site_config={"menus": MENUS})
    new = json.loads(json.dumps(MENUS))
    new["top"]["items"][0]["label"] = "Deals des Tages"
    body = json.dumps({"menus": new, "nav_cta": True, "nav_style": "centered", "nav_sticky": False})
    req = _req(
        "post", "/dashboard/site/preview/draft/", tenant, body, content_type="application/json"
    )
    assert views.site_preview_draft(req).status_code == 204
    draft = req.session["site_preview_draft"]
    assert draft["menus"]["top"]["items"][0]["label"] == "Deals des Tages"
    assert draft["nav"].get("cta") is True
    # шапка витрины под ?preview=1 читает ЧЕРНОВИК: подпись, стиль, sticky
    preq = _req("get", "/?preview=1", tenant)
    preq.session["site_preview_draft"] = draft
    preq.session.save()
    ctx = core_context.modules_nav(preq)
    assert ctx["storefront_menu"][0]["label"] == "Deals des Tages"
    assert ctx["storefront_nav_style"] == "centered" and ctx["storefront_nav_sticky"] is False
    # без превью — сохранённое
    plain = core_context.modules_nav(_req("get", "/", tenant))
    assert (
        plain["storefront_menu"][0]["label"] == "Angebote"
        and plain["storefront_nav_style"] == "classic"
    )


def test_draft_ignores_invalid_menus_payload():
    tenant = TenantFactory(slug="sthf6", name="StHf6", site_config={"menus": MENUS})
    for bad in ('{"menus": "x"}', '{"menus": {"foo": 1}}', '{"menus": []}'):
        req = _req(
            "post", "/dashboard/site/preview/draft/", tenant, bad, content_type="application/json"
        )
        assert views.site_preview_draft(req).status_code == 204
        assert req.session["site_preview_draft"]["menus"]["top"]["items"][0]["label"] == "Angebote"


def test_dead_config_nav_cta_from_kits_renders_the_header_button():
    """DS-3b писал nav.cta в киты — кнопка обязана рендериться (иначе ключ мёртв)."""
    from apps.tenants import demo_kits

    kits_with_cta = [
        k
        for k, kit in demo_kits.KITS.items()
        if (getattr(kit, "config_patch", None) or {}).get("nav", {}).get("cta")
    ]
    assert kits_with_cta, "ни один кит не включает nav.cta — DS-3b ось потеряна"
    tenant = TenantFactory(
        slug="sthf7", name="StHf7", business_type="bakery", site_config={"nav": {"cta": True}}
    )
    html = public_views.storefront_home(_req("get", "/", tenant)).content.decode()
    assert "data-nav-cta" in html
