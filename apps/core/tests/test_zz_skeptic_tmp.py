import pytest
from apps.tenants import menu as menu_mod
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def test_existing_curated_menu_with_promotions_node_now_resolves():
    """Меню, СОХРАНЁННОЕ ДО HF-1 (как SHOP_MENUS): узел archetype/promotions."""
    tenant = TenantFactory(
        schema_name="public",
        slug="skep",
        name="Skep",
        disabled_modules=[],
        site_config={
            "menus": {
                "top": {
                    "style": "classic",
                    "sticky": True,
                    "items": [
                        {"label": "Sortiment", "type": "archetype", "target": "catalog"},
                        {"label": "Aktionen", "type": "archetype", "target": "promotions"},
                        {"label": "Über uns", "type": "page", "target": "about"},
                    ],
                },
                "bottom": {"enabled": False, "items": []},
            }
        },
    )
    items = menu_mod.resolve_menu(tenant, "top")
    print("RESOLVED:", [(i["label"], i["url"]) for i in items])
