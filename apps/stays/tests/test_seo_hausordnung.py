"""H6: SEO (Hotel JSON-LD priceRange/image) + Hausordnung-страница."""

import pytest
from django.http import Http404
from django.test import RequestFactory

from apps.core.seo import localbusiness_ld
from apps.stays import public_views
from apps.stays.models import StaySettings
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(path="/hausordnung/"):
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware

    request = RequestFactory().get(path)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(disabled_modules=[])
    return request


# --- H6 SEO ----------------------------------------------------------------------


def test_localbusiness_ld_includes_price_range_and_image():
    tenant = TenantFactory.build(business_type="hotel", name="Pension X")
    out = localbusiness_ld(
        tenant, url="https://x.de/", price_range="ab 69 €", image="https://x/i.jpg"
    )
    assert '"@type":"Hotel"' in out
    assert '"priceRange":"ab 69 €"' in out
    assert '"image":"https://x/i.jpg"' in out


def test_localbusiness_ld_omits_when_empty():
    tenant = TenantFactory.build(business_type="hotel")
    out = localbusiness_ld(tenant, url="https://x.de/")
    assert "priceRange" not in out


# --- H6 Hausordnung --------------------------------------------------------------


def test_hausordnung_404_when_empty():
    StaySettings.objects.create(house_rules="")
    with pytest.raises(Http404):
        public_views.hausordnung(_req())


def test_hausordnung_renders_rules_when_set():
    StaySettings.objects.create(house_rules="Check-in ab 15 Uhr\nRuhezeiten 22–7")
    body = public_views.hausordnung(_req()).content.decode()
    assert "Check-in ab 15 Uhr" in body
    assert "Ruhezeiten" in body


def test_hausordnung_gated_by_module():
    req = _req()
    req.tenant = TenantFactory.build(disabled_modules=["stays"])
    with pytest.raises(Http404):
        public_views.hausordnung(req)
