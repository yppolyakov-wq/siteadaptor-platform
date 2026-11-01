"""STU-19b: cabinet tab "Seitenvorlage" (Sortiment) + stateless storefront preview.

Locks:
* the tab shows exactly the schema of its three page types (registry ⇄ screen);
* POST writes through page_settings only and keeps every other key;
* garbage is refused with a message, the config stays unchanged;
* the screen is gated by the catalog module; the menu entry reverses;
* `?preview=1&tpl=` changes ONLY the rendered page, never the store, and a stale
  Studio draft does not leak into it;
* the Studio links to the tab (deep link both ways).
"""

import uuid
from pathlib import Path

import pytest
from django.conf import settings as dj_settings
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory
from django.urls import reverse

from apps.catalog.tests.factories import CategoryFactory, ProductFactory
from apps.core import nav_registry, page_settings, page_templates, view_perms
from apps.promotions import public_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(tenant, method="get", data=None, path="/dashboard/seitenvorlagen/sortiment/"):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    o = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
    )
    request.tenant = tenant
    return request


@pytest.fixture
def tenant():
    return TenantFactory(business_type="bakery")


def test_tab_shows_exactly_the_schema(tenant):
    for typ in ("catalog", "category", "product"):
        html = page_templates.page_templates_sortiment(_req(tenant, data={"typ": typ}))
        body = html.content.decode()
        shown = {
            part.split('"')[0] for part in body.split('data-pt-setting="')[1:] if part.split('"')[0]
        }
        expected = {s.code for s in page_settings.schema(tenant, (typ,))[0].settings}
        assert shown == expected, typ


def test_post_writes_through_the_service_and_keeps_other_keys(tenant):
    tenant.site_config = {"seo": {"title": "X"}, "board": {"labels": {"a": "b"}}}
    tenant.save(update_fields=["site_config"])
    resp = page_templates.page_templates_sortiment(
        _req(
            tenant, "post", {"setting": "catalog_page_style", "value": "magazin", "typ": "catalog"}
        )
    )
    assert resp.status_code == 302 and resp["Location"].endswith("?typ=catalog")
    tenant.refresh_from_db()
    assert tenant.site_config["catalog_page_style"] == "magazin"
    assert tenant.site_config["seo"] == {"title": "X"}
    assert tenant.site_config["board"] == {"labels": {"a": "b"}}


def test_garbage_post_changes_nothing(tenant):
    tenant.site_config = {"catalog_page_style": "kompakt"}
    tenant.save(update_fields=["site_config"])
    page_templates.page_templates_sortiment(
        _req(tenant, "post", {"setting": "catalog_page_style", "value": "<script>"})
    )
    tenant.refresh_from_db()
    assert tenant.site_config == {"catalog_page_style": "kompakt"}


def test_unavailable_tile_is_disabled_with_reason(tenant):
    body = page_templates.page_templates_sortiment(
        _req(tenant, data={"typ": "category"})
    ).content.decode()
    i = body.index('name="value" value="regale"')
    tile = body[i : i + 300]
    assert "disabled" in tile and "aria-describedby" in tile


def test_without_any_page_type_the_screen_explains_instead_of_404(tenant, monkeypatch):
    """STU-19d: the menu entry is universal — a shop without any of the section's pages
    (e.g. "Nur Aktionen") gets an explanation, not a 404 behind a visible link."""
    monkeypatch.setattr(type(tenant), "is_module_active", lambda self, key: False)
    body = page_templates.page_templates_sortiment(_req(tenant)).content.decode()
    assert 'data-pt-setting="' not in body and "ui-empty" in body


def test_menu_entry_and_permission_rule():
    entry = next(e for e in nav_registry.ENTRIES if e.url_name == "page-templates-sortiment")
    # STU-19d: the tab covers services/rooms/events too — the screen filters types
    assert entry.module_key is None and entry.hub == "sellables"
    assert reverse("page-templates-sortiment") == "/dashboard/seitenvorlagen/sortiment/"
    rule = view_perms.RULES["page-templates-sortiment"]
    assert rule.write == "website.edit"
    assert nav_registry.ANCHOR_BY_NAV["seitenvorlage"] == nav_registry.ANCHOR_BY_NAV["categories"]


@pytest.fixture
def category_tree():
    parent = CategoryFactory(slug="brot", name={"de": "Brot"})
    child = CategoryFactory(slug="brot-roggen", name={"de": "Roggen"}, parent=parent)
    ProductFactory(name={"de": "Roggenbrot"}, category=child)


@pytest.fixture
def may_preview(monkeypatch):
    """The cabinet user (signed in, website rights) — `?tpl=` is honoured."""
    monkeypatch.setattr(page_settings, "_may_preview", lambda request: True)


def _category_page(query: str, draft: dict | None = None) -> str:
    request = RequestFactory().get(f"/sortiment/brot/{query}")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    if draft is not None:
        request.session["site_preview_draft"] = draft
    request.tenant = TenantFactory.build(name="Bäckerei X", address="Hauptstr. 1")
    return public_views.product_list(request, slug="brot").content.decode()


def test_preview_tpl_changes_only_the_rendered_page(category_tree, may_preview):
    body = _category_page("?preview=1&tpl=category_page_style:magazin")
    assert 'data-cat-layout="magazin"' in body
    assert 'data-cat-layout="magazin"' not in _category_page("")


def test_stale_studio_draft_does_not_leak_into_tpl_preview(category_tree, may_preview):
    draft = {"site_defaults": {"category_page_style": "kompakt"}}
    body = _category_page("?preview=1&tpl=category_page_style:magazin", draft)
    assert 'data-cat-layout="magazin"' in body and 'data-cat-layout="kompakt"' not in body


def test_garbage_tpl_is_ignored(category_tree, may_preview):
    body = _category_page("?preview=1&tpl=category_page_style:%3Cscript%3E")
    assert "<script>" not in body.split("data-cat-layout", 1)[-1][:40]


def test_studio_links_to_the_tab():
    html = (Path(dj_settings.BASE_DIR) / "templates/tenant/site_home.html").read_text()
    for typ in ("catalog", "category"):
        assert f"{{% url 'page-templates-sortiment' %}}?typ={typ}" in html
    # STU-19e-1: the product page layout is a summary — its link comes from cabinet_url
    assert "stu19.product_detail_layout" in html
    assert page_templates.cabinet_url("product").endswith("?typ=product")


def test_anonymous_visitor_cannot_use_tpl(category_tree):
    """Security review: `?tpl=` is a cabinet tool. For anyone else it is ignored —
    no extra gate queries and no uncached page variants for bots."""
    body = _category_page("?preview=1&tpl=category_page_style:magazin")
    assert 'data-cat-layout="magazin"' not in body


def test_may_preview_is_fail_closed_for_anonymous():
    request = RequestFactory().get("/?preview=1&tpl=x:y")
    assert page_settings._may_preview(request) is False


# ── STU-19d: every section, every page type ─────────────────────────────────────


def _modules(monkeypatch, tenant, active):
    monkeypatch.setattr(type(tenant), "is_module_active", lambda self, key: key in active)


def test_aktionen_tab_needs_promotions(tenant, monkeypatch):
    _modules(monkeypatch, tenant, {"catalog"})
    with pytest.raises(Http404):
        page_templates.page_templates_aktionen(_req(tenant))
    _modules(monkeypatch, tenant, {"catalog", "promotions"})
    body = page_templates.page_templates_aktionen(_req(tenant)).content.decode()
    assert 'data-pt-setting="promo_page_style"' in body
    assert 'name="frage"' not in body  # the setup helper creates catalog things only


def test_website_screen_lists_text_pages_and_hides_inactive_types(tenant, monkeypatch):
    _modules(monkeypatch, tenant, {"catalog"})
    body = page_templates.page_templates_website(_req(tenant)).content.decode()
    assert "?typ=text" in body and "?typ=catalog" in body
    assert "?typ=services" not in body and "?typ=stays" not in body
    body = page_templates.page_templates_website(
        _req(tenant, data={"typ": "home"})
    ).content.decode()
    assert 'data-pt-setting="home_hero"' in body


def test_sortiment_shows_services_when_booking_is_on(tenant, monkeypatch):
    _modules(monkeypatch, tenant, {"catalog", "booking"})
    body = page_templates.page_templates_sortiment(
        _req(tenant, data={"typ": "services"})
    ).content.decode()
    assert 'data-pt-setting="services_sort"' in body


def test_section_writes_only_its_own_settings(tenant, monkeypatch):
    """The Aktionen tab must not become a back door for unrelated settings."""
    _modules(monkeypatch, tenant, {"catalog", "promotions"})
    page_templates.page_templates_aktionen(
        _req(tenant, "post", {"setting": "catalog_page_style", "value": "magazin"})
    )
    tenant.refresh_from_db()
    assert "catalog_page_style" not in (tenant.site_config or {})


def test_preview_query_paths_get_the_right_separator():
    assert page_templates._with_preview("/aktionen/?gruppe=A", "x:y") == (
        "/aktionen/?gruppe=A&preview=1&tpl=x%3Ay"
    )
    assert page_templates._with_preview("/termin/") == "/termin/?preview=1"
    assert page_templates._with_preview("") == ""


def test_every_type_has_a_preview_strategy():
    """A type is either reversible without args or handled by `_object_path`."""
    from django.urls import NoReverseMatch

    from apps.core import studio_pages

    for page in studio_pages.PAGE_TYPES:
        try:
            reverse(page.url_names[0])
            continue
        except NoReverseMatch:
            pass
        assert page.code in {
            "category",
            "product",
            "promo",
            "service",
            "stay",
            "event",
            "blog_post",
            "lookbook",
        }, page.code
