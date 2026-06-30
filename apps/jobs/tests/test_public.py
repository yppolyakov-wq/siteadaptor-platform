"""G6 / F3: публичная заявка /anfrage/ + публичное Angebot /angebot/<token>/
(онлайн-принятие/отклонение) + письмо клиенту со сметой."""

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory

from apps.jobs import public_views, services
from apps.jobs.models import Job
from apps.jobs.state_machine import JobSM
from apps.notifications.models import Notification
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(**kwargs):
    kwargs.setdefault("disabled_modules", [])  # jobs активен
    return TenantFactory.build(**kwargs)


def _req(method="get", path="/anfrage/", data=None, tenant=None):
    import uuid

    request = getattr(RequestFactory(), method)(path, data or {})
    # Уникальный IP на запрос — иначе общий счётчик rate-limit «anfrage» (5/окно)
    # переполняется при нескольких POST-тестах в одном прогоне (кэш делится).
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.9"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant if tenant is not None else _tenant()
    return request


def _quoted_job(email="kunde@test.de"):
    job = services.create_job(title="Bad streichen", name="Kunde", email=email)
    services.set_lines(job, [{"text": "Arbeit", "qty": 4, "unit_price": "50.00"}])
    return JobSM().apply(job, "quoted")


# --- заявка -----------------------------------------------------------------------


def test_anfrage_gating_404():
    request = _req(tenant=_tenant(disabled_modules=["jobs"]))
    with pytest.raises(Http404):
        public_views.anfrage(request)


def test_anfrage_creates_job():
    request = _req("post", data={"title": "Zaun bauen", "name": "Herr Meyer", "email": "m@t.de"})
    resp = public_views.anfrage(request)
    assert resp.status_code == 302
    job = Job.objects.get(title="Zaun bauen")
    assert job.status == "new"


def test_anfrage_requires_title_and_name():
    request = _req("post", data={"title": "", "name": ""})
    public_views.anfrage(request)
    assert not Job.objects.exists()


def test_anfrage_form_renders():
    body = public_views.anfrage(_req()).content.decode()
    assert "Request a quote" in body or "Anfrage" in body


# --- A9: структурные данные авто (Kfz-Werkstatt) ----------------------------------
def test_anfrage_shows_vehicle_fields_and_autorepair_ld_when_workshop():
    tenant = _tenant(site_config={"jobs_vehicle": True}, name="Werkstatt Dreyer")
    body = public_views.anfrage(_req(tenant=tenant)).content.decode()
    assert 'name="vehicle_plate"' in body and 'name="vehicle_hsn"' in body
    assert '"@type":"AutoRepair"' in body  # JSON-LD


def test_anfrage_hides_vehicle_fields_by_default():
    body = public_views.anfrage(_req()).content.decode()  # jobs_vehicle off
    assert 'name="vehicle_hsn"' not in body
    assert "AutoRepair" not in body


# --- A7: Einzugsgebiet / зона обслуживания ----------------------------------------
def test_service_area_plz_list_parses_and_dedups():
    t = TenantFactory.build(service_area_plz="40724, 42697 40724;50667")
    assert t.service_area_plz_list == ["40724", "42697", "50667"]  # uniq, 5 цифр, порядок
    assert t.has_service_area


def test_serves_plz_logic():
    t = TenantFactory.build(service_area_plz="40724, 42697")
    assert t.serves_plz("40724") and not t.serves_plz("99999")
    assert TenantFactory.build(service_area_plz="").serves_plz("99999")  # без списка — везде


def test_anfrage_shows_service_area_banner_and_plz_field():
    tenant = _tenant(service_area_plz="40724, 42697", service_area_note="Hilden und Umgebung")
    body = public_views.anfrage(_req(tenant=tenant)).content.decode()
    assert "Hilden und Umgebung" in body and "40724" in body
    assert 'name="site_plz"' in body  # поле PLZ показано


def test_anfrage_hides_service_area_when_unset():
    body = public_views.anfrage(_req()).content.decode()  # зона не задана
    assert 'name="site_plz"' not in body


def test_anfrage_stores_site_plz_and_warns_when_outside_area():
    from django.contrib.messages import get_messages

    tenant = _tenant(service_area_plz="40724, 42697")
    request = _req(
        "post", data={"title": "Malern", "name": "X", "site_plz": "99999"}, tenant=tenant
    )
    public_views.anfrage(request)
    assert Job.objects.get(title="Malern").site_plz == "99999"
    texts = [m.message for m in get_messages(request)]
    assert any("outside our usual service area" in t for t in texts)


def test_anfrage_no_warning_when_plz_in_area():
    from django.contrib.messages import get_messages

    tenant = _tenant(service_area_plz="40724, 42697")
    request = _req(
        "post", data={"title": "Fliesen", "name": "X", "site_plz": "40724"}, tenant=tenant
    )
    public_views.anfrage(request)
    assert Job.objects.get(title="Fliesen").site_plz == "40724"
    texts = [m.message for m in get_messages(request)]
    assert not any("outside" in t for t in texts)


def test_anfrage_stores_structured_vehicle_data():
    tenant = _tenant(site_config={"jobs_vehicle": True})
    request = _req(
        "post",
        data={
            "title": "Inspektion",
            "name": "Vogel",
            "email": "v@t.de",
            "vehicle": "VW Golf",
            "vehicle_plate": "do-mv 1234",
            "vehicle_hsn": "0603",
            "vehicle_tsn": "bnv",
        },
        tenant=tenant,
    )
    public_views.anfrage(request)
    job = Job.objects.get(title="Inspektion")
    assert job.vehicle_plate == "DO-MV 1234"  # верхний регистр
    assert job.vehicle_hsn == "0603" and job.vehicle_tsn == "BNV"


# --- публичное Angebot ------------------------------------------------------------


def test_quoted_sends_customer_email():
    job = _quoted_job()
    assert Notification.objects.filter(dedupe_key=f"job:{job.id}:quoted:customer").exists()


def test_angebot_renders_with_lines():
    job = _quoted_job()
    body = public_views.angebot(_req(), token=job.public_token).content.decode()
    assert job.reference_code in body and "Arbeit" in body


def test_angebot_accept():
    job = _quoted_job()
    request = _req("post", path=f"/angebot/{job.public_token}/", data={"action": "accept"})
    resp = public_views.angebot(request, token=job.public_token)
    assert resp.status_code == 302
    job.refresh_from_db()
    assert job.status == "accepted" and job.accepted_at is not None


def test_angebot_decline():
    job = _quoted_job()
    request = _req("post", path=f"/angebot/{job.public_token}/", data={"action": "decline"})
    public_views.angebot(request, token=job.public_token)
    job.refresh_from_db()
    assert job.status == "declined"


def test_angebot_accept_only_from_quoted():
    job = _quoted_job()
    JobSM().apply(job, "accepted")  # уже принято
    request = _req("post", path=f"/angebot/{job.public_token}/", data={"action": "decline"})
    public_views.angebot(request, token=job.public_token)
    job.refresh_from_db()
    assert job.status == "accepted"  # повторное решение игнорируется


# --- A7c: онлайн-Anzahlung за смету ----------------------------------------------


def _with_deposit(job, cents=5000):
    job.deposit_cents = cents
    job.save(update_fields=["deposit_cents", "updated_at"])
    return job


def test_mark_deposit_paid_accepts_quote():
    from django.db import connection

    from apps.jobs import payments

    job = _with_deposit(_quoted_job())
    ok = payments.mark_deposit_paid(
        tenant_schema=connection.schema_name, job_id=str(job.id), payment_intent="pi_1"
    )
    assert ok
    job.refresh_from_db()
    assert job.payment_state == "paid"
    assert job.status == "accepted" and job.accepted_at is not None
    assert job.stripe_payment_intent == "pi_1"
    # идемпотентно (повтор вебхука)
    assert payments.mark_deposit_paid(tenant_schema=connection.schema_name, job_id=str(job.id))


def test_angebot_accept_with_deposit_redirects_to_checkout(monkeypatch):
    from apps.billing import connect
    from apps.jobs import payments

    job = _with_deposit(_quoted_job())
    monkeypatch.setattr(connect, "is_connect_configured", lambda: True)
    monkeypatch.setattr(payments, "deposit_checkout_url", lambda *a, **k: "https://stripe.test/pay")
    tenant = _tenant(payments_enabled=True, stripe_connect_id="acct_1")
    request = _req(
        "post", path=f"/angebot/{job.public_token}/", data={"action": "accept"}, tenant=tenant
    )
    resp = public_views.angebot(request, token=job.public_token)
    assert resp.status_code == 302 and resp.url == "https://stripe.test/pay"
    job.refresh_from_db()
    assert job.status == "quoted"  # принятие — только после оплаты (вебхук)


def test_angebot_accept_deposit_but_payments_off_is_direct():
    job = _with_deposit(_quoted_job())
    tenant = _tenant(payments_enabled=False)  # оплата не подключена → прямой accept
    request = _req(
        "post", path=f"/angebot/{job.public_token}/", data={"action": "accept"}, tenant=tenant
    )
    public_views.angebot(request, token=job.public_token)
    job.refresh_from_db()
    assert job.status == "accepted"


# --- A7b: фото к заявке ----------------------------------------------------------


def _png_upload(name="damage.png"):
    import io

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "blue").save(buf, format="PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def test_anfrage_with_photo_creates_jobphoto(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    from apps.jobs.models import JobPhoto

    request = _req(
        "post", path="/anfrage/", data={"title": "Wand", "name": "Kunde", "photos": _png_upload()}
    )
    public_views.anfrage(request)
    job = Job.objects.get()
    assert JobPhoto.objects.filter(job=job).count() == 1


def test_anfrage_skips_non_image(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.jobs.models import JobPhoto

    bad = SimpleUploadedFile("note.txt", b"hello", content_type="text/plain")
    request = _req("post", path="/anfrage/", data={"title": "Wand", "name": "Kunde", "photos": bad})
    public_views.anfrage(request)
    assert JobPhoto.objects.count() == 0  # не-изображение отброшено
