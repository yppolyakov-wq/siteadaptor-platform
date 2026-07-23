"""R2: таксономия событий (направление/уровень/язык/длительность) + фильтры каталога."""

import uuid
from datetime import datetime, timedelta

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.events import public_views, taxonomy
from apps.events.models import Event
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(data=None, tenant=None):
    request = RequestFactory().get("/veranstaltung/", data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.7"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant or TenantFactory.build()
    return request


def _event(**kw):
    defaults = {
        "title": "Event",
        "starts_at": timezone.now() + timedelta(days=10),
        "status": Event.STATUS_PUBLISHED,
        "price_cents": 0,
        "capacity": 20,
    }
    defaults.update(kw)
    return Event.objects.create(**defaults)


# --- taxonomy --------------------------------------------------------------
def test_duration_kind_classifies_by_dates():
    # Якорим на фиксированное утро: duration_kind считает по разнице КАЛЕНДАРНЫХ
    # дат, поэтому now()+6ч поздним вечером пересекало бы полночь (flaky → wochenende).
    start = timezone.make_aware(datetime(2026, 6, 1, 9, 0))  # утро — +6ч не пересекает полночь
    assert taxonomy.duration_kind(start, None) == "tag"
    assert taxonomy.duration_kind(start, start + timedelta(hours=6)) == "tag"  # тот же день
    assert taxonomy.duration_kind(start, start + timedelta(days=2)) == "wochenende"
    assert taxonomy.duration_kind(start, start + timedelta(days=5)) == "mehrtaegig"


def test_event_labels_resolve():
    ev = _event(category="yoga", level="anfaenger", language="de")
    assert ev.category_label == "Yoga"
    assert ev.level_label == "Anfänger"
    assert ev.language_label == "Deutsch"


# --- catalog filters -------------------------------------------------------
def test_facets_only_include_present_values():
    _event(category="yoga", city="Freiburg", level="alle")
    _event(category="meditation", city="Berlin")
    body = public_views.veranstaltung_index(_req()).content.decode()
    # обе категории присутствуют в фасетах → есть опции
    assert "Yoga" in body and "Meditation" in body
    assert "Freiburg" in body and "Berlin" in body
    # Ayurveda нет ни у одного события → опции нет
    assert "Ayurveda" not in body


def test_filter_by_category():
    _event(title="Yoga-Tag", category="yoga")
    _event(title="Klang-Abend", category="klang")
    body = public_views.veranstaltung_index(_req({"cat": "yoga"})).content.decode()
    assert "Yoga-Tag" in body and "Klang-Abend" not in body


def test_filter_by_city_case_insensitive():
    _event(title="In Freiburg", city="Freiburg")
    _event(title="In Berlin", city="Berlin")
    body = public_views.veranstaltung_index(_req({"city": "freiburg"})).content.decode()
    assert "In Freiburg" in body and "In Berlin" not in body


def test_filter_by_duration():
    # Будущая дата, но утренний час: +5ч не пересекает полночь (иначе days=1 →
    # «Tagesding» ошибочно станет wochenende; flaky по времени суток UTC).
    start = (timezone.now() + timedelta(days=10)).replace(hour=9, minute=0, second=0, microsecond=0)
    _event(title="Wochenende", starts_at=start, ends_at=start + timedelta(days=2))
    _event(title="Tagesding", starts_at=start, ends_at=start + timedelta(hours=5))
    body = public_views.veranstaltung_index(_req({"dur": "wochenende"})).content.decode()
    assert "Wochenende" in body and "Tagesding" not in body


def test_filter_by_month():
    start = timezone.now() + timedelta(days=10)
    ev = _event(title="DiesenMonat", starts_at=start)
    _event(title="Später", starts_at=start + timedelta(days=90))
    body = public_views.veranstaltung_index(
        _req({"month": ev.starts_at.strftime("%Y-%m")})
    ).content.decode()
    assert "DiesenMonat" in body and "Später" not in body


def test_no_match_shows_empty_message():
    _event(category="yoga")
    body = public_views.veranstaltung_index(_req({"cat": "ayurveda"})).content.decode()
    assert "yoga" not in body.lower() or "match" in body.lower()


# --- M20U-7: раскладка индекса событий (список/сетка) ------------------------
def test_events_index_default_is_list():
    _event(title="Yoga-Tag")
    body = public_views.veranstaltung_index(_req()).content.decode()
    assert "space-y-3" in body  # дефолт — вертикальный список


def test_events_index_grid_from_config():
    _event(title="Yoga-Tag")
    tenant = TenantFactory.build()
    tenant.site_config = {"events_index_layout": {"preset": "cols2"}}
    body = public_views.veranstaltung_index(_req(tenant=tenant)).content.decode()
    assert "lg:grid-cols-2" in body  # сетка вместо списка


# --- M20U-3: фильтры по умолчанию свёрнуты/скрыты на маленькой витрине -------
def test_filters_hidden_on_small_storefront():
    # ≤ порога событий и без активного фильтра → панель фильтров не выводится.
    _event(category="yoga", city="Freiburg")
    _event(category="meditation", city="Berlin")
    body = public_views.veranstaltung_index(_req()).content.decode()
    assert 'name="cat"' not in body  # селектов фильтра нет
    # DL-1: свитчер языков — тоже <details>; проверяем ИМЕННО панель фильтров.
    assert '<details class="mb-5"' not in body


def test_filters_collapsed_when_enough_events():
    # > порога событий → панель есть, но свёрнута (<details без open).
    for i in range(public_views._FILTER_MIN_EVENTS + 1):
        _event(title=f"E{i}", category="yoga", city="Freiburg")
    body = public_views.veranstaltung_index(_req()).content.decode()
    assert '<details class="mb-5"' in body and 'name="cat"' in body
    assert "open>" not in body  # без активного фильтра — свёрнута


def test_filters_expanded_when_active():
    # активный фильтр → панель раскрыта (open), даже если событий мало.
    _event(title="Yoga-Tag", category="yoga")
    _event(title="Klang", category="klang")
    body = public_views.veranstaltung_index(_req({"cat": "yoga"})).content.decode()
    assert '<details class="mb-5"' in body and "open>" in body


# --- cabinet form ----------------------------------------------------------
def test_form_saves_taxonomy():
    from apps.events.forms import EventForm

    form = EventForm(
        data={
            "title": "Retreat",
            "starts_at": "2099-01-01T10:00",
            "capacity": 0,
            "price_eur": "0",
            "city": "Freiburg",
            "category": "yoga",
            "level": "anfaenger",
            "language": "de",
        }
    )
    assert form.is_valid(), form.errors
    event = form.save()
    assert event.city == "Freiburg"
    assert (event.category, event.level, event.language) == ("yoga", "anfaenger", "de")
    # повторная инициализация формой подставляет значения
    assert EventForm(instance=event).fields["category"].initial == "yoga"
