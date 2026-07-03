"""D2.4: self-serve featured для события (generic-зеркало P2.4b)."""

import uuid
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.events import views
from apps.events.models import Event

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None):
    request = getattr(RequestFactory(), method)("/dashboard/events/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(
        username=f"o-{owner}", email=f"o-{owner}@test.de", password="pw12345678"
    )
    return request


def _event(**kw):
    kw.setdefault("title", "Konzert")
    kw.setdefault("status", Event.STATUS_PUBLISHED)
    kw.setdefault("starts_at", timezone.now() + timedelta(days=7))
    return Event.objects.create(**kw)


def test_event_feature_page_renders():
    event = _event()
    body = views.event_feature(_req(), event.pk).content.decode()
    assert "Konzert" in body and "Anzeige" in body


def test_past_event_shows_hint():
    event = _event(starts_at=timezone.now() - timedelta(days=1))
    body = views.event_feature(_req(), event.pk).content.decode()
    assert "kommende Veranstaltungen" in body


def test_event_feature_checkout_blocked_without_payments():
    event = _event()
    resp = views.event_feature_checkout(_req("post", {"days": "7"}), event.pk)
    assert resp.status_code == 302
    assert "/feature/" in resp["Location"]
