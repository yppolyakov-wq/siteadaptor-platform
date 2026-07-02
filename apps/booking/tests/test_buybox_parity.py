"""UA3-2 (шаг 0): характеризационные замки формы брони слот-пикера услуги ДО свода
на контрактный путь `_buybox.html` — точный набор полей POST-формы, action и гейт
«форма только при выбранном слоте» (план docs/ua3-2-two-step-buybox-plan-2026-07-02.md §4)."""

import re
import uuid
from datetime import time, timedelta

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.booking import availability, public_views
from apps.booking.models import AvailabilityRule, Resource, Service
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

DAY = timezone.localdate() + timedelta(days=7)  # заведомо в будущем (см. test_public)


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def form_block(body, action_attr):
    """Единственный <form>…</form> с этим action= в открывающем теге."""
    forms = re.findall(r"<form[^>]*>.*?</form>", body, flags=re.S)
    hits = [f for f in forms if action_attr in f[: f.index(">")]]
    assert len(hits) == 1, f"{len(hits)} forms with {action_attr}"
    return hits[0]


def field_names(form_html):
    """Точный набор name= полей формы (input/select/textarea, включая hidden)."""
    return set(re.findall(r'name="([^"]+)"', form_html))


def _resource():
    resource = Resource.objects.create(name=f"R {uuid.uuid4().hex[:6]}")
    AvailabilityRule.objects.create(
        resource=resource,
        weekday=DAY.weekday(),
        start_time=time(10, 0),
        end_time=time(13, 0),
        slot_minutes=60,
    )
    return resource


def _service():
    return Service.objects.create(name="Ölwechsel", duration_minutes=60, price_cents=4900)


def _slots_page(service, params):
    request = RequestFactory().get(f"/termin/leistung/{service.pk}/", params)
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(business_type="cafe")
    return public_views.service_slots(request, pk=service.pk).content.decode()


def test_book_form_base_exact_fields():
    _resource()
    service = _service()
    slot = availability.service_slots(service, DAY)[0]
    body = _slots_page(service, {"tag": DAY.isoformat(), "slot": slot.isoformat()})
    form = form_block(body, f'action="/termin/leistung/{service.pk}/buchen/"')
    assert field_names(form) == {
        "csrfmiddlewaretoken",
        "start",  # hidden ISO выбранного слота
        "website",  # honeypot
        "name",
        "email",
        "phone",
        "note",
    }
    assert f'name="start" value="{slot.isoformat()}"' in form


def test_book_form_with_resource_and_embed_fields():
    r1 = _resource()
    _resource()  # второй ресурс → пикер мастера активен
    service = _service()
    slot = availability.service_slots(service, DAY, resource=r1)[0]
    body = _slots_page(
        service,
        {"tag": DAY.isoformat(), "slot": slot.isoformat(), "resource": str(r1.pk), "embed": "1"},
    )
    form = form_block(body, f'action="/termin/leistung/{service.pk}/buchen/"')
    assert field_names(form) == {
        "csrfmiddlewaretoken",
        "embed",  # G10 iframe-carry
        "start",
        "resource",  # hidden pk выбранного мастера
        "website",
        "name",
        "email",
        "phone",
        "note",
    }


def test_no_slot_selected_hint_not_form():
    _resource()
    service = _service()
    body = _slots_page(service, {"tag": DAY.isoformat()})
    assert f"/termin/leistung/{service.pk}/buchen/" not in body  # POST-формы нет
    assert "Pick a time to continue." in body  # хинт при доступных стартах
