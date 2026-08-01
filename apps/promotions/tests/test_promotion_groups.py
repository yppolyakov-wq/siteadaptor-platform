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


# --- i18n метки группы (2026-08-01) -----------------------------------------
# Ключ фасета `?gruppe=` остаётся ПЛОСКИМ немецким значением (ссылки не должны
# разъезжаться между локалями), переводится только показ.


def test_group_localized_falls_back_to_plain():
    p = Promotion(title={"de": "x"}, group="Wochenangebote")
    assert p.group_localized == "Wochenangebote"


def test_promotion_list_shows_localized_group_label_but_keeps_key():
    from django.utils import translation

    tenant = _tenant(slug="pgi", enabled_locales=["de", "en"])
    Promotion.objects.create(
        title={"de": "Deal", "en": "Deal"},
        status="active",
        group="Wochenangebote",
        group_i18n={"en": "Weekly offers"},
    )
    with translation.override("en"):
        body = public_views.promotion_list(_get("/aktionen/", tenant=tenant)).content.decode()
    assert "Weekly offers" in body  # заголовок секции и чип — на локали
    assert "?gruppe=Wochenangebote" in body  # ключ фильтра остался немецким


def test_group_chips_keep_labels_of_other_groups_when_filtered():
    """Карта меток строится по НЕотфильтрованной выдаче — иначе чип невыбранной
    группы остался бы без перевода."""
    from django.utils import translation

    tenant = _tenant(slug="pgi2", enabled_locales=["de", "en"])
    Promotion.objects.create(
        title={"de": "A"}, status="active", group="Wochenangebote", group_i18n={"en": "Weekly"}
    )
    Promotion.objects.create(
        title={"de": "B"}, status="active", group="Räumung", group_i18n={"en": "Clearance"}
    )
    with translation.override("en"):
        body = public_views.promotion_list(
            _get("/aktionen/", {"gruppe": "Wochenangebote"}, tenant)
        ).content.decode()
    assert "Clearance" in body and "Weekly" in body
