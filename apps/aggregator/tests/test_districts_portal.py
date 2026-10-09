"""T-8.15/T-8.17: демо вне настоящих порталов + районы города на портале.

План — docs/t8-15-districts-portal-plan-2026-10-09.md.
"""

import uuid

import pytest
from django.core.cache import cache
from django.http import Http404
from django.test import RequestFactory, override_settings

from apps.aggregator import portal_views
from apps.aggregator.models import AggregatorListing, AggregatorPortal
from apps.aggregator.tasks import refresh_tenant_fields
from apps.aggregator.views import listings_for
from apps.core import districts
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear():
    cache.clear()
    yield
    cache.clear()


def _portal(**kw):
    defaults = {
        "host": "solingen.siteadaptor.de",
        "kind": "city",
        "city": "Solingen",
        "title": {"de": "Angebote in Solingen"},
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorPortal.objects.create(**defaults)


def _listing(**kw):
    defaults = {
        "tenant_schema": "t1",
        "tenant_slug": "x",
        "business_name": "X",
        "business_type": "bakery",
        "city": "Solingen",
        "promo_uuid": uuid.uuid4(),
        "title": {"de": "Brot"},
        "detail_url": "https://x.siteadaptor.de/p/1/",
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorListing.objects.create(**defaults)


def _get(portal, path="/"):
    req = RequestFactory().get(path)
    req.portal = portal
    return req


# --- реестр районов -----------------------------------------------------------


def test_registry_has_all_five_solingen_districts_in_official_order():
    names = [name for _slug, name in districts.choices_for("Solingen")]
    assert names == ["Gräfrath", "Wald", "Mitte", "Burg/Höhscheid", "Ohligs/Aufderhöhe/Merscheid"]


@pytest.mark.parametrize(
    "city, value, slug",
    [
        ("Solingen", "Ohligs", "ohligs-aufderhoehe-merscheid"),
        ("solingen", "aufderhöhe", "ohligs-aufderhoehe-merscheid"),
        ("Solingen", "Gräfrath", "graefrath"),
        ("Solingen", "Solingen-Wald", "wald"),
        ("Solingen-Ohligs", "mitte", "mitte"),
        ("Solingen", "Unbekannt", ""),
        ("Hilden", "Mitte", ""),  # город не в справочнике → пусто, без каши
    ],
)
def test_normalize_maps_names_and_aliases_to_one_slug(city, value, slug):
    assert districts.normalize(city, value) == slug


def test_suggest_by_postcode_only_for_confident_codes():
    assert districts.suggest("Solingen", "Klostergasse 3, 42653 Solingen") == "graefrath"
    assert districts.suggest("Solingen", "Weg 1, 42719 Solingen") == "wald"
    assert districts.suggest("Solingen", "Weg 1, 42655 Solingen") == ""  # делится между районами


# --- T-8.15: демо вне настоящих порталов --------------------------------------


def test_demo_listings_hidden_unless_portal_shows_demo():
    _listing(title={"de": "EchtDeal"})
    _listing(title={"de": "DemoDeal"}, is_demo=True)
    titles = {lst.title_text for lst in listings_for(city="Solingen", include_demo=False)}
    assert titles == {"EchtDeal"}
    # платформенная витрина /entdecken/ — по-прежнему с демо (они помечены)
    assert listings_for(city="Solingen").count() == 2


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_real_portal_hides_demo_preview_portal_labels_it():
    _listing(title={"de": "EchtDeal"})
    _listing(title={"de": "DemoDeal"}, is_demo=True)

    real = _portal()
    html = portal_views.portal_home(_get(real)).content.decode()
    assert "EchtDeal" in html and "DemoDeal" not in html
    assert "data-demo-notice" not in html

    cache.clear()
    preview = _portal(host="vorschau.siteadaptor.de", show_demo=True)
    html = portal_views.portal_home(_get(preview)).content.decode()
    assert "DemoDeal" in html
    assert "data-demo-notice" in html and "data-demo-badge" in html


def test_apply_kit_marks_tenant_as_demo_and_sets_district():
    from apps.tenants import demo_kits

    tenant = TenantFactory(schema_name="public", slug="lite-graefrath", name="Salon")
    assert demo_kits.apply_kit(tenant, "graefrather_markt") is True
    tenant.refresh_from_db()
    assert tenant.is_demo is True
    assert tenant.district == "graefrath"


def test_lite_kits_cover_all_five_districts():
    from apps.tenants import demo_kits

    covered = {k.district for k in demo_kits.KITS.values() if k.profile == "aktionen"}
    assert covered == {slug for slug, _ in districts.choices_for("Solingen")}


# --- T-8.17: районы на портале ------------------------------------------------


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_district_chips_only_for_districts_with_offers():
    p = _portal()
    _listing(district="wald", title={"de": "WaldDeal"})
    html = portal_views.portal_home(_get(p)).content.decode()
    assert "data-district-chips" in html
    assert "/stadtteil/wald/" in html
    assert "/stadtteil/mitte/" not in html  # пустой район — мёртвый чип не показываем


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_district_page_filters_and_type_chips_stay_inside_district():
    p = _portal()
    _listing(district="graefrath", title={"de": "GraefrathDeal"}, business_type="friseur")
    _listing(district="wald", title={"de": "WaldDeal"}, business_type="bakery")
    resp = portal_views.portal_home(_get(p, "/stadtteil/graefrath/"), district="graefrath")
    html = resp.content.decode()
    assert "GraefrathDeal" in html and "WaldDeal" not in html
    assert "Gräfrath" in html
    assert "/stadtteil/graefrath/friseur/" in html  # чип типа ведёт внутри района
    assert "/stadtteil/graefrath/bakery/" not in html  # в районе нет пекарен


def test_unknown_district_is_404():
    p = _portal()
    with pytest.raises(Http404):
        portal_views.portal_home(_get(p, "/stadtteil/atlantis/"), district="atlantis")


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_sitemap_lists_district_pages():
    p = _portal()
    _listing(district="mitte")
    body = portal_views.portal_sitemap_xml(_get(p, "/sitemap.xml")).content.decode()
    assert "/stadtteil/mitte/" in body


# --- перенос полей бизнеса в листинги -----------------------------------------


def test_refresh_moves_district_but_keeps_event_city():
    tenant = TenantFactory(
        schema_name="t_refresh", slug="t-refresh", city="Solingen", district="wald"
    )
    promo = _listing(tenant_schema="t_refresh", city="Solingen")
    away = _listing(
        tenant_schema="t_refresh",
        listing_kind=AggregatorListing.KIND_EVENT,
        promo_uuid=None,
        source_ref="7",
        city="Köln",
    )
    refresh_tenant_fields(tenant)
    promo.refresh_from_db()
    away.refresh_from_db()
    assert promo.district == "wald"
    assert away.city == "Köln" and away.district == ""


def test_listing_card_shows_district_name():
    lst = _listing(district="burg-hoehscheid")
    assert lst.district_name == "Burg/Höhscheid"


# --- форма настроек бизнеса ---------------------------------------------------


def test_settings_form_offers_district_select_with_postcode_hint():
    from apps.tenants.forms import BusinessSettingsForm

    tenant = TenantFactory(
        schema_name="t_form1", slug="t-form1", city="Solingen", address="Klostergasse 3, 42653"
    )
    form = BusinessSettingsForm(instance=tenant)
    assert form.district_known
    assert form.fields["district"].initial == "graefrath"
    assert ("wald", "Wald") in form.fields["district"].choices


def test_settings_form_unknown_city_keeps_district_hidden_in_dom():
    from apps.tenants.forms import BusinessSettingsForm

    tenant = TenantFactory(schema_name="t_form2", slug="t-form2", city="Hilden")
    form = BusinessSettingsForm(instance=tenant)
    assert not form.district_known
    assert 'name="district"' in str(form["district"])  # W0: поле в DOM, Save не затирает


def test_settings_form_normalizes_district_value():
    from apps.tenants.forms import BusinessSettingsForm

    tenant = TenantFactory(schema_name="t_form3", slug="t-form3", city="Solingen")
    form = BusinessSettingsForm(instance=tenant)
    form.cleaned_data = {"city": "Solingen", "district": "Ohligs"}
    assert form.clean_district() == "ohligs-aufderhoehe-merscheid"
