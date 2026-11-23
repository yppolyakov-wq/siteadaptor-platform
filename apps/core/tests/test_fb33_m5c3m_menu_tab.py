"""FB-33 M5c-4m (C3m): экран «Menü» открывается на вкладке из адреса `?tab=`.

План `docs/fb33-stack11-plan-2026-11-23.md` §2 C3m, §4 C3m, §8.1 L4. Вкладку выбирает
сервер (белый список `top`/`bottom`/`footer`, иначе `top`): `aria-selected` кнопок и
`hidden` панелей — в разметке, без display-класса на панели (иначе `hidden` перебит).
Форма несёт `tab`, POST возвращает на ту же вкладку. Без параметра разметка вкладок —
как до правки (байт в байт).
"""

import json
import re
from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

TABS = ("top", "bottom", "footer")

# Разметка вкладок и открывающие теги панелей ДО правки (de, без параметра).
BEFORE_TABS = (
    '<button type="button" class="ui-tab" role="tab" data-tab="top" aria-selected="true">'
    "Kopfzeile</button>\n"
    '    <button type="button" class="ui-tab" role="tab" data-tab="bottom" '
    'aria-selected="false">Untere Leiste (Handy)</button>\n'
    '    <button type="button" class="ui-tab" role="tab" data-tab="footer" '
    'aria-selected="false">Fußzeile</button>'
)
BEFORE_PANES = [
    '<div data-pane="top">',
    '<div data-pane="bottom" hidden>',
    '<div data-pane="footer" hidden>',
]


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    settings.LANGUAGE_CODE = "de"


def _request(method, path, data=None, tenant=None):
    req = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    return req


def _get(tenant, query=""):
    from django.utils import translation

    with translation.override("de"):
        resp = views.menu_builder_view(
            _request("get", "/dashboard/site/menu/" + query, tenant=tenant)
        )
    assert resp.status_code == 200
    return resp.content.decode()


def _post(tenant, data):
    menus = {"top": {"items": []}, "bottom": {"items": []}}
    return views.menu_builder_view(
        _request("post", "/dashboard/site/menu/", {"menus_json": json.dumps(menus), **data}, tenant)
    )


def _tab_button(body, key):
    m = re.search(rf'<button[^>]*data-tab="{key}"[^>]*>', body)
    assert m, key
    return m.group(0)


def _pane(body, key):
    m = re.search(rf'<div[^>]*data-pane="{key}"[^>]*>', body)
    assert m, key
    return m.group(0)


def _selected(body):
    return [k for k in TABS if 'aria-selected="true"' in _tab_button(body, k)]


def _open_panes(body):
    return [k for k in TABS if not re.search(r"\shidden(\s|>|=)", _pane(body, k))]


@pytest.mark.parametrize("key", TABS)
def test_menu_tab_from_address(key):
    tenant = TenantFactory(schema_name="public", slug=f"m5c3m{key}", name="M")
    body = _get(tenant, f"?tab={key}")
    assert _selected(body) == [key]
    assert _open_panes(body) == [key]
    # форма несёт выбранную вкладку
    assert f'<input type="hidden" name="tab" value="{key}"' in body


@pytest.mark.parametrize("junk", ["", "zzz", "Footer", "footer ", "<x>", "panel-body"])
def test_menu_tab_whitelist(junk):
    tenant = TenantFactory(schema_name="public", slug="m5c3mjunk", name="M")
    body = _get(tenant, "?" + "tab=" + junk)
    assert _selected(body) == ["top"]
    assert _open_panes(body) == ["top"]
    assert "<x>" not in body
    assert '<input type="hidden" name="tab" value="top"' in body
    resp = _post(tenant, {"tab": junk})
    assert resp.status_code == 302
    assert resp["Location"] == "/dashboard/site/menu/"


def test_menu_footer_tab_nojs():
    tenant = TenantFactory(schema_name="public", slug="m5c3mfoot", name="M")
    body = _get(tenant, "?tab=footer")
    assert 'aria-selected="true"' in _tab_button(body, "footer")
    for k in ("top", "bottom"):
        assert 'aria-selected="false"' in _tab_button(body, k)
        assert re.search(r"\shidden(\s|>)", _pane(body, k))
    footer = _pane(body, "footer")
    assert "hidden" not in footer
    # №25: на панели нет display-класса Tailwind, который перебил бы `hidden`
    for k in TABS:
        assert "class=" not in _pane(body, k)
    # без JS видна вводная подвала
    assert "Spalten mit Links unter der Website." in body


def test_default_tab_unchanged():
    tenant = TenantFactory(schema_name="public", slug="m5c3mdef", name="M")
    body = _get(tenant)
    assert BEFORE_TABS in body
    for tag in BEFORE_PANES:
        assert tag in body
    assert _get(tenant, "?tab=top").count(BEFORE_TABS) == 1


@pytest.mark.parametrize("key", ["bottom", "footer"])
def test_menu_post_redirect_keeps_tab(key):
    tenant = TenantFactory(schema_name="public", slug=f"m5c3mpost{key}", name="M")
    resp = _post(tenant, {"tab": key})
    assert resp.status_code == 302
    assert resp["Location"] == f"/dashboard/site/menu/?tab={key}"
    # битый payload тоже возвращает на вкладку
    bad = views.menu_builder_view(
        _request("post", "/dashboard/site/menu/", {"menus_json": "{x", "tab": key}, tenant)
    )
    assert bad["Location"] == f"/dashboard/site/menu/?tab={key}"


def test_menu_post_top_redirect_as_before():
    tenant = TenantFactory(schema_name="public", slug="m5c3mposttop", name="M")
    assert _post(tenant, {"tab": "top"})["Location"] == "/dashboard/site/menu/"
    assert _post(tenant, {})["Location"] == "/dashboard/site/menu/"


def test_js_takes_initial_tab_from_dom_and_syncs_hidden_field():
    import pathlib

    src = pathlib.Path("templates/tenant/site_menu.html").read_text()
    assert 'var tab = "top"' not in src
    assert '[data-tab][aria-selected="true"]' in src
    assert 'getElementById("menu-tab")' in src
