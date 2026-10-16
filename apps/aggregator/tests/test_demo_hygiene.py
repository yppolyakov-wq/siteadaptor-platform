"""T-8.26 п.2 — гигиена демо: noindex, машинные поверхности без демо, плашка на
/entdecken/, флаг внутренних (тестовых) тенантов. План —
docs/t8-26-2-demo-hygiene-plan-2026-10-16.md."""

import uuid

import pytest
from django.core.cache import cache
from django.http import Http404, HttpResponse
from django.test import RequestFactory, override_settings

from apps.aggregator import llms, middleware, portal_views, reviews_views, views, visibility
from apps.aggregator.models import AggregatorListing, AggregatorPortal
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

NOINDEX = '<meta name="robots" content="noindex,follow">'


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def _portal(**kw):
    defaults = {
        "host": f"{uuid.uuid4().hex[:8]}.solingen.test",
        "kind": "city",
        "city": "Solingen",
        "title": {"de": "Angebote in Solingen"},
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorPortal.objects.create(**defaults)


def _listing(**kw):
    defaults = {
        "tenant_schema": kw.pop("schema", f"t_{uuid.uuid4().hex[:6]}"),
        "tenant_slug": kw.pop("slug", f"s-{uuid.uuid4().hex[:6]}"),
        "business_name": "X",
        "business_type": "bakery",
        "city": "Solingen",
        "promo_uuid": uuid.uuid4(),
        "title": {"de": "Brot"},
        "detail_url": "https://x.siteadaptor.de/p/1/",
        "is_active": True,
        "listing_kind": AggregatorListing.KIND_PROMOTION,
        "source_ref": uuid.uuid4().hex,
        "city_category": "cafes",
    }
    defaults.update(kw)
    return AggregatorListing.objects.create(**defaults)


def _get(path="/", portal=None, **extra):
    req = RequestFactory().get(path, **extra)
    req.portal = portal
    return req


def _html(resp):
    return resp.content.decode()


# --- 2a: превью-портал целиком noindex ---------------------------------------------


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_preview_portal_is_noindex_meta_real_portal_is_not():
    _listing(is_demo=True)
    _listing(title={"de": "Echt"})
    preview = _portal(show_demo=True)
    assert NOINDEX in _html(portal_views.portal_home(_get("/", preview)))
    real = _portal()
    assert NOINDEX not in _html(portal_views.portal_home(_get("/", real)))


def test_preview_portal_sets_x_robots_tag_header_outside_cache(monkeypatch):
    preview = _portal(show_demo=True)
    real = _portal()
    mw = middleware.AggregatorPortalMiddleware(lambda r: HttpResponse("ok"))
    monkeypatch.setattr(middleware, "resolve_portal", lambda r: preview)
    assert mw(RequestFactory().get("/"))["X-Robots-Tag"] == "noindex, follow"
    monkeypatch.setattr(middleware, "resolve_portal", lambda r: real)
    assert "X-Robots-Tag" not in mw(RequestFactory().get("/"))


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_preview_portal_sitemap_empty_and_robots_without_sitemap_line():
    _listing(is_demo=True, slug="demo-biz")
    preview = _portal(show_demo=True)
    xml = _html(portal_views.portal_sitemap_xml(_get("/sitemap.xml", preview)))
    assert "<urlset" in xml and "<url>" not in xml
    robots = _html(portal_views.portal_robots_txt(_get("/robots.txt", preview)))
    assert "Allow: /" in robots and "Sitemap:" not in robots
    real = _portal()
    assert "Sitemap:" in _html(portal_views.portal_robots_txt(_get("/robots.txt", real)))


@override_settings(ROOT_URLCONF="config.urls_portal")
def test_preview_feed_and_llms_never_carry_demo():
    import json

    _listing(is_demo=True, title={"de": "DemoDeal"})
    preview = _portal(show_demo=True)
    data = json.loads(
        portal_views.portal_feed_json(_get("/feed.json", preview, REMOTE_ADDR="10.7.7.1")).content
    )
    assert data["_siteadaptor"]["preview"] is True
    assert data["items"] == []
    text = llms.build_portal(_get("/llms.txt", preview), preview)
    assert "Rubriken" not in text and "noch keine echten Angebote" in text
    # появилось настоящее — разделы строятся из него, оговорка «пока пусто» исчезает
    _listing(title={"de": "Echt"})
    text = llms.build_portal(_get("/llms.txt", preview), preview)
    assert "Rubriken" in text and "noch keine echten Angebote" not in text


# --- 2a/2b: /entdecken/ --------------------------------------------------------------


@override_settings(ROOT_URLCONF="config.urls_public")
def test_entdecken_demo_offer_is_noindex_with_notice_real_offer_is_indexed():
    demo = _listing(is_demo=True)
    real = _listing(title={"de": "Echt"})
    html = _html(views.offer_page(_get(f"/entdecken/angebot/{demo.pk}/"), demo.pk))
    assert NOINDEX in html and "data-demo-notice" in html
    html = _html(views.offer_page(_get(f"/entdecken/angebot/{real.pk}/"), real.pk))
    assert NOINDEX not in html and "data-demo-notice" not in html


@override_settings(ROOT_URLCONF="config.urls_public")
def test_entdecken_demo_business_page_is_noindex_with_notice():
    biz = TenantFactory(slug="demo-haus", name="Demo Haus", city="Solingen", is_demo=True)
    html = _html(reviews_views.business_page(_get("/entdecken/unternehmen/demo-haus/"), biz.slug))
    assert NOINDEX in html and "data-demo-notice" in html
    real = TenantFactory(slug="echt-haus", name="Echt Haus", city="Solingen")
    html = _html(reviews_views.business_page(_get("/entdecken/unternehmen/echt-haus/"), real.slug))
    assert NOINDEX not in html and "data-demo-notice" not in html


@override_settings(ROOT_URLCONF="config.urls_public")
def test_entdecken_city_demo_only_noindex_mixed_city_indexed_with_notice():
    _listing(is_demo=True, city="Wuppertal")
    html = _html(views.city_listing(_get("/entdecken/wuppertal/"), "Wuppertal"))
    assert NOINDEX in html and "data-demo-notice" in html
    _listing(city="Wuppertal", title={"de": "Echt"})
    html = _html(views.city_listing(_get("/entdecken/wuppertal/"), "Wuppertal"))
    assert NOINDEX not in html and "data-demo-notice" in html
    # город без демо — ни плашки, ни noindex
    _listing(city="Remscheid", title={"de": "Echt2"})
    html = _html(views.city_listing(_get("/entdecken/remscheid/"), "Remscheid"))
    assert NOINDEX not in html and "data-demo-notice" not in html


@override_settings(ROOT_URLCONF="config.urls_public")
def test_entdecken_search_index_and_finder_show_notice_only_with_demo_cards():
    _listing(is_demo=True, title={"de": "DemoBrot"})
    # поиск (?q=) — только демо найдено → плашка + noindex
    html = _html(views.discover_index(_get("/entdecken/?q=DemoBrot")))
    assert "data-demo-notice" in html and NOINDEX in html
    # главная /entdecken/ («Endet bald») — демо-карточки есть → плашка
    from datetime import timedelta

    from django.utils import timezone

    _listing(is_demo=True, title={"de": "DemoBald"}, ends_at=timezone.now() + timedelta(days=1))
    cache.clear()
    assert "data-demo-notice" in _html(views.discover_index(_get("/entdecken/")))
    # Finder с результатами только из недемо → плашки нет
    AggregatorListing.objects.filter(is_demo=True).delete()
    _listing(title={"de": "Echt"})
    cache.clear()
    html = _html(views.platform_finder(_get("/entdecken/finder/?typ=bakery&stadt=Solingen")))
    assert "Echt" in html and "data-demo-notice" not in html  # шаг 3 с результатами


# --- 2a: витрина демо-тенанта -------------------------------------------------------


def test_demo_storefront_robots_without_sitemap_and_empty_sitemap():
    """Как у портала-превью: Allow (робот должен увидеть noindex), без Sitemap, sitemap пуст."""
    from apps.promotions import public_views

    req = RequestFactory().get("/robots.txt")
    req.tenant = TenantFactory(is_demo=True)
    body = _html(public_views.robots_txt(req))
    assert "Allow: /" in body and "Disallow" not in body and "Sitemap:" not in body
    req.tenant = TenantFactory()
    body = _html(public_views.robots_txt(req))
    assert "Sitemap:" in body


def test_demo_storefront_sitemap_is_empty():
    from apps.promotions import public_views

    req = RequestFactory().get("/sitemap.xml")
    req.tenant = TenantFactory(is_demo=True)
    xml = _html(public_views.sitemap_xml(req))
    assert "<urlset" in xml and "<url>" not in xml


def test_mark_internal_action_requires_change_permission_and_skips_public():
    from django.contrib.admin.sites import AdminSite

    from apps.tenants.admin import TenantAdmin
    from apps.tenants.models import Tenant

    assert "change" in TenantAdmin.mark_internal.allowed_permissions
    biz = TenantFactory(slug="probe2", name="Probe2", city="Solingen")
    _listing(schema=biz.schema_name, slug="probe2")
    public, _ = Tenant.objects.get_or_create(
        schema_name="public", defaults={"name": "Platform", "slug": "public"}
    )
    admin = TenantAdmin(Tenant, AdminSite())
    admin.mark_internal(
        RequestFactory().post("/admin/"), Tenant.objects.filter(pk__in=[biz.pk, public.pk])
    )
    biz.refresh_from_db()
    public.refresh_from_db()
    assert biz.is_internal and not public.is_internal
    assert not AggregatorListing.objects.filter(tenant_schema=biz.schema_name).exists()


def test_admin_save_without_visibility_change_does_not_touch_snapshots(monkeypatch):
    from django.contrib.admin.sites import AdminSite

    from apps.tenants import admin as tenants_admin
    from apps.tenants.models import Tenant

    biz = TenantFactory(slug="probe3", name="Probe3", city="Solingen")
    called = []
    monkeypatch.setattr(
        "apps.aggregator.visibility.apply_visibility", lambda t: called.append(t.schema_name)
    )
    admin = tenants_admin.TenantAdmin(Tenant, AdminSite())
    form = type("F", (), {"changed_data": ["name"]})()
    admin.save_model(RequestFactory().post("/admin/"), biz, form, change=True)
    assert called == []
    # а правка видимостного поля у public-тенанта — тоже не трогает (схема без tenant-таблиц)
    public, _ = Tenant.objects.get_or_create(
        schema_name="public", defaults={"name": "Platform", "slug": "public"}
    )
    form = type("F", (), {"changed_data": ["is_active"]})()
    admin.save_model(RequestFactory().post("/admin/"), public, form, change=True)
    assert called == []


# --- 2c: внутренние (тестовые) тенанты ----------------------------------------------


def test_internal_tenant_is_withheld_everywhere():
    biz = TenantFactory(slug="rest", name="Rest", city="Solingen", is_internal=True)
    assert not visibility.listable(biz)
    _listing(schema=biz.schema_name, slug="rest")
    assert not AggregatorListing.objects.public().filter(tenant_schema=biz.schema_name).exists()
    with pytest.raises(Http404):
        reviews_views.business_page(_get("/entdecken/unternehmen/rest/"), "rest")


def test_owner_settings_form_does_not_expose_internal_flag():
    from apps.tenants import forms

    for form_cls in (getattr(forms, n) for n in dir(forms) if n.endswith("Form")):
        meta = getattr(form_cls, "Meta", None)
        fields = getattr(meta, "fields", None)
        if fields and fields != "__all__":
            assert "is_internal" not in fields, form_cls.__name__


def test_admin_marking_internal_removes_snapshots(django_capture_on_commit_callbacks):
    from django.contrib.admin.sites import AdminSite

    from apps.tenants.admin import TenantAdmin
    from apps.tenants.models import Tenant

    biz = TenantFactory(slug="probe", name="Probe", city="Solingen")
    _listing(schema=biz.schema_name, slug="probe")
    admin = TenantAdmin(Tenant, AdminSite())
    biz.is_internal = True
    form = type("F", (), {"changed_data": ["is_internal"]})()
    with django_capture_on_commit_callbacks(execute=False):
        admin.save_model(RequestFactory().post("/admin/"), biz, form, change=True)
    assert not AggregatorListing.objects.filter(tenant_schema=biz.schema_name).exists()
