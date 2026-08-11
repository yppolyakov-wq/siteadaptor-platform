"""AF-2b: встраиваемые блоки форм (anfrage_ref / message_ref) на страницах.

Зеркала test_page_ref_blocks: валидны ТОЛЬКО в page_blocks (в home-sections
отбрасываются — golden целы), рендер гейтится модулем (выключен → пусто),
csrf в отдаче, add_block принимает только с page_key, маркер в билдере.
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


def test_normalize_form_ref_blocks_page_only():
    cfg = siteconfig.normalize(
        {
            "sections": [{"key": "anfrage_ref", "id": "r1"}, {"key": "message_ref", "id": "r2"}],
            "page_blocks": {
                "service_detail": [{"key": "anfrage_ref", "id": "r3"}],
                "info": [{"key": "message_ref", "id": "r4"}],
            },
        }
    )
    home_keys = {s.get("key") for s in cfg["sections"]}
    assert "anfrage_ref" not in home_keys and "message_ref" not in home_keys
    assert [b["key"] for b in cfg["page_blocks"]["service_detail"]] == ["anfrage_ref"]
    assert [b["key"] for b in cfg["page_blocks"]["info"]] == ["message_ref"]
    assert cfg["page_blocks"]["service_detail"][0]["data"] == {}  # ref без данных


def _tag_html(tenant, host):
    req = RequestFactory().get("/x/")
    req.tenant = tenant
    return siteui.page_blocks(Context({"request": req}), host)


def test_anfrage_ref_renders_form_with_csrf_and_event_fields():
    tenant = TenantFactory.build(
        disabled_modules=[],  # jobs активен
        site_config={
            "anfrage": {"fields": ["date", "guests"]},
            "page_blocks": {"service_detail": [{"key": "anfrage_ref", "id": "r1"}]},
        },
    )
    html = _tag_html(tenant, "service_detail")
    assert 'action="/anfrage/"' in html and "csrfmiddlewaretoken" in html
    assert 'name="title"' in html
    # глобальный site.anfrage доезжает во встроенную форму
    assert 'name="event_date"' in html and 'name="guest_count"' in html


def test_anfrage_ref_empty_when_jobs_module_off():
    tenant = TenantFactory.build(
        disabled_modules=["jobs"],
        site_config={"page_blocks": {"info": [{"key": "anfrage_ref", "id": "r1"}]}},
    )
    html = _tag_html(tenant, "info")
    assert 'action="/anfrage/"' not in html and 'name="title"' not in html


def test_message_ref_renders_form_and_gates_on_inbox():
    cfg = {"page_blocks": {"info": [{"key": "message_ref", "id": "r1"}]}}
    on = _tag_html(TenantFactory.build(disabled_modules=[], site_config=cfg), "info")
    assert 'action="/nachricht/"' in on and 'name="body"' in on and 'name="phone"' in on
    off = _tag_html(TenantFactory.build(disabled_modules=["inbox"], site_config=cfg), "info")
    assert 'action="/nachricht/"' not in off


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


def test_add_block_form_ref_page_only():
    tenant = TenantFactory(schema_name="public", slug="frb1", name="Frb1", site_config={})
    core_views.home_builder_view(
        _req(
            data={"action": "add_block", "block_type": "anfrage_ref", "page_key": "service_detail"},
            tenant=tenant,
        )
    )
    tenant.refresh_from_db()
    pb = siteconfig.normalize(tenant.site_config).get("page_blocks", {})
    assert [b["key"] for b in pb.get("service_detail", [])] == ["anfrage_ref"]
    # на главной (без page_key) — отклоняется
    core_views.home_builder_view(
        _req(data={"action": "add_block", "block_type": "message_ref"}, tenant=tenant)
    )
    tenant.refresh_from_db()
    cfg = siteconfig.normalize(tenant.site_config)
    assert not any(s.get("key") == "message_ref" for s in cfg["sections"])


def test_builder_inserter_carries_form_ref_markers():
    tenant = TenantFactory(schema_name="public", slug="frb2", name="Frb2", site_config={})
    body = core_views.home_builder_view(_req("get", tenant=tenant)).content.decode()
    assert 'data-bt="anfrage_ref" data-page-only="1"' in body
    assert 'data-bt="message_ref" data-page-only="1"' in body
