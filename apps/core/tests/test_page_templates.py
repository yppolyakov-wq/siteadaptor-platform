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


def _req(tenant, method="get", data=None, path="/dashboard/seitenvorlagen/"):
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
        html = page_templates.page_templates_website(_req(tenant, data={"typ": typ}))
        body = html.content.decode()
        shown = {
            part.split('"')[0] for part in body.split('data-pt-setting="')[1:] if part.split('"')[0]
        }
        expected = {s.code for s in page_settings.schema(tenant, (typ,))[0].settings}
        assert shown == expected, typ


def test_post_writes_through_the_service_and_keeps_other_keys(tenant):
    tenant.site_config = {"seo": {"title": "X"}, "board": {"labels": {"a": "b"}}}
    tenant.save(update_fields=["site_config"])
    resp = page_templates.page_templates_website(
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
    page_templates.page_templates_website(
        _req(tenant, "post", {"setting": "catalog_page_style", "value": "<script>"})
    )
    tenant.refresh_from_db()
    assert tenant.site_config == {"catalog_page_style": "kompakt"}


def test_unavailable_tile_is_disabled_with_reason(tenant):
    body = page_templates.page_templates_website(
        _req(tenant, data={"typ": "category"})
    ).content.decode()
    i = body.index('name="value" value="regale"')
    tile = body[i : i + 300]
    assert "disabled" in tile and "aria-describedby" in tile


def test_without_any_page_type_the_screen_explains_instead_of_404(tenant, monkeypatch):
    """STU-19d: the menu entry is universal — a shop without any of the section's pages
    (e.g. "Nur Aktionen") gets an explanation, not a 404 behind a visible link."""
    # FB-16: the Website screen always has the home page — the empty case is forced
    monkeypatch.setattr(page_settings, "active_types", lambda tenant, types: ())
    body = page_templates.page_templates_website(_req(tenant)).content.decode()
    assert 'data-pt-setting="' not in body and "ui-empty" in body


def test_menu_entry_and_permission_rule():
    # FB-16: page templates live only under Website — no entry in Sortiment/Aktionen
    names = {e.url_name for e in nav_registry.ENTRIES}
    assert "page-templates-website" in names
    assert "page-templates-sortiment" not in names and "page-templates-aktionen" not in names
    entry = next(e for e in nav_registry.ENTRIES if e.url_name == "page-templates-website")
    assert entry.module_key is None and entry.hub == "site"
    assert view_perms.RULES["page-templates-website"].write == "website.edit"


def test_fb16_old_tabs_redirect_to_website(tenant):
    """FB-16: old addresses keep working — the type is kept, a question goes to the helper."""
    resp = page_templates.page_templates_sortiment(_req(tenant, data={"typ": "category"}))
    assert resp.status_code == 302 and resp["Location"] == "/dashboard/seitenvorlagen/?typ=category"
    resp = page_templates.page_templates_sortiment(_req(tenant))
    assert resp["Location"] == "/dashboard/seitenvorlagen/?typ=catalog"
    resp = page_templates.page_templates_aktionen(_req(tenant, data={"typ": "catalog"}))
    assert resp["Location"] == "/dashboard/seitenvorlagen/?typ=promos"
    resp = page_templates.page_templates_sortiment(_req(tenant, data={"frage": "Brot 3 €"}))
    assert resp["Location"].startswith("/dashboard/anlegen/?frage=")
    assert page_templates.cabinet_url("promo_group") == "/dashboard/seitenvorlagen/?typ=promo_group"


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
    # STU-19e: the moved settings are summaries — their links come from cabinet_url
    for code in ("catalog_page_style", "category_page_style", "product_detail_layout"):
        assert f"stu19.{code}" in html
    for typ in ("catalog", "category", "product"):
        assert page_templates.cabinet_url(typ).endswith(f"?typ={typ}")


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


def test_promo_types_need_promotions(tenant, monkeypatch):
    """FB-16: the offer pages are types of the Website screen — shown only with the module."""
    _modules(monkeypatch, tenant, {"catalog"})
    body = page_templates.page_templates_website(_req(tenant)).content.decode()
    assert "?typ=promos" not in body
    _modules(monkeypatch, tenant, {"catalog", "promotions"})
    body = page_templates.page_templates_website(
        _req(tenant, data={"typ": "promos"})
    ).content.decode()
    assert 'data-pt-setting="promo_page_style"' in body
    assert 'name="frage"' not in body  # the setup helper has its own screen


def test_website_screen_lists_text_pages_and_hides_inactive_types(tenant, monkeypatch):
    _modules(monkeypatch, tenant, {"catalog"})
    body = page_templates.page_templates_website(_req(tenant)).content.decode()
    assert "?typ=text" in body and "?typ=catalog" in body
    assert "?typ=services" not in body and "?typ=stays" not in body
    body = page_templates.page_templates_website(
        _req(tenant, data={"typ": "home"})
    ).content.decode()
    assert 'data-pt-setting="home_hero"' in body


def test_website_shows_services_when_booking_is_on(tenant, monkeypatch):
    _modules(monkeypatch, tenant, {"catalog", "booking"})
    body = page_templates.page_templates_website(
        _req(tenant, data={"typ": "services"})
    ).content.decode()
    assert 'data-pt-setting="services_sort"' in body


def test_screen_writes_only_settings_of_active_types(tenant, monkeypatch):
    """The screen must not become a back door for settings of switched-off pages."""
    _modules(monkeypatch, tenant, {"catalog"})
    page_templates.page_templates_website(
        _req(tenant, "post", {"setting": "promo_page_style", "value": "magazin"})
    )
    tenant.refresh_from_db()
    assert "promo_page_style" not in (tenant.site_config or {})


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


def test_every_preview_path_runs(tenant):
    """Review lesson (STU-19e-2): `_object_path` referenced a constant that does not
    exist — no test executed it. Run every type's preview path for real."""
    from apps.core import studio_pages

    for page in studio_pages.PAGE_TYPES:
        path = page_templates._preview_path(page.code)
        assert path == "" or path.startswith("/"), (page.code, path)
