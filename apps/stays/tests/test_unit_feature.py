"""D2.4: self-serve featured для типа размещения (generic-зеркало P2.4b)."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.aggregator.models import AggregatorListing
from apps.stays import views
from apps.stays.models import StayUnit

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None):
    request = getattr(RequestFactory(), method)("/dashboard/stays/units/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
    )
    return request


def _unit(**kw):
    kw.setdefault("name", "Doppelzimmer")
    kw.setdefault("price_cents", 8000)
    return StayUnit.objects.create(**kw)


def test_unit_feature_page_renders_with_listing_stats():
    unit = _unit()
    AggregatorListing.objects.create(
        tenant_schema="public",  # тесты без tenant-миддлвари живут в public
        tenant_slug="x",
        business_name="X",
        listing_kind=AggregatorListing.KIND_STAY,
        source_ref=str(unit.pk),
        title={"de": unit.name},
        detail_url="https://x.siteadaptor.de/unterkunft/1/",
        featured_impressions=5,
        featured_clicks=2,
    )
    body = views.unit_feature(_req(), unit.pk).content.decode()
    assert "Doppelzimmer" in body
    assert "5 Aufrufe" in body and "2 Klicks" in body


def test_unit_feature_checkout_blocked_without_payments():
    unit = _unit()
    resp = views.unit_feature_checkout(_req("post", {"days": "7"}), unit.pk)
    # featured выключен (нет Stripe-ключа) → назад на страницу продвижения
    assert resp.status_code == 302
    assert resp["Location"].endswith(f"/dashboard/stays/units/{unit.pk}/feature/")


def test_inactive_unit_page_shows_hint():
    unit = _unit(is_active=False)
    body = views.unit_feature(_req(), unit.pk).content.decode()
    assert "Nur aktive Unterk" in body
