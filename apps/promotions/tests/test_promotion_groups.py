"""S6: группы/направления акций — публичная /aktionen/ + цели promo_group в меню."""

import pytest
from django.http import Http404
from django.test import RequestFactory

from apps.promotions import public_views
from apps.promotions.models import Promotion
from apps.tenants import menu
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(**kw):
    return TenantFactory(schema_name="public", slug=kw.pop("slug", "pg"), name="PG", **kw)


def _get(path, params=None, tenant=None):
    req = RequestFactory().get(path, params or {})
    req.tenant = tenant
    return req


def test_promotion_list_filters_by_group():
    tenant = _tenant(slug="pg1")
    Promotion.objects.create(title={"de": "FastFoodDeal"}, status="active", group="Fastfood")
    Promotion.objects.create(title={"de": "FertigDeal"}, status="active", group="Fertiggerichte")

    body = public_views.promotion_list(_get("/aktionen/", tenant=tenant)).content.decode()
    assert "FastFoodDeal" in body and "FertigDeal" in body  # все
    assert "Fastfood" in body and "Fertiggerichte" in body  # чипы групп

    filtered = public_views.promotion_list(
        _get("/aktionen/", {"gruppe": "Fastfood"}, tenant)
    ).content.decode()
    assert "FastFoodDeal" in filtered and "FertigDeal" not in filtered


def test_promotion_list_404_when_module_disabled():
    tenant = _tenant(slug="pg2", disabled_modules=["promotions"])
    with pytest.raises(Http404):
        public_views.promotion_list(_get("/aktionen/", tenant=tenant))


def test_menu_promo_group_resolves_only_with_active_promo():
    tenant = _tenant(
        slug="pg3",
        site_config={
            "menus": {
                "top": {
                    "items": [
                        {"label": "FF-Aktionen", "type": "promo_group", "target": "Fastfood"},
                    ]
                }
            }
        },
    )
    assert menu.resolve_menu(tenant, "top") == []  # группа пуста → пункт отброшен
    Promotion.objects.create(title={"de": "x"}, status="active", group="Fastfood")
    items = menu.resolve_menu(tenant, "top")
    assert items and items[0]["url"].startswith("/aktionen/?gruppe=Fastfood")
