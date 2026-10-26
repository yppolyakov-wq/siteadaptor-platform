"""KA-12 A-7 (E7.5): Widerrufsbelehrung на странице сметы, снимок при принятии,
подтверждение договора с PDF, функция отказа (§ 356a) — за флагом."""

import datetime
import uuid

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory
from django.utils import timezone

from apps.jobs import public_views, services, withdrawal
from apps.jobs.models import Job
from apps.notifications.models import Notification
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _setup(settings, monkeypatch):
    settings.ROOT_URLCONF = "config.urls_tenant"
    settings.QUOTE_WITHDRAWAL_ENABLED = True
    tenant = TenantFactory.build(
        disabled_modules=[], name="Fliesen Kern", owner_email="chef@example.com"
    )
    monkeypatch.setattr("apps.promotions.notifications._tenant", lambda schema: tenant)
    monkeypatch.setattr("apps.jobs.notifications._tenant", lambda schema: tenant)
    return tenant


def _req(method="get", data=None):
    request = getattr(RequestFactory(), method)("/angebot/x/", data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.9"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(disabled_modules=[], name="Fliesen Kern")
    return request


def _quoted(customer_type="private"):
    job = services.create_job(
        title="Bad fliesen", name="Anna Kern", email=f"{uuid.uuid4().hex[:6]}@example.com"
    )
    services.set_lines(job, [{"text": "Fliesen legen", "qty": 1, "unit_price": "500"}])
    Job.objects.filter(pk=job.pk).update(status=Job.STATUS_QUOTED, customer_type=customer_type)
    job.refresh_from_db()
    return job


def _accept(job, **extra):
    data = {"action": "accept", **extra}
    return public_views.angebot(_req("post", data), token=job.public_token)


def test_flag_off_shows_nothing(settings):
    settings.QUOTE_WITHDRAWAL_ENABLED = False
    job = _quoted()
    body = public_views.angebot(_req(), token=job.public_token).content.decode()
    assert "data-withdrawal-info" not in body and 'name="early_start"' not in body
    _accept(job)
    job.refresh_from_db()
    assert job.status == Job.STATUS_ACCEPTED and job.withdrawal_info_at is None


def test_business_customer_has_no_withdrawal():
    job = _quoted(customer_type="company")
    body = public_views.angebot(_req(), token=job.public_token).content.decode()
    assert "data-withdrawal-info" not in body


def test_accept_snapshots_text_once_and_sends_contract_with_pdf(_setup):
    job = _quoted()
    body = public_views.angebot(_req(), token=job.public_token).content.decode()
    assert "data-withdrawal-info" in body and "Widerrufsrecht" in body
    _accept(job, early_start="1")
    job.refresh_from_db()
    assert job.status == Job.STATUS_ACCEPTED
    assert len(job.withdrawal_text_hash) == 64  # sha256 показанного текста
    assert job.early_start_requested_at is not None
    first = job.withdrawal_info_at
    withdrawal.record_info(job, _setup, early_start=False)
    job.refresh_from_db()
    assert job.withdrawal_info_at == first and job.early_start_requested_at is not None
    mail = Notification.objects.get(type="job_contract", recipient=job.customer.email)
    assert "Widerrufsrecht" in mail.payload.get("body", "")
    assert mail.payload.get("attachments")


def test_early_start_unchecked_stays_empty():
    job = _quoted()
    _accept(job)
    job.refresh_from_db()
    assert job.withdrawal_info_at is not None and job.early_start_requested_at is None


def test_withdraw_within_window_cancels_once(django_capture_on_commit_callbacks):
    job = _quoted()
    _accept(job)
    job.refresh_from_db()
    body = public_views.angebot(_req(), token=job.public_token).content.decode()
    assert "data-withdraw-form" in body
    data = {"action": "withdraw", "confirm": "1"}
    with django_capture_on_commit_callbacks(execute=True):
        public_views.angebot(_req("post", data), token=job.public_token)
    job.refresh_from_db()
    assert job.status == Job.STATUS_CANCELLED and job.withdrawn_at is not None
    first = job.withdrawn_at
    public_views.angebot(_req("post", data), token=job.public_token)
    job.refresh_from_db()
    assert job.withdrawn_at == first
    assert (
        Notification.objects.filter(type="job_withdrawn", recipient=job.customer.email).count() == 1
    )


def test_withdraw_needs_confirmation():
    job = _quoted()
    _accept(job)
    public_views.angebot(_req("post", {"action": "withdraw"}), token=job.public_token)
    job.refresh_from_db()
    assert job.status == Job.STATUS_ACCEPTED and job.withdrawn_at is None


def test_withdraw_after_deadline_refused():
    job = _quoted()
    _accept(job)
    Job.objects.filter(pk=job.pk).update(
        accepted_at=timezone.now() - datetime.timedelta(days=withdrawal.WITHDRAWAL_DAYS + 1)
    )
    job.refresh_from_db()
    assert not withdrawal.can_withdraw(job)
    public_views.angebot(
        _req("post", {"action": "withdraw", "confirm": "1"}), token=job.public_token
    )
    job.refresh_from_db()
    assert job.status == Job.STATUS_ACCEPTED and job.withdrawn_at is None


def test_done_without_early_start_still_withdrawable_and_recorded(
    django_capture_on_commit_callbacks,
):
    """Отметка «erledigt» право не гасит; отмены из done в FSM нет — отказ фиксируется,
    владелец получает письмо и решает вручную."""
    job = _quoted()
    _accept(job)
    Job.objects.filter(pk=job.pk).update(status=Job.STATUS_DONE)
    job.refresh_from_db()
    assert withdrawal.can_withdraw(job)
    with django_capture_on_commit_callbacks(execute=True):
        assert withdrawal.withdraw(job, None)
    job.refresh_from_db()
    assert job.withdrawn_at is not None and job.status == Job.STATUS_DONE
    assert Notification.objects.filter(type="job_withdrawn_owner").exists()


def test_done_with_early_start_not_withdrawable():
    job = _quoted()
    _accept(job, early_start="1")
    Job.objects.filter(pk=job.pk).update(status=Job.STATUS_DONE)
    job.refresh_from_db()
    assert not withdrawal.can_withdraw(job)


def test_reclick_while_quoted_takes_last_choice():
    job = _quoted()
    withdrawal.record_info(job, TenantFactory.build(name="Kern"), early_start=True)
    assert job.early_start_requested_at is not None
    withdrawal.record_info(job, TenantFactory.build(name="Kern"), early_start=False)
    assert job.early_start_requested_at is None


def test_owner_manual_accept_drops_click_snapshot():
    from apps.jobs.state_machine import JobSM

    job = _quoted()
    withdrawal.record_info(
        job, TenantFactory.build(name="Kern"), early_start=True
    )  # клиент кликнул и бросил оплату
    JobSM().apply(job, Job.STATUS_ACCEPTED)  # владелец принял сам
    job.refresh_from_db()
    assert job.withdrawal_info_at is None and not withdrawal.can_withdraw(job)
    assert not Notification.objects.filter(
        type="job_contract", recipient=job.customer.email
    ).exists()


def test_redelivered_deposit_webhook_keeps_refunded_state():
    from django.db import connection

    from apps.jobs import payments

    job = _quoted()
    Job.objects.filter(pk=job.pk).update(
        status=Job.STATUS_CANCELLED, payment_state=Job.PAYMENT_REFUNDED
    )
    assert payments.mark_deposit_paid(
        tenant_schema=connection.schema_name, job_id=str(job.id), payment_intent="pi_x"
    )
    job.refresh_from_db()
    assert job.payment_state == Job.PAYMENT_REFUNDED and job.status == Job.STATUS_CANCELLED


def test_quote_accepted_without_belehrung_cannot_be_withdrawn_online():
    job = _quoted()
    Job.objects.filter(pk=job.pk).update(status=Job.STATUS_ACCEPTED, accepted_at=timezone.now())
    job.refresh_from_db()
    assert not withdrawal.can_withdraw(job)


def test_unknown_token_404():
    with pytest.raises(Http404):
        public_views.angebot(_req("post", {"action": "withdraw"}), token=uuid.uuid4())
