"""FB-29 T4: примеры в предпросмотре дизайна — и на страницах-списках услуг, номеров,
событий (пока своих записей нет); на живом сайте и в обычном превью их нет."""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core import design_samples
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

DESIGN = "?preview=1&look=klar"


def _req(path, bt):
    request = RequestFactory().get(path)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(business_type=bt, disabled_modules=[])
    return request


def _services(query=""):
    from apps.booking import public_views

    return public_views.termin_index(_req("/termin/" + query, "friseur")).content.decode()


def _rooms(query=""):
    from apps.stays import public_views

    return public_views.unterkunft_index(_req("/unterkunft/" + query, "hotel")).content.decode()


def _events(query=""):
    from apps.events import public_views

    return public_views.veranstaltung_index(
        _req("/veranstaltung/" + query, "retreat")
    ).content.decode()


@pytest.mark.parametrize("page", [_services, _rooms, _events])
def test_empty_listing_shows_samples_only_in_the_design_preview(page):
    html = page(DESIGN)
    assert "data-sample-section" in html and "data-sample-note" in html
    assert " inert" in html, "примеры не кликаются"
    assert "data-sample-section" not in page()
    assert "data-sample-section" not in page("?preview=1")


def test_samples_write_nothing():
    from apps.booking.models import Service
    from apps.events.models import Event
    from apps.stays.models import StayUnit

    _services(DESIGN), _rooms(DESIGN), _events(DESIGN)
    assert not Service.objects.exists() and not StayUnit.objects.exists()
    assert not Event.objects.exists()


def test_listing_with_own_records_never_gets_samples():
    from django.utils import timezone

    from apps.events.models import Event

    Event.objects.create(
        title="Echter Abend",
        starts_at=timezone.now() + timezone.timedelta(days=3),
        status=Event.STATUS_PUBLISHED,
    )
    html = _events(DESIGN)
    assert "Echter Abend" in html and "data-sample-section" not in html


def test_listing_context_is_empty_without_samples():
    request = RequestFactory().get("/veranstaltung/")
    assert design_samples.listing_context(request, "events") == {}
    assert design_samples.listing_context(request, "nope") == {}


def test_real_resources_never_get_service_samples_beside_them():
    from apps.booking.models import Resource

    Resource.objects.create(name="Stuhl 1")
    Resource.objects.create(name="Stuhl 2")
    assert "data-sample-section" not in _services(DESIGN)
