"""KA-12 A-5 (HW-3): фото мастера (до/после) и акт сдачи-приёмки (Abnahmeprotokoll)
с PDF и онлайн-подтверждением клиента на /auftrag/<token>/ — один раз, без смены статуса."""

import io
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import Http404
from django.test import RequestFactory

from apps.jobs import public_views, services, views
from apps.jobs.models import JobPhoto, JobProtocol
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings, tmp_path):
    settings.ROOT_URLCONF = "config.urls_tenant"
    settings.MEDIA_ROOT = str(tmp_path)


def _session(request):
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(disabled_modules=[])
    return request


def _cab(method="get", data=None):
    request = _session(getattr(RequestFactory(), method)("/dashboard/auftraege/x/", data or {}))
    owner = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(username=f"o-{owner}", password="pw1234567")
    return request


def _pub(method="get", data=None):
    request = getattr(RequestFactory(), method)("/auftrag/x/", data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.7"
    return _session(request)


def _png():
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "green").save(buf, "PNG")
    return SimpleUploadedFile("x.png", buf.getvalue(), content_type="image/png")


def _job():
    return services.create_job(title="Bad fliesen", name="Frau Kern")


def _protocol(job, **extra):
    data = {
        "action": "protocol",
        "kind": "handover",
        "date": "2026-10-20",
        "items": "Fugen sauber\n✗ Silikon Ecke links fehlt",
        "notes": "Rest am Freitag",
        "mileage_km": "",
        "signed_name": "",
        "release": "1",
    }
    data.update(extra)
    return views.job_detail(_cab("post", data), pk=job.pk)


def test_master_photos_do_not_eat_customer_limit():
    job = _job()
    views.job_detail(
        _cab("post", {"action": "photos", "kind": "after", "photos": [_png() for _ in range(6)]}),
        pk=job.pk,
    )
    assert job.photos.filter(kind="after").count() == 6
    views.job_detail(
        _cab("post", {"action": "photos", "photos": [_png() for _ in range(6)]}), pk=job.pk
    )
    assert job.photos.filter(kind="customer").count() == services.MAX_PHOTOS
    photo = job.photos.filter(kind="after").first()
    assert photo.uploaded_by is not None


def test_unknown_photo_kind_falls_back_to_customer():
    job = _job()
    views.job_detail(
        _cab("post", {"action": "photos", "kind": "evil", "photos": [_png()]}), pk=job.pk
    )
    assert JobPhoto.objects.get(job=job).kind == "customer"


def test_protocol_saved_with_items_and_defect_marks():
    job = _job()
    _protocol(job)
    proto = JobProtocol.objects.get(job=job, kind="handover")
    assert proto.items == [
        {"label": "Fugen sauber", "ok": True},
        {"label": "Silikon Ecke links fehlt", "ok": False},
    ]
    assert str(proto.date) == "2026-10-20" and proto.notes == "Rest am Freitag"
    _protocol(job, notes="geändert")
    assert JobProtocol.objects.filter(job=job).count() == 1
    proto.refresh_from_db()
    assert proto.notes == "geändert"


def test_customer_confirms_once_without_status_change():
    from apps.audit.models import AuditEvent

    job = _job()
    _protocol(job)
    status = job.status
    data = {"action": "confirm_protocol", "name": "Anna Kern", "checked": "1"}
    public_views.auftrag_status(_pub("post", data), token=job.public_token)
    proto = JobProtocol.objects.get(job=job)
    first = proto.confirmed_online_at
    assert first and proto.confirmed_name == "Anna Kern"
    public_views.auftrag_status(_pub("post", {**data, "name": "Jemand"}), token=job.public_token)
    proto.refresh_from_db()
    assert proto.confirmed_online_at == first and proto.confirmed_name == "Anna Kern"
    job.refresh_from_db()
    assert job.status == status
    assert (
        AuditEvent.objects.filter(
            action="job.protocol_confirmed", resource_id=str(proto.pk)
        ).count()
        == 1
    )


def test_confirmation_needs_name_and_check():
    job = _job()
    _protocol(job)
    public_views.auftrag_status(
        _pub("post", {"action": "confirm_protocol", "name": "A"}), token=job.public_token
    )
    public_views.auftrag_status(
        _pub("post", {"action": "confirm_protocol", "name": "", "checked": "1"}),
        token=job.public_token,
    )
    assert JobProtocol.objects.get(job=job).confirmed_online_at is None


def test_confirmed_protocol_is_frozen_in_cabinet():
    job = _job()
    _protocol(job)
    public_views.auftrag_status(
        _pub("post", {"action": "confirm_protocol", "name": "Anna", "checked": "1"}),
        token=job.public_token,
    )
    _protocol(job, notes="nachträglich")
    assert JobProtocol.objects.get(job=job).notes == "Rest am Freitag"


def test_public_page_shows_protocol_and_after_photos_only():
    job = _job()
    _protocol(job)
    views.job_detail(
        _cab("post", {"action": "photos", "kind": "after", "photos": [_png()]}), pk=job.pk
    )
    views.job_detail(
        _cab("post", {"action": "photos", "kind": "before", "photos": [_png()]}), pk=job.pk
    )
    body = public_views.auftrag_status(_pub(), token=job.public_token).content.decode()
    assert "Silikon Ecke links fehlt" in body and 'name="confirm_protocol"' not in body
    assert 'value="confirm_protocol"' in body
    after = job.photos.get(kind="after").image.url
    before = job.photos.get(kind="before").image.url
    assert after in body and before not in body


def test_unknown_token_404():
    with pytest.raises(Http404):
        public_views.auftrag_status(_pub(), token=uuid.uuid4())


def test_protocol_pdf_renders():
    job = _job()
    _protocol(job)
    response = views.job_protocol_pdf(_cab(), pk=job.pk, kind="handover")
    assert response["Content-Type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    with pytest.raises(Http404):
        views.job_protocol_pdf(_cab(), pk=job.pk, kind="intake")


def test_dsgvo_erases_customer_photos_and_names_keeps_protocol():
    from apps.crm import dsgvo

    job = _job()
    views.job_detail(_cab("post", {"action": "photos", "photos": [_png()]}), pk=job.pk)
    views.job_detail(
        _cab("post", {"action": "photos", "kind": "after", "photos": [_png()]}), pk=job.pk
    )
    _protocol(job, signed_name="Anna Kern")
    export = dsgvo.export_customer(job.customer)
    row = export["data"]["jobs.Job"][0]
    assert len(row["photos"]) == 2 and row["protocols"][0]["signed_name"] == "Anna Kern"
    job.status = "cancelled"
    job.save(update_fields=["status"])
    dsgvo.erase_customer(job.customer)
    assert not job.photos.filter(kind="customer").exists()
    assert job.photos.filter(kind="after").exists()
    proto = JobProtocol.objects.get(job=job)
    assert proto.signed_name == "" and proto.confirmed_name == "" and proto.notes == ""
    assert proto.items  # пункты акта остаются (доказательство Abnahme)


def test_draft_protocol_is_hidden_and_not_confirmable():
    job = _job()
    _protocol(job, release="")
    body = public_views.auftrag_status(_pub(), token=job.public_token).content.decode()
    assert "Silikon Ecke links fehlt" not in body
    data = {"action": "confirm_protocol", "name": "Anna", "checked": "1"}
    public_views.auftrag_status(_pub("post", data), token=job.public_token)
    assert JobProtocol.objects.get(job=job).confirmed_online_at is None


def test_plain_x_item_is_not_a_defect_and_round_trips():
    items = services.parse_protocol_items("x 2 Steckdosen geprüft\n✗ Kratzer")
    assert items == [
        {"label": "x 2 Steckdosen geprüft", "ok": True},
        {"label": "Kratzer", "ok": False},
    ]


def test_after_photos_frozen_after_confirmation():
    job = _job()
    _protocol(job)
    data = {"action": "confirm_protocol", "name": "Anna", "checked": "1"}
    public_views.auftrag_status(_pub("post", data), token=job.public_token)
    views.job_detail(
        _cab("post", {"action": "photos", "kind": "after", "photos": [_png()]}), pk=job.pk
    )
    assert not job.photos.filter(kind="after").exists()


def test_cancelled_job_cannot_confirm():
    job = _job()
    _protocol(job)
    job.status = "cancelled"
    job.save(update_fields=["status"])
    with pytest.raises(Http404):
        public_views.auftrag_status(
            _pub("post", {"action": "confirm_protocol", "name": "A", "checked": "1"}),
            token=job.public_token,
        )
