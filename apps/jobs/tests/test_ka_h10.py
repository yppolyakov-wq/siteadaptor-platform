"""KA-H10 (аудит KA-5f): смета, счёт и сроки у ремесла/заявок.

H1 смета заперта после принятия · H2 получатель счёта = фирма сделки, Leistungsdatum ·
H3 «уже получено» → открытая сумма · H4 просроченную смету не принять ·
L5 в генерируемой Datenschutz нет ложного «nicht an Dritte weitergegeben»."""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.utils import timezone

from apps.core import deal_discount
from apps.finance import bank
from apps.finance.services import issue_invoice
from apps.jobs import public_views, services, views
from apps.jobs.models import Job
from apps.jobs.state_machine import JobSM
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

LINES = [{"text": "Fliesen legen", "qty": 1, "unit_price": "100.00"}]


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="post", data=None, tenant=None):
    request = getattr(RequestFactory(), method)("/dashboard/auftraege/", data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    o = uuid.uuid4().hex[:8]
    request.user = get_user_model().objects.create_user(f"h-{o}", f"h-{o}@t.de", "pw12345678")
    request.tenant = tenant if tenant is not None else TenantFactory.build(disabled_modules=[])
    return request


def _job(status="quoted", lines=LINES, **kw):
    job = services.create_job(title="Bad", name="Kunde", email=f"{uuid.uuid4().hex[:6]}@t.de")
    services.set_lines(job, lines)
    job.refresh_from_db()
    for key, value in kw.items():
        setattr(job, key, value)
    if kw:
        job.save()
    path = {
        "quoted": ["quoted"],
        "accepted": ["quoted", "accepted"],
        "done": ["quoted", "accepted", "done"],
    }
    for dst in path.get(status, []):
        JobSM().apply(job, dst)
    job.refresh_from_db()
    return job


def _post_lines(job, **extra):
    data = {"action": "save_lines", "line_text_1": "Neu", "line_price_1": "999", **extra}
    request = _req(data=data)
    views.job_detail(request, pk=job.pk)
    return request


# --- H1 -----------------------------------------------------------------------------------


def test_save_lines_ignored_after_accept():
    job = _job("accepted")
    gross = job.gross
    request = _post_lines(job)
    job.refresh_from_db()
    assert job.gross == gross and job.lines.first().text == "Fliesen legen"
    assert any("gesperrt" in str(m) for m in get_messages(request))


def test_locked_save_still_updates_vehicle_and_service_due():
    job = _job("done")
    due = timezone.localdate() + timedelta(days=200)
    _post_lines(job, vehicle="AB-CD 12", service_due_date=due.isoformat())
    job.refresh_from_db()
    assert job.vehicle == "AB-CD 12" and job.service_due_date == due
    assert job.lines.first().text == "Fliesen legen"


def test_save_lines_open_in_quoted():
    job = _job("quoted")
    _post_lines(job)
    job.refresh_from_db()
    assert job.lines.first().text == "Neu"


def test_deposit_unchanged_when_paid():
    job = _job("quoted", deposit_cents=2000, payment_state="paid")
    views.job_detail(_req(data={"action": "deposit", "deposit_eur": "50"}), pk=job.pk)
    job.refresh_from_db()
    assert job.deposit_cents == 2000


def test_deal_discount_rejected_for_accepted_job():
    job = _job("accepted")
    assert deal_discount.supports("job", job) is False
    assert deal_discount.supports("job", _job("quoted")) is True


def test_detail_renders_lines_readonly_when_locked():
    job = _job("accepted")
    body = views.job_detail(_req("get"), pk=job.pk).content.decode()
    assert "data-lines-locked" in body and "disabled" in body


# --- H2 -----------------------------------------------------------------------------------


def test_invoice_recipient_uses_company():
    job = _job(
        "done",
        customer_type="company",
        billing_company="Muster GmbH",
        billing_vat_id="DE123",
        site_address="Baustelle 1",
    )
    invoice = services.quote_to_invoice(job)
    assert invoice.recipient.startswith("Muster GmbH")
    assert "DE123" in invoice.recipient


def test_invoice_recipient_private_appends_site_address():
    job = _job("done", site_address="Baustelle 1")
    invoice = services.quote_to_invoice(job)
    assert invoice.recipient.endswith("Baustelle 1")


def test_invoice_service_date_from_event_date():
    day = timezone.localdate() - timedelta(days=3)
    job = _job("done", event_date=day)
    assert services.quote_to_invoice(job).service_date == day


def test_issue_sets_service_date_to_issue_day_when_missing():
    invoice = services.quote_to_invoice(_job("done"))
    assert invoice.service_date is None
    issue_invoice(invoice)
    invoice.refresh_from_db()
    assert invoice.service_date == timezone.localdate()


# --- H3 -----------------------------------------------------------------------------------


def test_prepaid_cents_deposit_counts():
    job = _job("done", deposit_cents=3000, payment_state="paid")
    invoice = services.quote_to_invoice(job)
    assert invoice.prepaid_cents == 3000
    assert invoice.open_amount == Decimal(invoice.gross) - Decimal("30.00")


def test_prepaid_full_when_marked_paid_without_deposit():
    job = _job("done", payment_state="paid")
    assert services.quote_to_invoice(job).open_amount == 0


def test_open_items_use_open_amount_and_skip_settled():
    tenant = TenantFactory.build(disabled_modules=[])
    partly = services.quote_to_invoice(_job("done", deposit_cents=3000, payment_state="paid"))
    issue_invoice(partly)
    settled = services.quote_to_invoice(_job("done", payment_state="paid"))
    issue_invoice(settled)
    rows = {r["obj"].pk: r for r in bank.open_items(tenant) if r["kind"] == "invoice"}
    assert rows[partly.pk]["amount"] == partly.open_amount
    assert settled.pk not in rows


# --- H4 -----------------------------------------------------------------------------------


def _public(job, data=None, method="post"):
    rf = RequestFactory()
    path = f"/angebot/{job.public_token}/"
    request = rf.post(path, data or {}) if method == "post" else rf.get(path)
    from importlib import import_module

    from django.conf import settings

    request.session = import_module(settings.SESSION_ENGINE).SessionStore()
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(disabled_modules=[])
    request.META["REMOTE_ADDR"] = f"10.10.{uuid.uuid4().int % 250}.1"
    return public_views.angebot(request, token=job.public_token)


def test_angebot_accept_rejected_when_expired():
    job = _job("quoted", valid_until=timezone.localdate() - timedelta(days=1))
    _public(job, {"action": "accept"})
    job.refresh_from_db()
    assert job.status == Job.STATUS_QUOTED


def test_angebot_accept_allowed_on_last_day():
    job = _job("quoted", valid_until=timezone.localdate())
    _public(job, {"action": "accept"})
    job.refresh_from_db()
    assert job.status == Job.STATUS_ACCEPTED


# --- L5 -----------------------------------------------------------------------------------


def test_privacy_text_no_false_third_party_claim():
    tenant = TenantFactory.build(privacy_policy="")
    text = tenant.privacy_text()
    assert "nicht an Dritte" not in text
    assert "Dienstleister" in text
    own = TenantFactory.build(privacy_policy="Eigener Text")
    assert own.privacy_text() == "Eigener Text"
