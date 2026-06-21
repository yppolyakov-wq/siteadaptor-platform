"""S3: обложки разделов — нормализация, маппинг url_name→архетип, рендер-контекст,
кабинет (сохранение интро/hero с сохранением оверрайдов тизеров S2)."""

from types import SimpleNamespace

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import modules, views
from apps.core.context import modules_nav
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def test_normalize_keeps_cover_fields():
    cfg = siteconfig.normalize(
        {
            "archetypes": {
                "catalog": {"label": "Speisekarte", "intro": "Frisch", "hero_image": "/m/x.jpg"}
            }
        }
    )
    cat = cfg["archetypes"]["catalog"]
    assert cat["intro"] == "Frisch" and cat["hero_image"] == "/m/x.jpg"
    assert cat["label"] == "Speisekarte"  # оверрайд тизера (S2) цел


def test_archetype_by_landing():
    assert modules.archetype_by_landing("storefront-products") == "catalog"
    assert modules.archetype_by_landing("storefront-termin") == "booking"
    assert modules.archetype_by_landing("storefront-home") is None  # не лендинг архетипа


def _ctx_request(url_name, tenant):
    req = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(req)
    req.resolver_match = SimpleNamespace(url_name=url_name)
    req.tenant = tenant
    return modules_nav(req)


def test_cover_present_on_its_landing_only():
    tenant = TenantFactory.build(
        site_config={
            "archetypes": {"catalog": {"intro": "Frisch & vegan", "hero_image": "/m/h.jpg"}}
        }
    )
    cover = _ctx_request("storefront-products", tenant)["archetype_cover"]
    assert cover["intro"] == "Frisch & vegan" and cover["hero_image"] == "/m/h.jpg"
    # на другой странице обложки нет
    assert _ctx_request("storefront-home", tenant)["archetype_cover"] == {}
    assert _ctx_request("storefront-termin", tenant)["archetype_cover"] == {}


def test_sections_view_saves_cover_and_keeps_teaser_overrides():
    tenant = TenantFactory(
        schema_name="public",
        slug="cov",
        name="Cov",
        site_config={"archetypes": {"catalog": {"label": "Speisekarte", "hidden": True}}},
    )
    req = RequestFactory().post(
        "/dashboard/site/sections/",
        {"intro_catalog": "  Willkommen  ", "hero_catalog": "/m/banner.jpg"},
    )
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    resp = views.sections_view(req)
    assert resp.status_code == 302
    cat = siteconfig.normalize(tenant.site_config)["archetypes"]["catalog"]
    assert cat["intro"] == "Willkommen" and cat["hero_image"] == "/m/banner.jpg"
    # оверрайды тизера из S2 не затёрты
    assert cat["label"] == "Speisekarte" and cat["hidden"] is True
