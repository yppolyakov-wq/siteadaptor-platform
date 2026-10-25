"""KA-12 E11.1 (A-0): серверный золотой путь направления «Anfragen/Handwerk».

/anfrage/ → заявка → смета (две ставки) → /angebot/ принять → done → счёт → выручка
ровно одна и равна счёту; ветка с Anzahlung — к оплате остаётся счёт − депозит.
Браузерный двойник — GP-6 в `scripts/golden_paths.py`."""

import uuid
from decimal import Decimal

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection
from django.test import RequestFactory
from django.utils import timezone

from apps.finance.models import RevenueEntry
from apps.finance.services import issue_invoice
from apps.jobs import payments, public_views, services
from apps.jobs.models import Job
from apps.jobs.state_machine import JobSM
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

LINES = [
    {"text": "Arbeitszeit", "qty": 2, "unit_price": "50.00", "vat_rate": "19"},
    {"text": "Material", "qty": 1, "unit_price": "100.00", "vat_rate": "7"},
]


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(method="get", path="/anfrage/", data=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    request.META["REMOTE_ADDR"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.6"
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = TenantFactory.build(disabled_modules=[])
    return request


def _request_job():
    tag = uuid.uuid4().hex[:6]
    resp = public_views.anfrage(
        _req(
            "post",
            data={
                "title": f"GP {tag} Bad sanieren",
                "name": "Frau Kunde",
                "email": f"{tag}@t.de",
                "site_plz": "42651",
            },
        )
    )
    assert resp.status_code == 302
    return Job.objects.get(title__startswith=f"GP {tag}")


def _quote(job):
    services.set_lines(job, LINES)
    job.refresh_from_db()
    return JobSM().apply(job, "quoted")


def _accept(job):
    path = f"/angebot/{job.public_token}/"
    public_views.angebot(_req("post", path=path, data={"action": "accept"}), token=job.public_token)
    job.refresh_from_db()
    return job


def _entries(invoice):
    return RevenueEntry.objects.filter(source="job", source_ref__startswith=f"inv:{invoice.pk}:")


def test_request_quote_accept_done_invoice_one_revenue():
    job = _request_job()
    assert job.status == "new" and job.site_plz == "42651"
    job = _quote(job)
    body = public_views.angebot(_req(), token=job.public_token).content.decode()
    assert "Arbeitszeit" in body and "Material" in body
    job = _accept(job)
    assert job.status == "accepted" and job.accepted_at is not None
    JobSM().apply(job, "done")
    invoice = services.quote_to_invoice(job)
    assert "Frau Kunde" in invoice.recipient
    issue_invoice(invoice)
    invoice.refresh_from_db()
    # § 14 Abs. 4 Nr. 6 UStG: ohne Termin/Eventdatum — Ausstellungstag (KA-H10).
    assert invoice.service_date == timezone.localdate()
    assert sum(e.amount for e in _entries(invoice)) == invoice.gross
    assert {e.vat_rate for e in _entries(invoice)} == {Decimal("7.00"), Decimal("19.00")}


def test_deposit_branch_leaves_invoice_minus_deposit_open():
    job = _quote(_request_job())
    job.deposit_cents = 5000
    job.save(update_fields=["deposit_cents", "updated_at"])
    assert payments.mark_deposit_paid(tenant_schema=connection.schema_name, job_id=str(job.id))
    job.refresh_from_db()
    assert job.status == "accepted"
    JobSM().apply(job, "done")
    invoice = services.quote_to_invoice(job)
    issue_invoice(invoice)
    invoice.refresh_from_db()
    assert invoice.prepaid_cents == 5000
    assert invoice.open_amount == invoice.gross - Decimal("50.00")
