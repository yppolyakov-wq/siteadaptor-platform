"""FB-27 «Seiten», срез S-d: вкладка «Suchmaschinen» — свои заголовок, описание и запрет
индексации текстовой страницы."""

import pytest
from django.db import connection

from apps.core import content_page_views as views
from apps.core import content_pages
from apps.core.models import ContentPage
from apps.core.tests.test_m21_6_content_pages import _req, _user
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    before = getattr(connection, "tenant", None)
    t = TenantFactory(schema_name="public", slug="seo", name="Teeladen")
    connection.tenant = t
    yield t
    connection.tenant = before


def _page(**kw):
    return ContentPage.objects.create(
        slug="zahlung", title="Zahlung", body="<p>Karte und bar.</p>", is_published=True, **kw
    )


def _seo(tenant):
    cfg = siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)
    return (cfg.get("seo") or {}).get("pages") or {}


def test_rubbish_never_reaches_the_config():
    raw = {
        "pages": {
            "seite:zahlung": {"title": "  A   B ", "description": "x" * 500, "noindex": "yes"},
            "catalog": {"title": "fremd"},
            "seite:../x": {"title": "böse"},
            "info": {"title": "", "noindex": True},
            "versand": "nope",
        }
    }
    pages = siteconfig.normalize_seo(raw)["pages"]
    assert sorted(pages) == ["info", "seite:zahlung"]
    assert pages["seite:zahlung"] == {
        "title": "A B",
        "description": "x" * siteconfig.SEO_PAGE_DESCRIPTION_MAX,
    }
    assert pages["info"] == {"noindex": True}
    assert "seo" not in siteconfig.normalize({"seo": {"pages": {"catalog": {"title": "x"}}}})


def test_tab_saves_only_its_own_fields_and_leaves_the_page_text_alone(tenant):
    page = _page()
    user = _user()
    html = views.page_edit(
        _req("/x/?tab=suche", user=user, tenant=tenant), page.pk
    ).content.decode()
    assert (
        "data-page-seo-form" in html and "Zahlung — Teeladen" in html and "Karte und bar." in html
    )
    req = _req(
        "/x/?tab=suche",
        method="post",
        data={"seo_present": "1", "seo_title": "Zahlungsarten", "seo_noindex": "1"},
        user=user,
        tenant=tenant,
    )
    resp = views.page_edit(req, page.pk)
    assert resp.status_code == 302 and resp.url.endswith("?tab=suche")
    assert _seo(tenant) == {"seite:zahlung": {"title": "Zahlungsarten", "noindex": True}}
    page.refresh_from_db()
    assert (page.title, page.body) == ("Zahlung", "<p>Karte und bar.</p>")  # текст цел


def test_empty_fields_remove_the_entry_and_other_settings_stay(tenant):
    Tenant.objects.filter(pk=tenant.pk).update(
        site_config={
            "hero_title": "Hallo",
            "seo": {
                "templates": {"home": {"title": "Start"}},
                "pages": {"seite:zahlung": {"title": "Alt"}, "info": {"noindex": True}},
            },
        }
    )
    tenant.refresh_from_db()
    content_pages.save_page_seo(tenant, "seite:zahlung", {"title": "", "description": ""})
    raw = Tenant.objects.get(pk=tenant.pk).site_config
    assert raw["seo"]["pages"] == {"info": {"noindex": True}}
    assert raw["seo"]["templates"] == {"home": {"title": "Start"}} and raw["hero_title"] == "Hallo"
    with pytest.raises(content_pages.PageError):
        content_pages.save_page_seo(tenant, "catalog", {"title": "x"})


def test_address_change_moves_the_entry_and_deleting_the_page_drops_it(tenant):
    content_pages.save_page_seo(tenant, "seite:zahlung", {"title": "Zahlungsarten"})
    assert content_pages.move_page_blocks("zahlung", "bezahlen") is True  # блоков у страницы нет
    assert _seo(tenant) == {"seite:bezahlen": {"title": "Zahlungsarten"}}
    assert content_pages.move_page_blocks("bezahlen", None) is True
    assert _seo(tenant) == {}


def test_storefront_uses_the_own_title_description_and_robots(tenant):
    page = _page()
    plain = views.storefront_page(_req(tenant=tenant), page.slug).content.decode()
    assert "<title>Zahlung — Teeladen</title>" in plain and 'name="robots"' not in plain
    content_pages.save_page_seo(
        tenant,
        "seite:zahlung",
        {
            "title": "Zahlungsarten im Teeladen",
            "description": "Karte, bar, PayPal.",
            "noindex": True,
        },
    )
    html = views.storefront_page(_req(tenant=tenant), page.slug).content.decode()
    assert "<title>Zahlungsarten im Teeladen</title>" in html
    assert '<meta name="description" content="Karte, bar, PayPal.">' in html
    assert '<meta name="robots" content="noindex,follow">' in html


def test_new_page_has_no_search_tab_and_unsaved_system_page_has_one(tenant):
    user = _user()
    html = views.page_new(_req("/x/?tab=suche", user=user, tenant=tenant)).content.decode()
    assert "data-page-seo-form" not in html
    html = views.page_system(
        _req("/x/?tab=suche", user=user, tenant=tenant), "ueber-uns"
    ).content.decode()
    assert "data-page-seo-form" in html
    assert not ContentPage.objects.filter(slug="ueber-uns").exists()
