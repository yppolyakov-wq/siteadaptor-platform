"""KA-12 A-2 (HW-2/G-4): ручная заявка принимает то же, что /anfrage/ (PLZ, фото,
событие, авто, источник), а эти поля правятся в карточке — с presence-guard (W0)."""

import io
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory

from apps.jobs import services, views
from apps.jobs.models import Job
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

CATERING = {"anfrage": {"fields": ["date", "guests", "event_type"], "event_types": ["Hochzeit"]}}


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", data=None, tenant=None):
    request = getattr(RequestFactory(), method)("/dashboard/auftraege/neu/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(username=f"o-{owner}", password="pw1234567")
    request.tenant = tenant if tenant is not None else TenantFactory.build()
    return request


def _png():
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, "PNG")
    return SimpleUploadedFile("x.png", buf.getvalue(), content_type="image/png")


def test_manual_request_takes_plz_source_event_and_photo():
    tenant = TenantFactory.build(site_config=CATERING)
    data = {
        "title": "Hochzeit Meyer",
        "name": "Frau Meyer",
        "site_plz": "42651",
        "source": "manual-referral",
        "event_date": "2026-12-12",
        "guest_count": "80",
        "event_type": "Sommerfest",  # свой вид — кабинету можно
        "photos": [_png()],
    }
    views.job_new(_req("post", data=data, tenant=tenant))
    job = Job.objects.get(title="Hochzeit Meyer")
    assert job.site_plz == "42651" and job.source_channel == "manual-referral"
    assert job.guest_count == 80 and job.event_type == "Sommerfest"
    assert str(job.event_date) == "2026-12-12"
    assert job.photos.count() == 1


def test_unknown_source_falls_back_and_vehicle_only_for_workshop():
    views.job_new(
        _req("post", data={"title": "A", "name": "B", "source": "portal", "vehicle_plate": "x"})
    )
    job = Job.objects.get(title="A")
    assert job.source_channel == "manual" and job.vehicle_plate == ""
    werkstatt = TenantFactory.build(business_type="werkstatt")
    views.job_new(
        _req("post", data={"title": "C", "name": "D", "vehicle_plate": "m-ab 12"}, tenant=werkstatt)
    )
    assert Job.objects.get(title="C").vehicle_plate == "M-AB 12"


def test_new_form_shows_event_and_vehicle_fields_by_config():
    body = views.job_new(_req(tenant=TenantFactory.build(site_config=CATERING))).content.decode()
    assert 'name="guest_count"' in body and 'name="vehicle_plate"' not in body
    assert 'enctype="multipart/form-data"' in body and 'name="source"' in body
    body = views.job_new(_req(tenant=TenantFactory.build(business_type="werkstatt"))).content
    assert b'name="vehicle_plate"' in body and b'name="guest_count"' not in body


def _post_detail(job, data):
    return views.job_detail(_req("post", data=data), pk=job.pk)


def test_card_edit_request_fields_with_presence_guard():
    job = services.create_job(
        title="Alt", name="K", description="Text", site_plz="10115", guest_count=20
    )
    _post_detail(job, {"action": "request", "title": "Neu", "site_plz": "42651"})
    job.refresh_from_db()
    assert job.title == "Neu" and job.site_plz == "42651"
    assert job.description == "Text" and job.guest_count == 20  # не пришло — не стёрто
    _post_detail(
        job,
        {"action": "request", "event_present": "1", "guest_count": "35", "event_type": "Feier"},
    )
    job.refresh_from_db()
    assert job.guest_count == 35 and job.event_type == "Feier"


def test_card_edit_allowed_after_quote_accepted():
    from apps.jobs.state_machine import JobSM

    job = services.create_job(title="T", name="K")
    services.set_lines(job, [{"text": "Arbeit", "qty": 1, "unit_price": "10.00"}])
    for dst in ("quoted", "accepted"):
        JobSM().apply(job, dst)
    _post_detail(job, {"action": "request", "event_present": "1", "guest_count": "12"})
    job.refresh_from_db()
    assert job.guest_count == 12


def test_card_adds_photos_up_to_limit():
    job = services.create_job(title="F", name="K")
    _post_detail(job, {"action": "photos", "photos": [_png(), _png()]})
    assert job.photos.count() == 2
    _post_detail(job, {"action": "photos", "photos": [_png() for _ in range(6)]})
    assert job.photos.count() == services.MAX_PHOTOS


def test_unparseable_event_value_keeps_previous_and_accepted_edit_is_audited():
    from apps.audit.models import AuditEvent
    from apps.jobs.state_machine import JobSM

    job = services.create_job(title="G", name="K", guest_count=40)
    _post_detail(job, {"action": "request", "event_present": "1", "guest_count": "abc"})
    job.refresh_from_db()
    assert job.guest_count == 40
    services.set_lines(job, [{"text": "Arbeit", "qty": 1, "unit_price": "10.00"}])
    for dst in ("quoted", "accepted"):
        JobSM().apply(job, dst)
    _post_detail(job, {"action": "request", "event_present": "1", "guest_count": "60"})
    assert AuditEvent.objects.filter(action="job.request_edit", resource_id=str(job.pk)).exists()
