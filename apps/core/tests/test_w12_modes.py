"""W12 «честные режимы» (план w12-modes-plan-2026-08-05.md).

- W12-3: ось Простого режима живёт в спеках модулей — паритет 1:1 с прежними
  константами SIMPLE_HIDDEN_MODULES/ARCHETYPE_SIMPLE_HIDDEN (замок).
- W12-2: Простой прячет ящик «Erweitert» таб-баров целиком (страницы по URL
  доступны — S5; advanced-страница по прямой ссылке показывает ящик).
- W12-1: экран «Ansicht» — режим + честный список скрытого.
"""

from types import SimpleNamespace

import pytest
from django.template import Context, Template

from apps.core import modules
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


# --- W12-3: паритет производной со старыми константами -------------------------
def test_simple_hidden_derivation_parity_all_types():
    from apps.tenants.models import Tenant

    legacy_map = {
        "friseur": {"catalog"},
        "handwerker": {"catalog"},
        "events": {"catalog"},
        "hotel": {"catalog"},
    }
    for bt, _label in Tenant.BUSINESS_TYPES:
        expected = {"finance", "analytics"} | legacy_map.get(bt, set())
        assert set(modules._simple_hidden_for_type(bt)) == expected, bt


def test_simple_hidden_modules_empty_in_expert():
    t = SimpleNamespace(site_config={}, business_type="friseur")
    assert modules.simple_hidden_modules(t) == frozenset()
    t_simple = SimpleNamespace(site_config={"ui_mode": "simple"}, business_type="friseur")
    assert "catalog" in modules.simple_hidden_modules(t_simple)


# --- W12-2: Простой прячет ящик «Erweitert» ------------------------------------
def _render_settings_hub(nav, tenant):
    return Template('{% load cabinet %}{% hub_tabs "settings" %}').render(
        Context({"nav": nav, "request": SimpleNamespace(tenant=tenant)})
    )


def _tenant(simple=False):
    return SimpleNamespace(
        site_config={"ui_mode": "simple"} if simple else {},
        business_type="restaurant",
        disabled_modules=[],
        enabled_modules=[],
    )


def test_simple_mode_hides_tool_entries_from_drawer():
    # settings-ящик состоит из инструментов (module None) → в Простом пуст/скрыт.
    html = _render_settings_hub("settings", _tenant(simple=True))
    assert "Medien" not in html and "Funktionen" not in html
    assert "Mein Geschäft" in html  # прямые табы целы
    # Эксперт видит ящик целиком
    html = _render_settings_hub("settings", _tenant(simple=False))
    assert "Erweitert" in html and "Medien" in html


def test_simple_mode_keeps_module_features_in_drawer_for_werkstatt():
    # S6b-замок жив: werkstatt в Простом держит Produkte (advanced запись
    # МОДУЛЯ catalog — не инструмент) в ящике sellables-хаба.
    t = SimpleNamespace(
        site_config={"ui_mode": "simple"},
        business_type="werkstatt",
        disabled_modules=[],
        enabled_modules=[],
    )
    html = Template('{% load cabinet %}{% hub_tabs "sellables" %}').render(
        Context({"nav": "sellables", "request": SimpleNamespace(tenant=t)})
    )
    assert "Produkte" in html


def test_simple_mode_keeps_drawer_when_advanced_page_open():
    # advanced-страница по прямой ссылке (S5) — ящик виден, подсветка честная.
    html = _render_settings_hub("media", _tenant(simple=True))
    assert "Erweitert" in html
    assert html.count('aria-selected="true"') == 1


# --- W12-1: экран «Ansicht» -----------------------------------------------------
def test_ansicht_page_renders_mode_and_hidden_list():
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.core import views

    class _User:
        is_authenticated = True
        is_active = True
        username = "owner"

    req = RequestFactory().get("/dashboard/ansicht/")
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = _User()
    req.tenant = TenantFactory(business_type="friseur")
    body = views.ansicht_view(req).content.decode()
    assert "Einfach" in body and "Experte" in body
    assert "set-ui-mode" in body or "/dashboard/ui-mode/" in body
    # честный список: у friseur скрывается и Katalog (W12-3), и Finanzen/Auswertung
    assert "Katalog" in body
