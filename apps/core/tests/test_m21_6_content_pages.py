"""M21.6: свои страницы сайта — санитайзер, витрина, системные slug'и, кабинет, меню."""

from types import SimpleNamespace

import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory

from apps.core import content_page_views as views
from apps.core import content_pages
from apps.core.models import ContentPage
from apps.core.richtext import sanitize_page
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(path="/x/", method="get", data=None, user=None, tenant=None):
    rf = RequestFactory()
    req = rf.post(path, data or {}) if method == "post" else rf.get(path)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user = user or AnonymousUser()
    req.tenant = tenant or TenantFactory.build(schema_name="public", slug="t", name="T")
    return req


# --- санитайзер ---------------------------------------------------------------------


def test_sanitize_page_keeps_headings_and_local_images_drops_the_rest():
    out = sanitize_page(
        '<h2 style="color:red">Versand</h2><script>alert(1)</script>'
        '<img src="/media/a.webp" onerror="x()" width="390">'
        '<img src="https://tracker.example/p.gif"><img src="//evil/x.png">'
        '<a href="javascript:alert(1)">x</a><p class="c" onclick="y">Text</p>'
    )
    assert "<h2>Versand</h2>" in out
    assert '<img src="/media/a.webp" width="390">' in out
    for bad in (
        "script",
        "onerror",
        "tracker.example",
        "//evil",
        "javascript:",
        "onclick",
        "style",
    ):
        assert bad not in out
    assert "<p>Text</p>" in out


@pytest.mark.parametrize(
    "src",
    [
        "/\\evil.example/x.png",
        "/media\\..\\x.png",
        "/media/%2f%2fevil/x.png",
        "/media/%5Cevil.png",
        "/media/../dashboard/",
        "/dashboard/site/seiten/",
        "/media/a b.png",
        "data:image/png;base64,AAAA",
    ],
)
def test_sanitize_page_rejects_image_tricks(src):
    assert "src=" not in sanitize_page(f'<img src="{src}">')


# --- витрина -------------------------------------------------------------------------


def test_published_page_renders_and_draft_is_404_for_visitors():
    ContentPage.objects.create(slug="faq-tee", title="Tee-FAQ", body="<h2>Wie?</h2><p>So.</p>")
    body = views.storefront_page(_req("/seite/faq-tee/"), "faq-tee").content.decode()
    assert "Tee-FAQ" in body and "<h2>Wie?</h2>" in body and 'data-content-page="faq-tee"' in body

    ContentPage.objects.filter(slug="faq-tee").update(is_published=False)
    with pytest.raises(Http404):
        views.storefront_page(_req("/seite/faq-tee/"), "faq-tee")
    with pytest.raises(Http404):
        views.storefront_page(_req("/seite/nope/"), "nope")


def test_draft_is_visible_to_team_member(monkeypatch):
    ContentPage.objects.create(slug="neu", title="Neu", body="<p>x</p>", is_published=False)
    monkeypatch.setattr("apps.core.roles.has_cabinet_access", lambda user: True)
    rights = {"ok": True}
    monkeypatch.setattr("apps.core.view_perms.allowed", lambda user, name, method: rights["ok"])
    user = SimpleNamespace(is_authenticated=True)
    resp = views.storefront_page(_req("/seite/neu/", user=user), "neu")
    assert "Entwurf" in resp.content.decode()
    assert "no-store" in resp["Cache-Control"]  # черновик не кэшируется
    rights["ok"] = False  # сотрудник без права на сайт черновик не видит
    with pytest.raises(Http404):
        views.storefront_page(_req("/seite/neu/", user=user), "neu")


def test_render_sanitizes_again_even_if_db_holds_raw_html():
    ContentPage.objects.create(slug="alt", title="Alt", body="<p>ok</p><script>bad()</script>")
    body = views.storefront_page(_req("/seite/alt/"), "alt").content.decode()
    assert "bad()" not in body


def test_system_slug_redirects_to_system_page_and_shows_there():
    ContentPage.objects.create(slug="ueber-uns", title="Über uns", body="<p>Seit 1990</p>")
    resp = views.storefront_page(_req("/seite/ueber-uns/"), "ueber-uns")
    assert resp.status_code == 301 and resp["Location"] == "/ueber-uns/"

    from apps.promotions import public_views

    tenant = TenantFactory(schema_name="public", slug="ab", site_config={"about_text": "ALT"})
    body = public_views.about_page(_req("/ueber-uns/", tenant=tenant)).content.decode()
    assert "Seit 1990" in body and "ALT" not in body


def test_versand_text_shows_above_shipping_methods(monkeypatch):
    from apps.orders import public_views

    monkeypatch.setattr(public_views, "_require_orders_active", lambda request: None)
    ContentPage.objects.create(slug="versand", title="Versand", body="<p>Mit DHL</p>")
    body = public_views.shipping_info(_req("/versand/")).content.decode()
    assert "Mit DHL" in body and "data-shipping-info" in body


# --- кабинет -------------------------------------------------------------------------


def _user():
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(username="owner-cp", password="pw1234567")


def test_create_edit_delete_page():
    user = _user()
    resp = views.page_new(
        _req(
            method="post",
            user=user,
            data={"title": "Zahlungsarten & Mehr", "body": "<p>PayPal</p>", "is_published": "1"},
        )
    )
    page = ContentPage.objects.get()
    assert resp.status_code == 302 and page.slug == "zahlungsarten-mehr" and page.is_published

    views.page_edit(
        _req(
            method="post",
            user=user,
            data={"title": "Zahlung", "slug": "zahlung", "body": "<p>Bar</p><script>x</script>"},
        ),
        page.pk,
    )
    page.refresh_from_db()
    assert (page.title, page.slug, page.body, page.is_published) == (
        "Zahlung",
        "zahlung",
        "<p>Bar</p>",
        False,
    )

    views.page_delete(_req(method="post", user=user), page.pk)
    assert not ContentPage.objects.exists()


def test_slug_must_be_unique_and_title_required():
    ContentPage.objects.create(slug="versand", title="Versand")
    user = _user()
    views.page_new(_req(method="post", user=user, data={"title": "Versand"}))
    views.page_new(_req(method="post", user=user, data={"title": ""}))
    assert ContentPage.objects.count() == 1
    with pytest.raises(content_pages.PageError):
        content_pages.clean_slug("versand")
    assert content_pages.make_slug("Über uns") == "ueber-uns"


def test_cabinet_views_require_login_and_have_rules_and_nav_entry():
    from apps.core import nav_registry
    from apps.core.view_perms import RULES

    for name in ("content-pages", "content-page-new", "content-page-edit", "content-page-delete"):
        assert name in RULES, name
    assert any(e.url_name == "content-pages" for e in nav_registry.ENTRIES)
    resp = views.pages_list(_req("/dashboard/site/seiten/"))
    assert resp.status_code == 302 and "login" in resp["Location"]


# --- меню ----------------------------------------------------------------------------


def test_menu_cpage_node_links_only_published_page():
    from apps.tenants import menu

    def fresh():  # карта ссылок мемоизируется на объекте тенанта (на запрос)
        return TenantFactory.build(schema_name="public")

    ContentPage.objects.create(slug="zahlung", title="Zahlungsarten")
    node = {"label": "Zahlung", "type": "cpage", "target": "zahlung", "children": []}
    assert menu._node_url(fresh(), node) == "/seite/zahlung/"
    ContentPage.objects.filter(slug="zahlung").update(is_published=False)
    assert menu._node_url(fresh(), node) is None
    assert menu._node_url(fresh(), {**node, "target": "nope"}) is None
    ContentPage.objects.filter(slug="zahlung").update(is_published=True)
    values = {o["value"] for o in menu.target_options(fresh())}
    assert "cpage:zahlung" in values


def test_rename_keeps_menu_links_and_typed_input_survives_errors(monkeypatch):
    from django.db import connection

    tenant = TenantFactory(
        schema_name="public",
        slug="cp-ren",
        site_config={
            "menus": {
                "footer": {
                    "columns": [{"label": "K", "items": [{"type": "cpage", "target": "zahlung"}]}]
                }
            }
        },
    )
    monkeypatch.setattr(connection, "tenant", tenant, raising=False)
    page = ContentPage.objects.create(slug="zahlung", title="Zahlung")
    content_pages.save_page(page, title="Zahlung", slug="bezahlen", body="", is_published=True)
    tenant.refresh_from_db()
    item = tenant.site_config["menus"]["footer"]["columns"][0]["items"][0]
    assert item["target"] == "bezahlen"
    assert content_pages.menu_references("bezahlen", tenant) == 1

    # пустое поле адреса не меняет существующий адрес (пункты меню не теряются)
    content_pages.save_page(page, title="Anders", slug="", body="", is_published=True)
    assert page.slug == "bezahlen"

    ContentPage.objects.create(slug="versand", title="Versand")
    resp = views.page_edit(
        _req(method="post", user=_user(), data={"title": "Neu", "slug": "versand"}), page.pk
    )
    assert 'value="versand"' in resp.content.decode()  # набранное не потерялось
    page.refresh_from_db()
    assert page.slug == "bezahlen"


def test_menu_resolves_all_cpage_links_with_one_query(django_assert_max_num_queries):
    from apps.tenants import menu

    for slug in ("a", "b", "c"):
        ContentPage.objects.create(slug=slug, title=slug)
    tenant = TenantFactory.build(schema_name="public")
    with django_assert_max_num_queries(3):  # savepoint + select, не по пункту
        urls = [menu._node_url(tenant, {"type": "cpage", "target": s}) for s in "abcx"]
    assert urls == ["/seite/a/", "/seite/b/", "/seite/c/", None]
