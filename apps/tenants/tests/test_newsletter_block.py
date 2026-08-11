"""GK-8: C-блок «newsletter» — форма подписки (DOI) на главной и страницах.

Форма рендерится ВСЕГДА (данные блока — оверрайды заголовка/текста/кнопки);
POST идёт в штатный /newsletter/ (безусловный роут, honeypot, DOI = согласие)."""

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


def test_newsletter_clean_presence_minimal():
    assert siteconfig._clean_cblock_data("newsletter", {}) == {}
    out = siteconfig._clean_cblock_data(
        "newsletter", {"title": "  Bleib dabei  ", "body": "", "button_label": "x" * 100}
    )
    assert out == {"title": "Bleib dabei", "button_label": "x" * 40}


def test_newsletter_demo_data_round_trips():
    demo = siteconfig.CBLOCK_DEMO_DATA["newsletter"]
    assert siteconfig._clean_cblock_data("newsletter", demo) == demo


def _render(data):
    req = RequestFactory().get("/")
    req.tenant = TenantFactory.build()
    return siteui.render_block(
        Context({"request": req}), {"key": "newsletter", "id": "n1", "data": data}
    )


def test_newsletter_renders_form_even_without_data():
    html = _render({})
    assert 'action="/newsletter/"' in html and "csrfmiddlewaretoken" in html
    assert 'name="email"' in html and 'name="website"' in html  # honeypot
    assert "Newsletter" in html  # дефолтный заголовок


def test_newsletter_custom_title_and_button():
    html = _render({"title": "Bleib dabei", "button_label": "Eintragen"})
    assert "Bleib dabei" in html and "Eintragen" in html


def test_newsletter_valid_on_home_and_pages():
    cfg = siteconfig.normalize(
        {
            "sections": [{"key": "newsletter", "id": "n1", "data": {"title": "Abo"}}],
            "page_blocks": {"info": [{"key": "newsletter", "id": "n2"}]},
        }
    )
    assert any(s.get("key") == "newsletter" for s in cfg["sections"])
    assert cfg["page_blocks"]["info"][0]["key"] == "newsletter"


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


def test_builder_add_and_save_round_trip():
    tenant = TenantFactory(schema_name="public", slug="nl1", name="Nl1", site_config={})
    core_views.home_builder_view(
        _req(data={"action": "add_block", "block_type": "newsletter"}, tenant=tenant)
    )
    tenant.refresh_from_db()
    cfg = siteconfig.normalize(tenant.site_config)
    block = next(s for s in cfg["sections"] if s.get("key") == "newsletter")
    assert block["data"] == siteconfig.CBLOCK_DEMO_DATA["newsletter"]
    # save с правкой заголовка
    core_views.home_builder_view(
        _req(
            data={
                "cb_id": block["id"],
                f"cb_type_{block['id']}": "newsletter",
                f"enabled_cb_{block['id']}": "on",
                f"order_cb_{block['id']}": "1",
                f"cb_{block['id']}_title": "Bleib dabei",
                f"cb_{block['id']}_body": "",
                f"cb_{block['id']}_button_label": "Eintragen",
            },
            tenant=tenant,
        )
    )
    tenant.refresh_from_db()
    cfg = siteconfig.normalize(tenant.site_config)
    block = next(s for s in cfg["sections"] if s.get("key") == "newsletter")
    assert block["data"] == {"title": "Bleib dabei", "button_label": "Eintragen"}
