"""FB-30.14: пункты-функции нижней панели и подвал-аккордеон."""

import pytest
from django.template.loader import render_to_string

from apps.tenants import menu as menu_mod
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _bottom(items):
    return {"menus": {"top": {"items": []}, "bottom": {"enabled": True, "items": items}}}


def test_action_nodes_keep_known_targets_only():
    cfg = siteconfig.normalize(_bottom([
        {"label": "Menü", "type": "action", "target": "menu"},
        {"label": "Gold", "type": "action", "target": "gold"},
    ]))  # fmt: skip
    items = cfg["menus"]["bottom"]["items"]
    assert [(n["type"], n["target"]) for n in items] == [("action", "menu")]


def test_actions_resolve_to_their_function_and_hide_when_missing():
    tenant = TenantFactory.build(disabled_modules=[], contact_phone="", owner_phone="")
    nodes = [
        {"label": "Menü", "type": "action", "target": "menu"},
        {"label": "Korb", "type": "action", "target": "cart"},
        {"label": "Ruf", "type": "action", "target": "call"},
    ]
    tenant.site_config = _bottom(nodes)
    out = menu_mod.resolve_menu(tenant, "bottom")
    assert [(i["action"], i["url"]) for i in out] == [
        ("menu", "#sf-nav-mobile"),
        ("cart", "/warenkorb/"),
    ], "без телефона «Anrufen» не показывается"


def test_auto_bar_starts_with_the_site_menu():
    from django.test import RequestFactory

    from apps.core.context import _storefront_bottom_nav

    request = RequestFactory().get("/")
    request.session = {}
    tenant = TenantFactory.build(disabled_modules=[])
    first = _storefront_bottom_nav(request, tenant)[0]
    assert first["action"] == "menu" and first["icon"] == "☰"


def test_bar_renders_a_button_for_the_menu_and_links_for_the_rest():
    html = render_to_string(
        "storefront/_action_bar.html",
        {"storefront_bottom_nav": [
            {"url": "#sf-nav-mobile", "label": "Menü", "icon": "☰", "action": "menu"},
            {"url": "/warenkorb/", "label": "Warenkorb", "icon": "🛒", "kind": "primary"},
        ]},
    )  # fmt: skip
    assert 'data-open-site-menu aria-controls="sf-nav-mobile"' in html
    assert 'href="#sf-nav-mobile"' not in html and 'href="/warenkorb/"' in html


def test_editor_offers_functions_from_one_registry():
    tenant = TenantFactory.build(disabled_modules=[])
    values = [a["value"] for a in menu_mod.target_sets(tenant)["actions"]]
    assert values == list(siteconfig.MENU_ACTIONS) == list(menu_mod.ACTION_LABELS)


def test_footer_columns_are_an_accordion():
    src = open("templates/storefront/_base.html").read()
    block = src.split("data-footer-columns", 1)[1].split("</nav>", 1)[0]
    assert block.count("<details") == 2 and "data-footer-acc" in block


def test_action_nodes_never_render_in_the_top_menu_or_footer():
    tenant = TenantFactory.build(disabled_modules=[])
    node = {"label": "Menü", "type": "action", "target": "menu"}
    tenant.site_config = {
        "menus": {
            "top": {"items": [node, {"label": "Über", "type": "page", "target": "about"}]},
            "bottom": {"enabled": True, "items": [node]},
            "footer": {"columns": [{"label": "A", "items": [node]}]},
        }
    }
    assert all(i.get("action") is None for i in menu_mod.resolve_menu(tenant, "top"))
    assert menu_mod.resolve_footer(tenant) == []
    assert menu_mod.resolve_menu(tenant, "bottom")[0]["action"] == "menu"


def test_deals_follow_the_module_and_link_the_deals_page():
    node = [{"label": "A", "type": "action", "target": "deals"}]
    off = TenantFactory.build(disabled_modules=["promotions"])
    off.site_config = _bottom(node)
    assert menu_mod.resolve_menu(off, "bottom") == []
    on = TenantFactory.build(disabled_modules=[])
    on.site_config = _bottom(node)
    assert menu_mod.resolve_menu(on, "bottom")[0]["url"] == "/aktionen/"


def test_buy_bar_sits_above_the_bottom_bar():
    """Фидбэк владельца: строка «In den Warenkorb» пряталась наполовину под нижней панелью."""
    with_nav = render_to_string(
        "storefront/_detail_buybar.html",
        {"price": "7,20 €", "anchor": "#kaufen", "label": "Kaufen",
         "storefront_bottom_nav": [{"url": "/", "label": "x", "icon": "x"}]},
    )  # fmt: skip
    assert "bottom-[calc(46px+env(safe-area-inset-bottom))] sm:bottom-0" in with_nav
    plain = render_to_string(
        "storefront/_detail_buybar.html", {"price": "1 €", "anchor": "#k", "label": "K"}
    )
    assert "fixed bottom-0" in plain
