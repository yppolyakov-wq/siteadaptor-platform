"""V1: live-preview конструктора главной — draft-эндпоинт + рендер ?preview=1."""

import json
from types import SimpleNamespace

import pytest
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import views
from apps.promotions import public_views
from apps.tenants import siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _session(req):
    SessionMiddleware(lambda r: None).process_request(req)
    return req


def test_draft_endpoint_merges_into_session():
    tenant = TenantFactory(
        schema_name="public", slug="d", name="D", site_config={"hero_title": "Saved"}
    )
    body = json.dumps(
        {
            "sections": [{"key": "hero", "enabled": True}, {"key": "products", "enabled": False}],
            "archetypes": {"catalog": {"hidden": True, "label": "X"}},
        }
    )
    req = _session(
        RequestFactory().post(
            "/dashboard/site/preview/draft/", body, content_type="application/json"
        )
    )
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = tenant
    resp = views.site_preview_draft(req)
    assert resp.status_code == 204
    draft = req.session["site_preview_draft"]
    en = {s["key"] for s in draft["sections"] if s["enabled"]}
    assert "hero" in en and "products" not in en
    assert draft["hero_title"] == "Saved"  # прочий конфиг не затёрт
    assert draft["archetypes"]["catalog"]["hidden"] is True
    assert draft["archetypes"]["catalog"]["label"] == "X"
    # в БД ничего не записано
    tenant.refresh_from_db()
    assert tenant.site_config.get(
        "archetypes", {}
    ) == {} or "catalog" not in tenant.site_config.get("archetypes", {})


def _home(req, tenant):
    req = _session(req)
    req.tenant = tenant
    return public_views.storefront_home(req)


def test_storefront_home_renders_draft_under_preview():
    tenant = TenantFactory.build()
    draft = siteconfig.normalize(
        {
            "sections": [{"key": "hero", "enabled": True}, {"key": "contact", "enabled": True}],
            "hero_title": "DRAFTONLY",
        }
    )
    req = RequestFactory().get("/?preview=1")
    req = _session(req)
    req.session["site_preview_draft"] = draft
    req.tenant = tenant
    body = public_views.storefront_home(req).content.decode()
    assert "DRAFTONLY" in body  # черновик отрендерен

    # без ?preview=1 — сохранённое (черновик игнорируется)
    req2 = RequestFactory().get("/")
    req2 = _session(req2)
    req2.session["site_preview_draft"] = draft
    req2.tenant = tenant
    assert "DRAFTONLY" not in public_views.storefront_home(req2).content.decode()


def test_preview_skips_standalone_redirect():
    tenant = TenantFactory.build()
    draft = siteconfig.normalize(
        {"storefront_root": "catalog", "sections": [{"key": "hero", "enabled": True}]}
    )
    req = RequestFactory().get("/?preview=1")
    req = _session(req)
    req.session["site_preview_draft"] = draft
    req.tenant = tenant
    assert public_views.storefront_home(req).status_code == 200  # без редиректа
