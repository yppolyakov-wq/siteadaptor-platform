"""S5: публичная страница лояльности /treue/ + loyalty как архетип витрины."""

import pytest
from django.http import Http404
from django.test import RequestFactory

from apps.core import modules
from apps.loyalty.models import LoyaltyProgram
from apps.promotions import public_views
from apps.tenants import menu
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _get(tenant):
    req = RequestFactory().get("/treue/")
    req.tenant = tenant
    return req


def test_loyalty_page_lists_active_programs():
    tenant = TenantFactory(schema_name="public", slug="ly", name="LY")
    LoyaltyProgram.objects.create(
        label="Kaffee-Karte", stamps_required=10, reward_label="Gratis Kaffee"
    )
    LoyaltyProgram.objects.create(label="Alt", stamps_required=5, reward_label="X", is_active=False)
    body = public_views.loyalty_page(_get(tenant)).content.decode()
    assert "Kaffee-Karte" in body and "Gratis Kaffee" in body
    assert "Alt" not in body  # неактивная не показана


def test_loyalty_page_404_when_module_disabled():
    tenant = TenantFactory(
        schema_name="public", slug="ly2", name="LY2", disabled_modules=["loyalty"]
    )
    with pytest.raises(Http404):
        public_views.loyalty_page(_get(tenant))


def test_loyalty_is_storefront_archetype():
    keys = [a.key for a in modules.storefront_archetypes(TenantFactory.build())]
    assert "loyalty" in keys


def test_menu_archetype_loyalty_resolves_to_treue():
    tenant = TenantFactory.build(
        site_config={
            "menus": {
                "top": {
                    "items": [
                        {"label": "Treue", "type": "archetype", "target": "loyalty"},
                    ]
                }
            }
        }
    )
    items = menu.resolve_menu(tenant, "top")
    assert items and items[0]["url"] == "/treue/"
