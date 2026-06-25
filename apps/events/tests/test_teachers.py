"""R3: преподаватели (Teacher) — сущность, связь с событиями, фильтр каталога, страницы."""

import uuid
from datetime import timedelta

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.events import public_views, views
from apps.events.models import Event, Teacher
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


class _User:
    is_authenticated = True
    is_active = True


def _cab(method, data=None):
    request = getattr(RequestFactory(), method)("/dashboard/events/teachers/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = _User()
    return request


def _store(path="/lehrer/", data=None):
    request = RequestFactory().get(path, data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.0.7"
    request.tenant = TenantFactory.build()
    return request


def _event(**kw):
    defaults = {
        "title": "Retreat",
        "starts_at": timezone.now() + timedelta(days=10),
        "status": Event.STATUS_PUBLISHED,
        "capacity": 20,
    }
    defaults.update(kw)
    return Event.objects.create(**defaults)


# --- model -----------------------------------------------------------------
def test_instagram_url_from_handle_and_url():
    assert Teacher(instagram="mara_yoga").instagram_url == "https://instagram.com/mara_yoga"
    assert Teacher(instagram="@mara").instagram_url == "https://instagram.com/mara"
    assert Teacher(instagram="https://instagram.com/x").instagram_url == "https://instagram.com/x"
    assert Teacher(instagram="").instagram_url == ""


def test_upcoming_events_only_published_future():
    t = Teacher.objects.create(name="Mara")
    future = _event(title="Future")
    _past = _event(title="Past", starts_at=timezone.now() - timedelta(days=2))
    draft = _event(title="Draft", status=Event.STATUS_DRAFT)
    t.events.set([future, _past, draft])
    titles = [e.title for e in t.upcoming_events()]
    assert titles == ["Future"]


# --- catalog filter --------------------------------------------------------
def test_catalog_filter_by_teacher():
    mara = Teacher.objects.create(name="Mara")
    felix = Teacher.objects.create(name="Felix")
    e1 = _event(title="Yoga mit Mara")
    e2 = _event(title="Klang mit Felix")
    e1.teachers.set([mara])
    e2.teachers.set([felix])
    body = public_views.veranstaltung_index(
        _store("/veranstaltung/", {"teacher": str(mara.pk)})
    ).content.decode()
    assert "Yoga mit Mara" in body and "Klang mit Felix" not in body


def test_teacher_facet_lists_present_teachers():
    mara = Teacher.objects.create(name="Mara")
    # M20U-3: панель фильтров (с фасетом учителей) показывается при > порога
    # событий — создаём достаточно, чтобы она рендерилась.
    for i in range(public_views._FILTER_MIN_EVENTS + 1):
        _event(title=f"Retreat {i}").teachers.set([mara])
    body = public_views.veranstaltung_index(_store("/veranstaltung/")).content.decode()
    assert "Mara" in body and "teacher" in body


# --- storefront teacher pages ---------------------------------------------
def test_lehrer_index_lists_active_only():
    Teacher.objects.create(name="Sichtbar", is_active=True)
    Teacher.objects.create(name="Versteckt", is_active=False)
    body = public_views.lehrer_index(_store()).content.decode()
    assert "Sichtbar" in body and "Versteckt" not in body


def test_lehrer_detail_shows_upcoming():
    t = Teacher.objects.create(name="Mara", title="Yogalehrerin")
    ev = _event(title="Waldlicht-Retreat")
    t.events.set([ev])
    body = public_views.lehrer_detail(_store(f"/lehrer/{t.pk}/"), pk=t.pk).content.decode()
    assert "Mara" in body and "Waldlicht-Retreat" in body


# --- cabinet CRUD ----------------------------------------------------------
def test_cabinet_create_edit_delete_teacher():
    # create
    views.teacher_create(_cab("post", {"name": "Mara", "title": "Yogalehrerin", "is_active": "on"}))
    t = Teacher.objects.get(name="Mara")
    assert t.title == "Yogalehrerin"
    # edit
    views.teacher_edit(_cab("post", {"name": "Mara Lind", "is_active": "on"}), pk=t.pk)
    t.refresh_from_db()
    assert t.name == "Mara Lind"
    # delete
    views.teacher_delete(_cab("post"), pk=t.pk)
    assert not Teacher.objects.filter(pk=t.pk).exists()


def test_event_form_saves_teachers():
    from apps.events.forms import EventForm

    mara = Teacher.objects.create(name="Mara")
    form = EventForm(
        data={
            "title": "Retreat",
            "starts_at": "2099-01-01T10:00",
            "capacity": 20,
            "price_eur": "0",
            "teachers": [str(mara.pk)],
        }
    )
    assert form.is_valid(), form.errors
    event = form.save()
    assert list(event.teachers.all()) == [mara]
