"""KA-12 A-6b (Werkstatt): HU-напоминание по машине, Status-Vorlage, письмо
«Abholbereit», заголовок PDF «Fahrzeugannahme»."""

import datetime
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.jobs import services, status_presets, tasks
from apps.jobs.models import Job, JobProtocol, Vehicle
from apps.notifications.models import Notification
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

TODAY = datetime.date(2026, 10, 26)


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(**kw):
    return TenantFactory.build(disabled_modules=[], business_type="werkstatt", **kw)


def _job(plate="M-AB 12", email=None):
    email = email if email is not None else f"{uuid.uuid4().hex[:6]}@example.com"
    job = services.create_job(
        title="Inspektion", name="Herr Lang", email=email, vehicle_plate=plate
    )
    job.refresh_from_db()
    return job


def _hu(job, due):
    Vehicle.objects.filter(pk=job.vehicle_ref_id).update(hu_due=due)


def _hu_mails(job):
    return Notification.objects.filter(
        type="vehicle_hu_reminder", recipient=job.customer.email
    ).count()


# --- HU-напоминание ---------------------------------------------------------


def test_hu_reminder_once_per_date():
    job = _job()
    _hu(job, TODAY + datetime.timedelta(days=10))
    assert tasks.send_due_hu_reminders(today=TODAY, tenant=_tenant()) == 1
    assert tasks.send_due_hu_reminders(today=TODAY, tenant=_tenant()) == 0
    assert _hu_mails(job) == 1
    vehicle = Vehicle.objects.get(pk=job.vehicle_ref_id)
    assert vehicle.hu_reminder_sent_for == vehicle.hu_due
    # новая дата HU → новое письмо
    _hu(job, TODAY + datetime.timedelta(days=15))
    assert tasks.send_due_hu_reminders(today=TODAY, tenant=_tenant()) == 1


def test_hu_outside_window_is_ignored():
    job = _job()
    _hu(job, TODAY + datetime.timedelta(days=60))
    assert tasks.send_due_hu_reminders(today=TODAY, tenant=_tenant()) == 0
    _hu(job, TODAY - datetime.timedelta(days=1))
    assert tasks.send_due_hu_reminders(today=TODAY, tenant=_tenant()) == 0


def test_hu_duplicate_with_service_reminder_is_suppressed():
    job = _job()
    due = TODAY + datetime.timedelta(days=10)
    _hu(job, due)
    from django.utils import timezone

    Job.objects.filter(pk=job.pk).update(
        service_due_date=due, service_reminder_sent_at=timezone.now()
    )
    assert tasks.send_due_hu_reminders(today=TODAY, tenant=_tenant()) == 0
    assert Vehicle.objects.get(pk=job.vehicle_ref_id).hu_reminder_sent_for == due


def test_hu_unsubscribed_customer_not_marked():
    job = _job()
    _hu(job, TODAY + datetime.timedelta(days=10))
    job.customer.unsubscribed = True
    job.customer.save(update_fields=["unsubscribed"])
    assert tasks.send_due_hu_reminders(today=TODAY, tenant=_tenant()) == 0
    assert Vehicle.objects.get(pk=job.vehicle_ref_id).hu_reminder_sent_for is None


def test_hu_channel_off_sends_nothing():
    job = _job()
    _hu(job, TODAY + datetime.timedelta(days=10))
    tenant = _tenant(
        site_config={"notify": {"customer": {"job:service_reminder": {"email": False}}}}
    )
    assert tasks.send_due_hu_reminders(today=TODAY, tenant=tenant) == 0
    assert Vehicle.objects.get(pk=job.vehicle_ref_id).hu_reminder_sent_for is None


def test_beat_survives_failing_tenant(monkeypatch):
    class Boom:
        schema_name = "boom"

    monkeypatch.setattr(tasks, "_iter_tenants", lambda: [Boom()])
    assert tasks.send_service_reminders() == 0  # исключение поймано и залогировано


# --- Status-Vorlage ---------------------------------------------------------


def test_preset_merge_is_idempotent_and_keeps_owner_edits():
    cfg = {
        "status_defs": {
            "job": [
                {
                    "code": "in_arbeit",
                    "label": "Werkstatt läuft",
                    "role": "active",
                    "stage": "in_progress",
                }
            ]
        }
    }
    cfg, changed = status_presets.merge(cfg, "werkstatt")
    assert changed
    defs = {d["code"]: d for d in cfg["status_defs"]["job"]}
    assert defs["in_arbeit"]["label"] == "Werkstatt läuft"
    assert {"teile_bestellt", "abholbereit"} <= set(defs)
    again, changed_again = status_presets.merge(cfg, "werkstatt")
    assert not changed_again and again == cfg


def test_preset_default_only_without_own_job_statuses():
    own = {
        "status_defs": {
            "job": [{"code": "x", "label": "X", "role": "active", "stage": "in_progress"}]
        }
    }
    cfg, changed = status_presets.with_default(own, "werkstatt")
    assert not changed and [d["code"] for d in cfg["status_defs"]["job"]] == ["x"]
    cfg, changed = status_presets.with_default({}, "werkstatt")
    assert changed
    assert status_presets.merge({}, "friseur") == ({}, False)


def test_kit_matches_preset():
    from apps.tenants.demo_kits import WERKSTATT

    cfg, _changed = status_presets.merge({}, "werkstatt")
    kit_codes = [d["code"] for d in WERKSTATT.status_defs["job"]]
    assert kit_codes == [d["code"] for d in cfg["status_defs"]["job"]]
    kit_edges = {(e["src"], e["dst"]) for e in WERKSTATT.status_edges["job"]}
    assert kit_edges == {(e["src"], e["dst"]) for e in cfg["status_edges"]["job"]}


def test_load_preset_button_merges(monkeypatch):
    from apps.core import views as core_views

    request = RequestFactory().post("/x/", {"load_preset": "1", "next": "/dashboard/ablaeufe/"})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = get_user_model().objects.create_user(
        username=f"o-{uuid.uuid4().hex[:8]}", password="pw1234567"
    )
    tenant = _tenant()
    monkeypatch.setattr(type(tenant), "save", lambda self, **kw: None)
    request.tenant = tenant
    response = core_views.status_manager_save(request, kind="job")
    assert response.status_code == 302 and response.url == "/dashboard/ablaeufe/"
    codes = [d["code"] for d in tenant.site_config["status_defs"]["job"]]
    assert codes == ["in_arbeit", "teile_bestellt", "abholbereit"]


# --- письмо «Abholbereit» ---------------------------------------------------


def _walk_to_ready(job):
    from django.db import connection

    from apps.jobs.state_machine import JobSM

    cfg, _c = status_presets.merge({}, "werkstatt")
    tenant = _tenant(site_config=cfg)
    connection.tenant = tenant
    sm = JobSM()
    for dst in ("quoted", "accepted", "in_arbeit", "abholbereit"):
        sm.apply(job, dst)
    return sm


def test_ready_email_once_and_no_done_email_after(monkeypatch):
    from django.db import connection

    old = getattr(connection, "tenant", None)
    try:
        job = _job()
        sm = _walk_to_ready(job)
        email = job.customer.email
        assert Notification.objects.filter(type="job_ready", recipient=email).count() == 1
        sm.apply(job, "done")
        assert not Notification.objects.filter(type="job_done", recipient=email).exists()
    finally:
        connection.tenant = old


# --- PDF ----------------------------------------------------------------------


def test_intake_pdf_title_for_vehicle():
    from apps.jobs import pdf

    job = _job()
    Vehicle.objects.filter(pk=job.vehicle_ref_id).update(vin="WVWZZZ1JZXW000001")
    job.refresh_from_db()
    proto = JobProtocol.objects.create(job=job, kind="intake", date=TODAY, mileage_km=1234)
    calls = []
    real = pdf._

    def spy(msg):
        calls.append(msg)
        return real(msg)

    pdf._ = spy
    try:
        data = pdf.build_protocol_pdf(job, proto, _tenant(name="KFZ Dreyer"))
    finally:
        pdf._ = real
    assert data.startswith(b"%PDF")
    assert "Fahrzeugannahme" in calls and "Annahmeprotokoll" not in calls
    assert "FIN" in calls


# --- правки по ревью ----------------------------------------------------------


def test_uncovered_when_service_reminder_not_sent_yet():
    """A9-заявка с той же датой, но без отправленного напоминания (нет почты у её
    клиента и т.п.) машину НЕ гасит — HU-письмо уходит."""
    job = _job()
    due = TODAY + datetime.timedelta(days=10)
    _hu(job, due)
    other = _job(plate="", email="")
    Job.objects.filter(pk=other.pk).update(vehicle_ref=job.vehicle_ref_id, service_due_date=due)
    assert tasks.send_due_hu_reminders(today=TODAY, tenant=_tenant()) == 1


def test_bad_vehicle_does_not_stop_others(monkeypatch):
    first, second = _job("A-A 1"), _job("B-B 2")
    for j in (first, second):
        _hu(j, TODAY + datetime.timedelta(days=5))
    from apps.promotions import notifications as promo_notifications

    real = promo_notifications._render

    def flaky(name, ctx, locale=None):
        if ctx.get("vehicle") and ctx["vehicle"].plate == "A-A 1":
            raise RuntimeError("template broken")
        return real(name, ctx, locale)

    monkeypatch.setattr(promo_notifications, "_render", flaky)
    assert tasks.send_due_hu_reminders(today=TODAY, tenant=_tenant()) == 1
    assert _hu_mails(second) == 1
    assert Vehicle.objects.get(pk=first.vehicle_ref_id).hu_reminder_sent_for is None


def test_done_mail_kept_when_ready_mail_did_not_go_out():
    from django.db import connection

    old = getattr(connection, "tenant", None)
    try:
        job = _job(email="")  # нет почты → «Abholbereit» не ушло
        sm = _walk_to_ready(job)
        job.customer.email = f"{uuid.uuid4().hex[:6]}@example.com"
        job.customer.save(update_fields=["email"])
        sm.apply(job, "done")
        assert Notification.objects.filter(type="job_done", recipient=job.customer.email).exists()
    finally:
        connection.tenant = old
