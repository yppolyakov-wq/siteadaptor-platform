"""W7b (аудит кабинета 2026-08-05): навигационные предохранители.

Возвращённые входы-сироты (Finanzen/Auswertungen/Abrechnung/Blog/Newsletter/
Kollektionen), обратный путь Angebote↔Sortiment, гейты плиток главной,
фикс 404-ссылки Marketing-Puls, offer_cta для Handwerker.
"""

from types import SimpleNamespace

import pytest
from django.template import Context, Template

from apps.core import dashboard as dash
from apps.core.templatetags.cabinet import HUB_TABS

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(disabled=(), business_type=""):
    return SimpleNamespace(
        disabled_modules=list(disabled),
        enabled_modules=[],
        site_config={},
        business_type=business_type,
        is_module_active=lambda key: False,  # не используется реестром modules
    )


def _render(hub, nav, tenant=None):
    ctx = {"nav": nav}
    if tenant is not None:
        ctx["request"] = SimpleNamespace(tenant=tenant)
    return Template('{% load cabinet %}{% hub_tabs "' + hub + '" %}').render(Context(ctx))


# --- сироты получили входы -----------------------------------------------------
def test_settings_hub_gained_finance_analytics_billing():
    urls = [t[0] for t in HUB_TABS["settings"]]
    assert "finance:journal" in urls
    assert "promotions:analytics" in urls
    assert "billing" in urls  # подписка/счета — раньше без единого входа


def test_settings_hub_gates_finance_and_analytics_by_module():
    html = _render("settings", "settings", _tenant(disabled=["finance", "analytics"]))
    assert "Finanzen" not in html
    assert "Auswertungen" not in html
    assert "Abo &amp; Rechnung" in html  # billing — core, виден всегда (W9-1 лейбл)


def test_marketing_hub_gained_blog_and_newsletter():
    html = _render("marketing", "promotions", _tenant())
    assert "Blog &amp; News" in html or "Blog & News" in html
    assert "Newsletter" in html


def test_catalog_hub_has_return_path_to_angebote_and_collections():
    html = _render("catalog", "catalog", _tenant())
    assert "Angebote" in html  # обратный путь из Sortiment в хаб Angebote
    assert "Kollektionen" in html


def test_marketing_hub_has_no_dead_care_nav_key():
    # nav_key "care" не производила ни одна вьюха — вкладка не могла подсветиться.
    assert not any(t[2] == "care" for tabs in HUB_TABS.values() for t in tabs)


# --- плитки главной: гейт по модулям (докстринг стал правдой) ------------------
def test_hub_tiles_drop_marketing_when_promotions_disabled():
    keys = [t["key"] for t in dash.hub_tiles(_tenant(disabled=["promotions"]))]
    assert "marketing" not in keys
    assert "settings" in keys and "website" in keys


def test_hub_tiles_keep_marketing_when_active():
    keys = [t["key"] for t in dash.hub_tiles(_tenant())]
    assert "marketing" in keys


# --- Marketing-Puls: ссылка не ведёт в 404 -------------------------------------
def _widget_urls(tenant):
    return {w["key"]: w["url_name"] for w in dash.home_widgets(tenant)}


def test_puls_links_to_promotions_list_without_analytics_module():
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(business_type="bakery", disabled_modules=["analytics"])
    assert _widget_urls(tenant).get("puls") == "promotions:promotion-list"


def test_puls_links_to_analytics_when_module_active():
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(business_type="bakery", disabled_modules=[])
    assert _widget_urls(tenant).get("puls") == "promotions:analytics"


# --- чек-лист: Handwerker ведёт в Aufträge, не в каталог -----------------------
def test_offer_cta_jobs_for_handwerker():
    from apps.tenants import onboarding
    from apps.tenants.tests.factories import TenantFactory

    # S6-пресет Handwerker: jobs primary (events/stays/booking выключены).
    tenant = TenantFactory(
        business_type="handwerker", disabled_modules=["events", "stays", "booking"]
    )
    label, url_name = onboarding.offer_cta(tenant)
    assert url_name == "jobs:list"
