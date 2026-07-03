"""A4 — share-ссылка на черновик: выпуск (owner) → анонимный просмотр (410 по TTL),
снапшот фиксируется в момент выпуска."""

import json
import re
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from django.test import RequestFactory

from apps.core import views as core_views
from apps.promotions import public_views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", path="/", data=None, tenant=None, user=False, session=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    if session:
        request.session.update(session)
    if user:
        uname = f"own-{uuid.uuid4().hex[:8]}"
        request.user = get_user_model().objects.create_user(
            username=uname, email=f"{uname}@test.de", password="pw12345678"
        )
    request.tenant = tenant or TenantFactory.build(name="Bäckerei X")
    return request


def _issue(tenant, session=None):
    resp = core_views.share_preview_issue(
        _req("post", "/dashboard/site/share-preview/", tenant=tenant, user=True, session=session)
    )
    url = json.loads(resp.content)["url"]
    return re.search(r"/vorschau/([^/]+)/", url).group(1)


def test_share_roundtrip_anonymous_sees_draft():
    tenant = TenantFactory.build(name="Bäckerei X", site_config={"hero_title": "Alt"})
    draft = {
        "hero_title": "Geteilter Entwurf 777",
        "sections": [{"key": "hero", "enabled": True}],  # hero по умолчанию выключен
    }
    token = _issue(tenant, session={"site_preview_draft": draft})

    view_req = _req(path=f"/vorschau/{token}/", tenant=tenant)
    resp = public_views.shared_preview(view_req, token=token)
    assert resp.status_code == 302 and resp.url == "/?preview=1"
    assert view_req.session["site_preview_draft"] == draft  # штатный draft-путь витрины

    home = public_views.storefront_home(
        _req(path="/", tenant=tenant, session={"site_preview_draft": draft, "_": 1}, data=None)
    )
    # рендер главной с ?preview=1 читает сессию — проверяем через прямой запрос
    req = _req(path="/", tenant=tenant, session={"site_preview_draft": draft})
    req.GET = req.GET.copy()
    req.GET["preview"] = "1"
    body = public_views.storefront_home(req).content.decode()
    assert "Geteilter Entwurf 777" in body
    assert home.status_code == 200  # без ?preview=1 — публичная версия, без падений


def test_share_snapshot_is_frozen_at_issue_time():
    tenant = TenantFactory.build(site_config={})
    session = {"site_preview_draft": {"hero_title": "V1"}}
    token = _issue(tenant, session=session)
    session["site_preview_draft"] = {"hero_title": "V2"}  # владелец продолжил править
    assert cache.get(f"share_preview:{token}") == {"hero_title": "V1"}


def test_share_falls_back_to_db_draft_then_published():
    # нет черновика сессии → БД-`_draft`
    t1 = TenantFactory.build(site_config={"_draft": {"hero_title": "DB-Entwurf"}})
    token = _issue(t1)
    assert cache.get(f"share_preview:{token}")["hero_title"] == "DB-Entwurf"
    # нет и БД-черновика → нормализованный опубликованный конфиг
    t2 = TenantFactory.build(site_config={"hero_title": "Live"})
    token2 = _issue(t2)
    assert cache.get(f"share_preview:{token2}")["hero_title"] == "Live"


def test_share_expired_token_410():
    resp = public_views.shared_preview(_req(path="/vorschau/kaputt/"), token="kaputt")
    assert resp.status_code == 410
    assert "abgelaufen" in resp.content.decode()
