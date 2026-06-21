"""Z: live-предпросмотр витрины в кабинете (iframe + переключатель ширины)."""

from types import SimpleNamespace

import pytest
from django.test import RequestFactory

from apps.core import views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def test_preview_renders_iframe():
    req = RequestFactory().get("/dashboard/site/preview/")
    req.user = SimpleNamespace(is_authenticated=True)
    req.tenant = TenantFactory(schema_name="public", slug="pv", name="PV")
    resp = views.site_preview(req)
    assert resp.status_code == 200
    body = resp.content.decode()
    assert 'id="prev-frame"' in body  # iframe витрины
    assert 'src="/"' in body  # указывает на корень витрины
    assert "dev-btn" in body  # переключатель устройств
