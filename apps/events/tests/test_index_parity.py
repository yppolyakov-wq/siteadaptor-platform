"""UB1-3 C0: характеризационные тесты листинга событий — снапшот-паритет структуры
list/grid ДО и ПОСЛЕ свода на каркас listing.html. Фиксируют: порядок блоков
(заголовок → фильтры → грид), контейнеры обоих режимов, разметку карточек,
порядок событий и empty-state. Ломаются при структурной регрессии свода."""

import uuid
from datetime import timedelta

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.events import public_views
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
        "title": "Konzert",
        "starts_at": timezone.now() + timedelta(days=10),
        "status": Event.STATUS_PUBLISHED,
        "price_cents": 0,
        "capacity": 50,
    }
    defaults.update(kw)
    return Event.objects.create(**defaults)


def _body(data=None, tenant=None):
    return public_views.veranstaltung_index(_req(data, tenant)).content.decode()


def test_event_index_list_structure_snapshot():
    """Дефолт (events_index_layout=list): заголовок → контейнер списка space-y-3,
    горизонтальные карточки-строки, порядок по starts_at, ссылка на календарь."""
    _event(title="Alpha Retreat", starts_at=timezone.now() + timedelta(days=5), price_cents=2500)
    _event(title="Beta Konzert", starts_at=timezone.now() + timedelta(days=9))
    body = _body()
    assert 'data-sf-section="events" class="space-y-3"' in body  # list-контейнер
    assert body.index("Retreats") < body.index('data-sf-section="events"')  # header выше грида
    assert "flex gap-4 bg-white rounded-2xl" in body  # горизонтальная строка-карточка
    assert body.index("Alpha Retreat") < body.index("Beta Konzert")  # порядок по дате
    assert "storefront-events-calendar" in body or "/kalender/" in body or "Calendar" in body
    assert "data-price-edit" in body and "data-photo-edit" in body  # инлайн-едит замки
    assert "🗓" in body  # мета-строка даты


def test_event_index_grid_structure_snapshot():
    """Грид-режим (пресет cols3): движковый грид вместо space-y-3, крупные обложки
    aspect-[4/3] с ховер-зумом и оверлей-бейджами."""
    _event(title="Alpha Retreat", price_cents=2500)
    tenant = TenantFactory.build()
    tenant.site_config = {"events_index_layout": {"preset": "cols3"}}
    body = _body(tenant=tenant)
    assert 'data-sf-section="events" class="space-y-3"' not in body  # list-контейнер ушёл
    assert "lg:grid-cols-3" in body and 'data-sf-section="events"' in body
    # обложка aspect-[4/3] + зона оверлей-бейджей (безусловные части грид-карточки;
    # ховер-зум живёт на <img> и требует фото — не ассертим на событии без фото)
    assert "aspect-[4/3]" in body and "absolute top-2 left-2" in body
    assert "data-price-edit" in body


def test_event_index_filters_panel_before_grid():
    """Активный фильтр раскрывает панель фасетов; панель стоит ВЫШЕ грида;
    сброс ведёт на чистый листинг."""
    _event(title="Stadtfest", city="Bern")
    _event(title="Landfest", city="Chur")
    body = _body(data={"city": "Bern"})
    assert "<details" in body and body.index("<details") < body.index('data-sf-section="events"')
    assert 'name="city"' in body  # фасет города присутствует
    assert "Stadtfest" in body and "Landfest" not in body  # фильтр реально применён
    assert "Reset" in body or "storefront-events" in body  # сброс фильтров


def test_event_index_empty_states():
    """Пустой листинг: без фильтров и с фильтрами — разные подписи."""
    body = _body()
    assert "No upcoming events." in body
    _event(title="Solo", city="Bern")
    body_filtered = _body(data={"city": "Zermatt"})
    assert "No events match your filters." in body_filtered
