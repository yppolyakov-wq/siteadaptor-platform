"""R3b: годовой календарь ретритов + iCal-экспорт (один .ics + фид-подписка)."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.events import ical, public_views
from apps.events.models import Event
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(path):
    from django.test import RequestFactory

    request = RequestFactory().get(path, HTTP_HOST="retreat.example.de")
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.0.7"
    request.tenant = TenantFactory.build()
    return request


def _event(**kw):
    defaults = {
        "title": "Wochenend-Retreat",
        "starts_at": timezone.now() + timedelta(days=10),
        "status": Event.STATUS_PUBLISHED,
        "capacity": 20,
    }
    defaults.update(kw)
    return Event.objects.create(**defaults)


# --- ical builder ----------------------------------------------------------
def test_render_single_event_vevent():
    start = timezone.now() + timedelta(days=10)
    ev = _event(starts_at=start, ends_at=start + timedelta(days=2), location="Freiburg")
    body = ical.render(
        [ev], url_for=lambda e: "https://x.de/e/1", dtstamp=timezone.now(), host="x.de"
    )
    assert body.startswith("BEGIN:VCALENDAR")
    assert "BEGIN:VEVENT" in body and "END:VCALENDAR" in body
    assert "SUMMARY:Wochenend-Retreat" in body
    assert "DTSTART:" in body and "DTEND:" in body
    assert "LOCATION:Freiburg" in body
    assert "\r\n" in body  # CRLF


def test_render_escapes_special_chars():
    ev = _event(title="Yoga, Klang; Wald")
    body = ical.render([ev], url_for=lambda e: "", dtstamp=timezone.now(), host="x.de")
    assert "SUMMARY:Yoga\\, Klang\\; Wald" in body


def test_render_omits_dtend_without_ends_at():
    ev = _event(ends_at=None)
    body = ical.render([ev], url_for=lambda e: "", dtstamp=timezone.now(), host="x.de")
    assert "DTSTART:" in body and "DTEND:" not in body


# --- views -----------------------------------------------------------------
def test_event_ical_view_returns_calendar():
    ev = _event()
    resp = public_views.veranstaltung_ical(_req(f"/veranstaltung/{ev.pk}/ical"), pk=ev.pk)
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/calendar")
    assert b"BEGIN:VEVENT" in resp.content


def test_ical_feed_lists_future_published_only():
    _event(title="Future")
    _event(title="Past", starts_at=timezone.now() - timedelta(days=3))
    _event(title="Draft", status=Event.STATUS_DRAFT)
    resp = public_views.veranstaltung_ical_feed(_req("/veranstaltung/feed.ics"))
    body = resp.content.decode()
    assert "SUMMARY:Future" in body
    assert "Past" not in body and "Draft" not in body


def test_calendar_groups_by_month():
    start = timezone.now() + timedelta(days=10)
    _event(title="DiesenMonat", starts_at=start)
    _event(title="NaechsterMonat", starts_at=start + timedelta(days=40))
    body = public_views.veranstaltung_calendar(_req("/veranstaltung/kalender/")).content.decode()
    assert "DiesenMonat" in body and "NaechsterMonat" in body
    # хотя бы один немецкий месяц в подписи группы
    assert any(m in body for m in ical_months())


def ical_months():
    return public_views._DE_MONTHS[1:]
