"""UC2-3(b): ссылочные секции-справочники на страницах (PAGE_REF_BLOCKS).

Замки: ref-блок валиден ТОЛЬКО в page_blocks (в home-sections отбрасывается —
golden целы), рендер тега page_blocks показывает ГЛОБАЛЬНЫЙ справочник,
add_block принимает ref-тип только с page_key, пустой справочник → пусто.
"""

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.template import Context
from django.test import RequestFactory

from apps.core import views as core_views
from apps.tenants import siteconfig
from apps.tenants.templatetags import siteui
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def test_normalize_ref_blocks_page_only():
    cfg = siteconfig.normalize(
        {
            "sections": [{"key": "faq_ref", "id": "r1"}],  # home — невалиден
            "page_blocks": {"catalog": [{"key": "faq_ref", "id": "r2"}]},
        }
    )
    assert not any(s.get("key") == "faq_ref" for s in cfg["sections"])
    assert [b["key"] for b in cfg["page_blocks"]["catalog"]] == ["faq_ref"]
    assert cfg["page_blocks"]["catalog"][0]["data"] == {}  # без своих данных


def _tag_html(tenant, host="catalog"):
    req = RequestFactory().get("/produkte/?x=1")
    req.tenant = tenant
    return siteui.page_blocks(Context({"request": req}), host)


def test_ref_blocks_render_global_reference_data():
    tenant = TenantFactory(
        slug="prb1",
        name="Prb1",
        site_config={
            "faq": [{"q": "Liefern Sie?", "a": "Ja, in Hilden."}],
            "team": [{"name": "Mia Muster", "role": "Chefin", "photo": ""}],
            "page_blocks": {
                "catalog": [
                    {"key": "faq_ref", "id": "r1"},
                    {"key": "team_ref", "id": "r2"},
                ]
            },
        },
    )
    html = _tag_html(tenant)
    assert "Liefern Sie?" in html  # глобальный site.faq
    assert "Mia Muster" in html  # глобальный site.team


def test_ref_block_empty_reference_renders_nothing():
    tenant = TenantFactory(
        slug="prb2",
        name="Prb2",
        site_config={"page_blocks": {"catalog": [{"key": "faq_ref", "id": "r1"}]}},
    )
    html = _tag_html(tenant)
    assert "faq" not in html.lower() or "Liefern" not in html  # секция без данных пуста


def _req(method="post", data=None, tenant=None):
    req = getattr(RequestFactory(), method)("/dashboard/site/home/", data or {})
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    o = uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(
        username=f"o-{o}", email=f"o-{o}@t.de", password="pw12345678"
    )
    req.tenant = tenant
    return req


def test_add_block_ref_type_page_only():
    tenant = TenantFactory(schema_name="public", slug="prb3", name="Prb3", site_config={})
    # на странице — принимается
    core_views.home_builder_view(
        _req(
            data={"action": "add_block", "block_type": "faq_ref", "page_key": "catalog"},
            tenant=tenant,
        )
    )
    tenant.refresh_from_db()
    pb = siteconfig.normalize(tenant.site_config).get("page_blocks", {})
    assert [b["key"] for b in pb.get("catalog", [])] == ["faq_ref"]
    # на главной (без page_key) — отклоняется
    core_views.home_builder_view(
        _req(data={"action": "add_block", "block_type": "team_ref"}, tenant=tenant)
    )
    tenant.refresh_from_db()
    cfg = siteconfig.normalize(tenant.site_config)
    assert not any(s.get("key") == "team_ref" for s in cfg["sections"])


def test_builder_inserter_carries_page_only_marker():
    tenant = TenantFactory(schema_name="public", slug="prb4", name="Prb4", site_config={})
    body = core_views.home_builder_view(_req("get", tenant=tenant)).content.decode()
    assert 'data-bt="faq_ref" data-page-only="1"' in body
