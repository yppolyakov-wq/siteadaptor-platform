"""KA-12 Tickets T-3: минимум участников — письмо владельцу за N дней, без автоотмены."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.events import services, tasks
from apps.events.forms import EventForm
from apps.events.models import Event
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture
def owner_mail(monkeypatch):
    monkeypatch.setattr("apps.events.notifications._owner_email", lambda tenant: "owner@t.de")


def _event(days, minimum=5, deadline=7, **kw):
    return Event.objects.create(
        title="Kochkurs",
        starts_at=timezone.now() + timedelta(days=days),
        status=Event.STATUS_PUBLISHED,
        capacity=12,
        min_participants=minimum,
        min_deadline_days=deadline,
        **kw,
    )


def _owner_mails():
    return Notification.objects.filter(type="event_min_participants_owner")


def test_owner_notified_once_inside_deadline(owner_mail):
    event = _event(days=5)
    services.book_ticket(event, name="A", email="a@t.de", quantity=2, auto_confirm=True)
    assert event.min_missing == 3
    assert tasks.check_due_min_participants() == 1
    tasks.check_due_min_participants()
    assert _owner_mails().count() == 1
    event.refresh_from_db()
    assert event.status == Event.STATUS_PUBLISHED  # О-1: не отменяем сами


def test_not_notified_before_deadline_or_when_reached(owner_mail):
    early = _event(days=30)
    reached = _event(days=3, minimum=2)
    services.book_ticket(reached, name="A", email="a@t.de", quantity=2, auto_confirm=True)
    assert tasks.check_due_min_participants() == 0
    assert early.min_missing == 5 and reached.min_missing == 0


def test_no_minimum_means_no_mail(owner_mail):
    _event(days=2, minimum=0)
    assert tasks.check_due_min_participants() == 0


def test_form_defaults_keep_old_events_unchanged():
    form = EventForm(data={"title": "X", "starts_at": "2030-01-01T10:00", "capacity": "5"})
    form.is_valid()
    assert form.cleaned_data.get("min_participants") == 0
    assert form.cleaned_data.get("min_deadline_days") == 7
