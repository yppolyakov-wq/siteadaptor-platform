"""Тесты P2.1a: модель AggregatorPortal + резолвер host→портал (middleware).

Резолвер тестируем напрямую (RequestFactory + ручной request.tenant), как и
прочие вьюхи агрегатора (см. test_pages.py). Кэш чистим автофикстурой —
сигнал на save/delete тоже сбрасывает его, но фикстура даёт детерминизм.
"""

import types

import pytest
from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory

from apps.aggregator import middleware
from apps.aggregator.middleware import AggregatorPortalMiddleware, resolve_portal
from apps.aggregator.models import AggregatorPortal

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_portal_cache():
    cache.delete(middleware._CACHE_KEY)
    yield
    cache.delete(middleware._CACHE_KEY)


def _portal(**kw):
    defaults = {
        "host": "muenchen.siteadaptor.de",
        "kind": "city",
        "city": "München",
        "title": {"de": "Angebote München"},
        "is_active": True,
    }
    defaults.update(kw)
    return AggregatorPortal.objects.create(**defaults)


def _request(host, *, schema="public", with_tenant=True):
    req = RequestFactory().get("/", HTTP_HOST=host)
    if with_tenant:
        req.tenant = types.SimpleNamespace(schema_name=schema)
    return req


# --- модель -----------------------------------------------------------------


def test_str_shows_host_and_city_scope():
    p = _portal()
    assert "muenchen.siteadaptor.de" in str(p)
    assert "München" in str(p)


def test_str_uses_business_type_when_no_city():
    p = _portal(
        host="baeckerei.siteadaptor.de",
        kind="vertical",
        city="",
        business_type="bakery",
        title={"de": "Bäckereien"},
    )
    s = str(p)
    assert "baeckerei.siteadaptor.de" in s
    assert "Bakery" in s  # get_business_type_display()


def test_i18n_title_fallback_and_empty_tagline():
    p = _portal(title={"en": "Munich deals"}, tagline={})
    assert p.title_text == "Munich deals"  # de отсутствует → фолбэк на en
    assert p.tagline_text == ""


# --- резолвер ---------------------------------------------------------------


def test_resolve_matches_host_on_public_schema():
    p = _portal()
    assert resolve_portal(_request("muenchen.siteadaptor.de")).id == p.id


def test_resolve_is_case_insensitive_and_ignores_port():
    p = _portal()
    assert resolve_portal(_request("MUENCHEN.siteadaptor.de:8000")).id == p.id


def test_resolve_returns_none_for_unknown_host():
    _portal()
    assert resolve_portal(_request("koeln.siteadaptor.de")) is None


def test_resolve_returns_none_for_inactive_portal():
    _portal(is_active=False)
    assert resolve_portal(_request("muenchen.siteadaptor.de")) is None


def test_resolve_skipped_on_tenant_schema():
    _portal()
    assert resolve_portal(_request("muenchen.siteadaptor.de", schema="shop1")) is None


def test_resolve_none_without_tenant():
    _portal()
    assert resolve_portal(_request("muenchen.siteadaptor.de", with_tenant=False)) is None


def test_cache_invalidated_on_deactivate():
    p = _portal()
    assert resolve_portal(_request("muenchen.siteadaptor.de")).id == p.id  # прогрев кэша
    p.is_active = False
    p.save()  # сигнал сбрасывает кэш
    assert resolve_portal(_request("muenchen.siteadaptor.de")) is None


# --- middleware -------------------------------------------------------------


def _capture_portal(request):
    captured = {}

    def get_response(req):
        captured["portal"] = req.portal
        return HttpResponse("ok")

    resp = AggregatorPortalMiddleware(get_response)(request)
    return resp, captured


def test_middleware_sets_request_portal():
    p = _portal()
    resp, captured = _capture_portal(_request("muenchen.siteadaptor.de"))
    assert resp.status_code == 200
    assert captured["portal"].id == p.id


def test_middleware_sets_none_on_main_domain():
    _portal()
    _, captured = _capture_portal(_request("siteadaptor.de"))
    assert captured["portal"] is None
