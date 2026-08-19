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
def test_finance_analytics_billing_have_registry_entries():
    """W7b: у Finanzen/Auswertungen/Abrechnung есть вход в реестре. SM-4
    (осознанная переписка): отчёты переехали в board-хаб — подпункты раздела
    «Verkäufe» в сайдбаре; billing остался вкладкой Einstellungen."""
    board_urls = [t[0] for t in HUB_TABS["board"]]
    assert "finance:journal" in board_urls
    assert "promotions:analytics" in board_urls
    assert "billing" in [t[0] for t in HUB_TABS["settings"]]


def test_sidebar_gates_finance_and_analytics_by_module():
    """SM-4: гейты модулей действуют на подпункты сайдбара (бывший гейт табов)."""
    from apps.core import modules
    from apps.tenants.tests.factories import TenantFactory

    t = TenantFactory(slug="w7g", name="W7g", disabled_modules=["finance", "analytics"])
    verk = {
        c["url_name"]
        for it in modules.sidebar_nav(t)
        if it["url_name"] == "verkaeufe"
        for c in it["children"]
    }
    assert "finance:journal" not in verk
    assert "promotions:analytics" not in verk


def test_marketing_hub_gained_blog_and_newsletter():
    html = _render("marketing", "promotions", _tenant())
    assert "Blog &amp; News" in html or "Blog & News" in html
    assert "Newsletter" in html


def test_catalog_hub_has_return_path_to_angebote_and_collections():
    html = _render("catalog", "catalog", _tenant())
    # X4 (глоссарий): обратный путь ведёт в раздел «Sortiment» (бывш. «Angebote»).
    assert "Sortiment" in html
    assert "Kollektionen" in html


def test_marketing_hub_has_no_dead_care_nav_key():
    # nav_key "care" не производила ни одна вьюха — вкладка не могла подсветиться.
    assert not any(t[2] == "care" for tabs in HUB_TABS.values() for t in tabs)


# --- плитки главной: гейт по модулям (докстринг стал правдой) ------------------
# X2a: хаб-плитки главной удалены (дубль сайдбара) — гейт «Marketing без
# promotions» держат замки сайдбара (test_sidebar_st4b, test_x0_x7_locks);
# прежние два теста проверяли builder удалённой функции.


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
