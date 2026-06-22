"""G10: встраиваемый виджет брони (?embed=1) — без шапки, X-Frame разрешён, проброс."""

import uuid

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.stays import public_views
from apps.stays.models import StayUnit
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(path, data=None):
    request = RequestFactory().get(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(disabled_modules=[])
    return request


def _unit():
    return StayUnit.objects.create(name=f"Z {uuid.uuid4().hex[:6]}", price_cents=9000)


def test_embed_unit_is_chromeless_and_frameable():
    unit = _unit()
    _unit()  # второй, чтобы индекс не редиректил
    resp = public_views.unterkunft_unit(_req(f"/unterkunft/{unit.pk}/", {"embed": "1"}), pk=unit.pk)
    assert resp.status_code == 200
    assert getattr(resp, "xframe_options_exempt", False) is True
    body = resp.content.decode()
    assert "noindex" in body  # минимальный embed-шаблон
    # ссылка на бронь сохраняет embed
    assert 'name="embed" value="1"' in body


def test_non_embed_has_no_frame_exemption():
    unit = _unit()
    _unit()
    resp = public_views.unterkunft_unit(_req(f"/unterkunft/{unit.pk}/"), pk=unit.pk)
    assert getattr(resp, "xframe_options_exempt", False) is False
    assert "noindex" not in resp.content.decode()


def test_embed_index_propagates_to_unit_links():
    _unit()
    _unit()
    body = public_views.unterkunft_index(_req("/unterkunft/", {"embed": "1"})).content.decode()
    assert "embed=1" in body  # ссылки на номера несут embed
