"""FB-27 «Seiten», срезы S-b/S-c: вкладки страницы и вкладка «Blöcke» — блоки страницы
правятся теми же операциями «Seitenaufbau», второго писателя нет."""

import pytest

from apps.core import content_page_views as views
from apps.core import content_pages, site_schema
from apps.core.models import ContentPage
from apps.core.site_schema_views import site_schema_view
from apps.core.tests.test_m21_6_content_pages import _req, _user
from apps.tenants import siteconfig
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _text(bid, title):
    return {"key": "text", "id": bid, "enabled": True, "data": {"title": title}}


def _setup(blocks=None):
    tenant = TenantFactory(
        schema_name="public",
        slug="tabs",
        name="Tabs",
        site_config={"page_blocks": {"seite:zahlung": blocks or []}},
    )
    page = ContentPage.objects.create(slug="zahlung", title="Zahlung", is_published=True)
    return tenant, page, _user()


def _edit(tenant, page, user, query=""):
    return views.page_edit(_req(f"/x/{query}", user=user, tenant=tenant), page.pk).content.decode()


def test_saved_page_has_tabs_and_unknown_tab_falls_back_to_text():
    tenant, page, user = _setup()
    html = _edit(tenant, page, user)
    assert "data-page-tabs" in html and 'data-page-tab="text"' in html and "data-page-form" in html
    for query in ("?tab=nope", "?tab=<script>", "?tab="):
        html = _edit(tenant, page, user, query)
        assert "data-page-form" in html and "data-page-blocks-tab" not in html


def test_new_page_has_no_tabs_yet():
    html = views.page_new(_req("/x/?tab=bloecke", user=_user())).content.decode()
    assert "data-page-tabs" not in html and "data-page-form" in html


def test_blocks_tab_lists_the_blocks_of_this_page_only():
    tenant, page, user = _setup([_text("a", "Erster"), _text("b", "Zweiter")])
    html = _edit(tenant, page, user, "?tab=bloecke")
    assert "data-page-blocks-tab" in html and "data-page-form" not in html
    assert html.index('data-page-block="a"') < html.index('data-page-block="b"')
    assert "Ihr Text" in html and "seite=text%40seite%3Azahlung" in html


def test_action_from_the_tab_goes_through_the_schema_draft_and_comes_back():
    tenant, page, user = _setup([_text("a", "Erster"), _text("b", "Zweiter")])
    req = _req(
        "/dashboard/site/aufbau/",
        method="post",
        data={"seite": "text@seite:zahlung", "op": "down", "ref": "a", "zurueck": "seiten"},
        user=user,
        tenant=tenant,
    )
    resp = site_schema_view(req)
    assert resp.status_code == 302
    assert resp.url == f"/dashboard/site/seiten/{page.pk}/?tab=bloecke"
    # на сайте ничего: правка в черновике «Seitenaufbau»
    saved = siteconfig.normalize(Tenant.objects.get(pk=tenant.pk).site_config)
    assert [b["id"] for b in saved["page_blocks"]["seite:zahlung"]] == ["a", "b"]
    html = views.page_edit(
        _with_session(_req("/x/?tab=bloecke", user=user, tenant=tenant), req), page.pk
    ).content.decode()
    assert "data-page-blocks-draft" in html
    assert html.index('data-page-block="b"') < html.index('data-page-block="a"')


def _with_session(req, source):
    req.session = source.session
    return req


def test_return_address_is_built_from_the_page_never_taken_from_the_request():
    tenant, page, user = _setup([_text("a", "Erster")])
    for back in ("//evil.example/", "https://evil.example/", "seiten/../x", ""):
        req = _req(
            "/dashboard/site/aufbau/",
            method="post",
            data={"seite": "text@seite:zahlung", "op": "toggle", "ref": "a", "zurueck": back},
            user=user,
            tenant=tenant,
        )
        resp = site_schema_view(req)
        assert resp.url.startswith("/dashboard/site/aufbau/"), back
    # код не текстовой страницы с «zurueck=seiten» — обычный «Seitenaufbau»
    assert content_pages.edit_url_for_code("catalog") == ""
    assert content_pages.edit_url_for_code("text@seite:gibt-es-nicht") == ""
    assert content_pages.edit_url_for_code("text@versand").endswith("/system/versand/")


def test_system_page_without_a_stored_page_has_a_blocks_tab_too():
    tenant = TenantFactory(schema_name="public", slug="tabs2", name="T2")
    html = views.page_system(
        _req("/x/?tab=bloecke", user=_user(), tenant=tenant), "ueber-uns"
    ).content.decode()
    assert "data-page-blocks-tab" in html and "seite=text" in html
    assert content_pages.schema_ref("ueber-uns") == ("info", site_schema.TEXT)
    assert not ContentPage.objects.filter(slug="ueber-uns").exists()  # GET ничего не создал


def test_blocks_tab_is_read_only_for_someone_who_may_not_change_the_layout(monkeypatch):
    """Право просмотра «Seitenaufbau» кнопок не даёт: нажатие получило бы отказ."""
    from apps.core import view_perms

    tenant, page, user = _setup([_text("a", "Erster")])
    real = view_perms.allowed
    monkeypatch.setattr(
        view_perms,
        "allowed",
        lambda u, name, method="GET": (
            False if (name, method) == ("site-schema", "POST") else real(u, name, method)
        ),
    )
    html = _edit(tenant, page, user, "?tab=bloecke")
    assert 'data-page-block="a"' in html and "data-page-blocks-readonly" in html
    assert 'name="zurueck"' not in html and "data-page-blocks-add" not in html
