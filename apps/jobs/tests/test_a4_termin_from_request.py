"""KA-12 A-4 (HW-2): «📅 Termin anlegen» прямо из заявки — тем же ядром, что ручная
запись в Tagesplan (`booking.services.create_manual`), на клиента заявки, со связью."""

import uuid
from datetime import datetime, time, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.booking.models import Booking, Resource, Service
from apps.jobs import services, views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None, tenant=None):
    request = getattr(RequestFactory(), method)("/dashboard/auftraege/x/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(username=f"o-{owner}", password="pw1234567")
    request.tenant = tenant if tenant is not None else TenantFactory.build(disabled_modules=[])
    return request


def _start(days=7, hour=10):
    day = timezone.localdate() + timedelta(days=days)
    return datetime.combine(day, time(hour, 0)).strftime("%Y-%m-%dT%H:%M")


def _job(**kw):
    # Клиент без e-mail и телефона: поиск по контактам завёл бы второго «Walk-in».
    return services.create_job(name="Frau Meyer", title="Zaun reparieren", **kw)


def test_termin_is_created_on_request_customer_and_linked():
    resource = Resource.objects.create(name=f"Monteur {uuid.uuid4().hex[:5]}")
    service = Service.objects.create(name="Aufmaß", price_cents=5000, duration_minutes=90)
    job = _job()
    data = {
        "action": "create_booking",
        "resource": str(resource.pk),
        "start": _start(),
        "service": str(service.pk),
        "override_hours": "1",
    }
    views.job_detail(_req("post", data=data), pk=job.pk)
    job.refresh_from_db()
    booking = job.booking
    assert booking is not None and booking.customer_id == job.customer_id
    assert booking.status == "confirmed" and booking.source_channel == "manual"
    assert booking.price_cents == 5000
    assert booking.end - booking.start == timedelta(minutes=90)
    assert job.reference_code in booking.note


def test_taken_slot_is_refused_and_nothing_is_linked():
    resource = Resource.objects.create(name=f"Monteur {uuid.uuid4().hex[:5]}")
    job1, job2 = _job(), _job()
    data = {
        "action": "create_booking",
        "resource": str(resource.pk),
        "start": _start(),
        "minutes": "60",
        "override_hours": "1",
    }
    views.job_detail(_req("post", data=data), pk=job1.pk)
    req = _req("post", data=data)
    views.job_detail(req, pk=job2.pk)
    job2.refresh_from_db()
    assert job2.booking_id is None
    assert Booking.objects.filter(resource=resource).count() == 1
    assert any(m.level_tag == "error" for m in get_messages(req))


def test_form_shown_only_with_booking_module_and_resource():
    job = _job()
    body = views.job_detail(_req(), pk=job.pk).content.decode()
    assert "data-job-termin" not in body  # ресурса нет → подсказка, не форма
    Resource.objects.create(name=f"Monteur {uuid.uuid4().hex[:5]}")
    body = views.job_detail(_req(), pk=job.pk).content.decode()
    assert "data-job-termin" in body
    off = TenantFactory.build(disabled_modules=["booking"])
    body = views.job_detail(_req(tenant=off), pk=job.pk).content.decode()
    assert "data-job-termin" not in body


def test_post_without_booking_module_creates_nothing():
    resource = Resource.objects.create(name=f"Monteur {uuid.uuid4().hex[:5]}")
    job = _job()
    off = TenantFactory.build(disabled_modules=["booking"])
    data = {"action": "create_booking", "resource": str(resource.pk), "start": _start()}
    views.job_detail(_req("post", data=data, tenant=off), pk=job.pk)
    job.refresh_from_db()
    assert job.booking_id is None and not Booking.objects.filter(resource=resource).exists()
