"""MX-6 v1: серия одной точкой входа (series_id ожил) + свои категории."""

import uuid
from datetime import timedelta

import pytest
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.events import public_views, services
from apps.events.models import Event
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _get(path):
    request = RequestFactory().get(path)
    SessionMiddleware(lambda r: None).process_request(request)
    request.user = type("U", (), {"is_authenticated": False})()
    request.tenant = TenantFactory(enabled_modules=["events"])
    return request


def _event(**kw):
    kw.setdefault("title", f"Kurs {uuid.uuid4().hex[:6]}")
    kw.setdefault("starts_at", timezone.now() + timedelta(days=10))
    kw.setdefault("status", Event.STATUS_PUBLISHED)
    kw.setdefault("capacity", 10)
    kw.setdefault("price_cents", 1000)
    return Event.objects.create(**kw)


def test_detail_shows_series_siblings():
    source = _event()
    created = services.create_series(source, interval="weekly", count=3)
    assert source.series_id is not None and len(created) == 3
    resp = public_views.veranstaltung_detail(_get(f"/veranstaltung/{source.pk}/"), pk=source.pk)
    body = resp.content.decode()
    assert "Weitere Termine" in body
    # сиблинги — будущие опубликованные той же серии, сам источник исключён
    for sib in created:
        assert str(sib.pk) in body


def test_detail_without_series_has_no_block():
    ev = _event()
    resp = public_views.veranstaltung_detail(_get(f"/veranstaltung/{ev.pk}/"), pk=ev.pk)
    assert "Weitere Termine" not in resp.content.decode()


def test_custom_category_survives_form_and_appears_in_facet():
    from apps.events.forms import EventForm

    ev = _event(category="motorrad")  # своей категории нет в пресете из 9 тем
    form = EventForm(instance=ev)
    assert form.fields["category"].__class__.__name__ == "CharField"
    facets = public_views._event_facets([ev])
    assert ("motorrad", "motorrad") in facets["cat"]
