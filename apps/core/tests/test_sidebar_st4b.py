"""ST-4b (одобрено 2026-07-19): компактный сайдбар «хабы + Website».

Замки: состав/гейты якорей
(легаси-разметка цела), мобильный таб-бар = первая четвёрка, все url резолвятся.
"""

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.urls import reverse

from apps.core import modules
from apps.core import views as core_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

_TOUCHED = {"v": 2, "step": "language", "done": ["start"], "skipped": [], "completed": False}


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(tenant, path="/dashboard/"):
    request = RequestFactory().get(path)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    o = uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
    )
    return request


def test_sidebar_nav_composition_and_urls():
    t = TenantFactory(slug="sb1", name="Sb1", business_type="bakery")
    keys = [it["url_name"] for it in modules.sidebar_nav(t)]
    # V4 (2026-08-03): якорь «Verkäufe» ведёт на единую страницу продаж.
    assert keys == [
        "dashboard",
        "verkaeufe",
        "sellable-manage",
        "marketing-home",
        "integrations-home",
        "site",
        "settings",
    ]
    for it in modules.sidebar_nav(t):
        reverse(it["url_name"])  # каждый якорь резолвится


def test_sidebar_nav_gates():
    # promotions выключен → нет якоря Marketing; «Angebote» остаётся всегда
    # (catalog — core-модуль).
    t = TenantFactory(
        slug="sb2",
        name="Sb2",
        disabled_modules=["catalog", "booking", "stays", "events", "promotions"],
    )
    keys = [it["url_name"] for it in modules.sidebar_nav(t)]
    assert "marketing-home" not in keys
    assert "verkaeufe" in keys and "settings" in keys and "sellable-manage" in keys


def test_compact_sidebar_renders_on_dashboard():
    t = TenantFactory(
        schema_name="tenant_sb4",
        slug="sb4",
        name="Sb4",
        business_type="bakery",
        site_config={"onboarding": dict(_TOUCHED)},
    )
    html = core_views.dashboard(_req(t, "/dashboard/")).content.decode()
    assert "Mein Geschäft" not in html  # групп AB1 больше нет в компакт-виде
    assert 'href="/dashboard/marketing/"' in html  # якорь Marketing → центр ST-6
    assert 'href="/dashboard/integrationen/"' in html
    assert "data-inbox-badge" in html  # бейдж переехал на Marketing-якорь


def test_sales_anchor_respects_orders_view_default():
    """V4 (2026-08-03): якорь «Verkäufe» сайдбара ведёт на единую страницу
    продаж для ЛЮБОГО архетипа; легаси-маппинг (отель→Belegungsplan, магазин→
    список) закреплён в test_orders_view. Сайдбар
    рендерится легаси-веткой AB1 и якоря verkaeufe не несёт."""
    hotel = TenantFactory(
        slug="sbho", name="SbHo", business_type="hotel", disabled_modules=["events", "booking"]
    )
    item = next(it for it in modules.sidebar_nav(hotel) if it["url_name"] == "verkaeufe")
    assert item["nav_key"] == "board"  # общий якорь «Verkäufe» единой страницы

    shop = TenantFactory(
        slug="sbsh",
        name="SbSh",
        business_type="shop",
        disabled_modules=["events", "booking", "stays", "jobs"],
    )
    item = next(it for it in modules.sidebar_nav(shop) if it["url_name"] == "verkaeufe")
    assert item["nav_key"] == "board"
