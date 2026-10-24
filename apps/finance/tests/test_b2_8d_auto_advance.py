"""KA-12 B2-8d (8d-2): подтверждённая сделка фирмы с депозитом — Anzahlungsrechnung сама
и письмом с PDF (за флагом). «Kauf auf Rechnung», частное лицо, без депозита — нет."""

from datetime import date, timedelta

import pytest

from apps.finance.models import Invoice
from apps.notifications.models import Notification
from apps.stays.models import StayUnit
from apps.stays.services import book_stay
from apps.stays.state_machine import StayBookingSM

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _flag(settings, monkeypatch):
    from apps.finance import auto_invoice
    from apps.tenants.tests.factories import TenantFactory

    settings.ROOT_URLCONF = "config.urls_tenant"
    settings.ADVANCE_INVOICES_ENABLED = True
    tenant = TenantFactory(schema_name="public")
    monkeypatch.setattr(auto_invoice, "_real_tenant", lambda schema: tenant)


def _stay(customer_type="company", method="vorkasse", deposit=5000):
    unit = StayUnit.objects.create(name="Z", quantity=1, price_cents=10000, max_guests=2)
    arrival = date(2030, 6, 3)
    booking = book_stay(
        unit,
        arrival=arrival,
        departure=arrival + timedelta(days=2),
        name="Anna Gast",
        email="einkauf@example.com",
        auto_confirm=False,
        payment_method=method,
        customer_type=customer_type,
        billing_company="Muster GmbH",
    )
    type(booking).objects.filter(pk=booking.pk).update(deposit_cents=deposit)
    booking.refresh_from_db()
    return booking


def _confirm(capture, booking):
    with capture(execute=True):
        StayBookingSM().apply(booking, "confirmed")


def _advances(booking):
    return Invoice.objects.filter(kind="advance", deal_kind="stay", deal_id=booking.reference_code)


def test_company_deposit_gets_mailed_advance(django_capture_on_commit_callbacks):
    booking = _stay()
    _confirm(django_capture_on_commit_callbacks, booking)
    adv = _advances(booking).get()
    assert adv.status == "issued"
    note = Notification.objects.get(type="advance_invoice_issued")
    assert note.recipient == "einkauf@example.com"
    assert (note.payload.get("attachments") or [{}])[0].get("mime") == "application/pdf"
    adv.refresh_from_db()
    assert adv.sent_at is not None


def test_repeat_confirmation_gives_one_document_and_one_mail(django_capture_on_commit_callbacks):
    from apps.finance.auto_invoice import advance_on_confirmed

    booking = _stay()
    _confirm(django_capture_on_commit_callbacks, booking)
    with django_capture_on_commit_callbacks(execute=True):
        advance_on_confirmed("stay", booking)
    assert _advances(booking).count() == 1
    assert Notification.objects.filter(type="advance_invoice_issued").count() == 1


@pytest.mark.parametrize(
    "kw",
    [
        {"customer_type": "private"},
        {"deposit": 0},
        {"method": "invoice"},
    ],
)
def test_no_advance_when_not_applicable(django_capture_on_commit_callbacks, kw):
    booking = _stay(**kw)
    _confirm(django_capture_on_commit_callbacks, booking)
    assert not _advances(booking).exists()


def test_flag_off_means_no_advance(django_capture_on_commit_callbacks, settings):
    settings.ADVANCE_INVOICES_ENABLED = False
    booking = _stay()
    _confirm(django_capture_on_commit_callbacks, booking)
    assert not _advances(booking).exists()


def test_failure_does_not_undo_confirmation(django_capture_on_commit_callbacks, monkeypatch):
    from apps.finance import advance

    def boom(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(advance, "create_advance_invoice", boom)
    booking = _stay()
    _confirm(django_capture_on_commit_callbacks, booking)
    booking.refresh_from_db()
    assert booking.status == "confirmed"


def test_job_of_company_gets_advance_on_accept(django_capture_on_commit_callbacks):
    from apps.jobs import services as job_services
    from apps.jobs.state_machine import JobSM

    job = job_services.create_job(title="Bad", name="Kunde", email="firma@example.com")
    job.status, job.deposit_cents, job.customer_type = "quoted", 5000, "company"
    job.save()
    with django_capture_on_commit_callbacks(execute=True):
        JobSM().apply(job, "accepted")
    assert Invoice.objects.filter(kind="advance", deal_kind="job").count() == 1


# --- 8d-3: письмо о сторно отправленной Anzahlungsrechnung ---------------------------


def _storno_mails():
    return Notification.objects.filter(type="advance_invoice_cancelled")


def test_sent_advance_storno_on_deal_cancel_mails_customer(django_capture_on_commit_callbacks):
    booking = _stay()
    _confirm(django_capture_on_commit_callbacks, booking)
    with django_capture_on_commit_callbacks(execute=True):
        StayBookingSM().apply(booking, "cancelled")
    assert _advances(booking).get().status == "cancelled"
    note = _storno_mails().get()
    assert note.recipient == "einkauf@example.com"
    assert (note.payload.get("attachments") or [{}])[0].get("mime") == "application/pdf"


def test_unsent_advance_storno_sends_nothing(django_capture_on_commit_callbacks):
    from apps.finance import advance

    booking = _stay()
    with django_capture_on_commit_callbacks(execute=True):
        advance.create_advance_invoice("stay", booking, None)
        StayBookingSM().apply(booking, "cancelled")
    assert not _storno_mails().exists()


def test_repeat_cancel_gives_one_storno_mail(django_capture_on_commit_callbacks):
    from apps.finance import advance

    booking = _stay()
    _confirm(django_capture_on_commit_callbacks, booking)
    with django_capture_on_commit_callbacks(execute=True):
        StayBookingSM().apply(booking, "cancelled")
        advance.cancel_unpaid_for_deal("stay", booking)
    assert _storno_mails().count() == 1
