"""KA-12 B2-8b: Anzahlungsrechnung — счёт на предоплату (§ 14 Abs. 5 UStG).

Свой номер на сумму Anzahlung по ставкам сделки. Не выручка и не счёт сделки;
оплата синхронизируется с депозитом сделки в обе стороны."""

import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core import money_contract
from apps.core.fsm import IllegalTransition
from apps.finance import advance, bank
from apps.finance.models import Invoice, InvoiceDeduction, RevenueEntry
from apps.finance.state_machine import InvoiceSM
from apps.jobs import services as job_services
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

TENANT = SimpleNamespace(small_business=False, invoice_terms_days=14)


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    settings.ADVANCE_INVOICES_ENABLED = True


def _stay(deposit=5000):
    from apps.stays import services
    from apps.stays.models import StayUnit

    unit = StayUnit.objects.create(name=f"Zimmer {uuid.uuid4().hex[:6]}", price_cents=8000)
    arrival = timezone.localdate() + timedelta(days=10)
    s = services.book_stay(unit, arrival=arrival, departure=arrival + timedelta(days=2), name="G")
    s.deposit_cents = deposit
    s.save(update_fields=["deposit_cents"])
    return s


def _job(deposit=5000, **kw):
    job = job_services.create_job(title="Bad", name="Kunde")
    job.status = "accepted"
    job.deposit_cents = deposit
    for key, value in kw.items():
        setattr(job, key, value)
    job.save()
    return job


def test_advance_matches_deposit_and_has_own_number():
    stay = _stay()
    inv = advance.create_advance_invoice("stay", stay, TENANT)
    assert inv.kind == Invoice.KIND_ADVANCE and inv.number and inv.status == "issued"
    assert inv.gross == Decimal("50.00")
    assert inv.deal_kind == "stay" and inv.deal_id == stay.reference_code
    stay.refresh_from_db()
    assert stay.invoice_id is None  # не занимает счёт сделки


def test_repeat_click_returns_same_document():
    stay = _stay()
    first = advance.create_advance_invoice("stay", stay, TENANT)
    again = advance.create_advance_invoice("stay", stay, TENANT)
    assert again.pk == first.pk
    assert Invoice.objects.filter(kind="advance").count() == 1


def test_db_rejects_second_live_advance():
    stay = _stay()
    advance.create_advance_invoice("stay", stay, TENANT)
    with pytest.raises(IntegrityError), transaction.atomic():
        Invoice.objects.create(kind="advance", deal_kind="stay", deal_id=stay.reference_code)


def test_refused_without_deposit_and_after_final_invoice():
    with pytest.raises(advance.AdvanceError):
        advance.create_advance_invoice("stay", _stay(deposit=0), TENANT)
    stay = _stay()
    Invoice.objects.create(
        deal_kind="stay", deal_id=stay.reference_code, status="issued", number=999
    )
    with pytest.raises(advance.AdvanceError):
        advance.create_advance_invoice("stay", stay, TENANT)


def test_advance_is_not_the_deal_invoice():
    stay = _stay()
    advance.create_advance_invoice("stay", stay, TENANT)
    assert money_contract.invoice_for("stay", stay) is None


def test_job_advance_posts_no_revenue_even_after_storno():
    job = _job()
    inv = advance.create_advance_invoice("job", job, TENANT)
    assert RevenueEntry.objects.count() == 0
    InvoiceSM().apply(inv, "cancelled")
    assert RevenueEntry.objects.count() == 0
    job.refresh_from_db()
    assert job.invoice_id is None


def test_received_deposit_issues_paid():
    stay = _stay()
    stay.payment_state = "deposit"
    stay.save(update_fields=["payment_state"])
    inv = advance.create_advance_invoice("stay", stay, TENANT)
    assert inv.status == "paid"


def test_paying_the_advance_marks_only_the_deposit():
    stay = _stay()
    inv = advance.create_advance_invoice("stay", stay, TENANT)
    InvoiceSM().apply(inv, "paid", source="bank")
    stay.refresh_from_db()
    assert stay.payment_state == "deposit"
    from apps.core.models import DealPayment

    rows = list(DealPayment.objects.filter(deal_kind="stay", deal_id=stay.pk))
    assert sum(r.amount_cents for r in rows) == 5000


def test_job_deposit_settle_marks_advance_paid():
    job = _job()
    inv = advance.create_advance_invoice("job", job, TENANT)
    money_contract.settle_payment("job", job, source="bank", deposit_only=True)
    inv.refresh_from_db()
    assert inv.status == "paid"
    job.refresh_from_db()
    assert job.deposit_cents == 5000  # депозит сохранён (счёт потом вычтет ровно его)


def test_stripe_deposit_webhook_marks_advance_paid():
    from django.db import connection

    from apps.stays.payments import mark_stay_paid

    stay = _stay()
    inv = advance.create_advance_invoice("stay", stay, TENANT)
    mark_stay_paid(tenant_schema=connection.schema_name, booking_id=str(stay.id))
    inv.refresh_from_db()
    assert inv.status == "paid"


def test_open_items_show_advance_instead_of_deal_row():
    tenant = TenantFactory(schema_name="public")
    job = _job()
    inv = advance.create_advance_invoice("job", job, tenant)
    items = bank.open_items(tenant)
    assert not [i for i in items if i["kind"] == "job" and i["obj"].pk == job.pk]
    rows = [i for i in items if i["kind"] == "invoice" and i["obj"].pk == inv.pk]
    assert len(rows) == 1 and rows[0]["amount"] == Decimal("50.00")


def test_storno_refused_once_deducted():
    stay = _stay()
    inv = advance.create_advance_invoice("stay", stay, TENANT)
    final = Invoice.objects.create(
        deal_kind="stay", deal_id=stay.reference_code, status="issued", number=998
    )
    InvoiceDeduction.objects.create(
        final=final, advance=inv, vat_rate=Decimal("7"), net=1, vat=0, gross=1
    )
    with pytest.raises(IllegalTransition):
        InvoiceSM().apply(inv, "cancelled")


def test_job_deposit_locked_while_advance_lives(rf):
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware

    from apps.jobs.views import job_detail

    job = _job()
    advance.create_advance_invoice("job", job, TENANT)
    request = rf.post("/x/", {"action": "deposit", "deposit_eur": "10"})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    from django.contrib.auth import get_user_model

    request.user = get_user_model().objects.create_user(username="o-adv", password="pw123456")
    request.tenant = TenantFactory(schema_name="public")
    job_detail(request, pk=job.pk)
    job.refresh_from_db()
    assert job.deposit_cents == 5000


def test_pdf_title():
    from apps.finance.pdf import build_invoice_pdf

    inv = advance.create_advance_invoice("stay", _stay(), TENANT)
    pdf = build_invoice_pdf(inv, TenantFactory(schema_name="public"))
    assert pdf[:4] == b"%PDF"


def test_view_flag_and_role(client, settings):
    from django.http import Http404
    from django.test import RequestFactory

    from apps.core.views import deal_advance_invoice

    stay = _stay()
    request = RequestFactory().post("/x/")
    from django.contrib.auth import get_user_model

    request.user = get_user_model().objects.create_user(username="s-adv", password="pw123456")
    request.tenant = SimpleNamespace(is_module_active=lambda m: True, small_business=False)
    settings.ADVANCE_INVOICES_ENABLED = False
    with pytest.raises(Http404):
        deal_advance_invoice(request, kind="stay", pk=stay.pk)


def test_full_manual_payment_of_job_closes_advance():
    """Кнопка «bezahlt» обнуляет deposit_cents (KA-H10) — предоплата всё равно оплачена."""
    job = _job()
    inv = advance.create_advance_invoice("job", job, TENANT)
    money_contract.settle_payment("job", job, source="manual")
    inv.refresh_from_db()
    assert inv.status == "paid"


def test_paid_advance_with_zeroed_deposit_never_marks_deal_paid():
    stay = _stay()
    inv = advance.create_advance_invoice("stay", stay, TENANT)
    type(stay).objects.filter(pk=stay.pk).update(deposit_cents=0)
    InvoiceSM().apply(inv, "paid")
    stay.refresh_from_db()
    assert stay.payment_state not in ("paid", "deposit")


def test_sync_failure_does_not_break_payment(monkeypatch):
    stay = _stay()
    advance.create_advance_invoice("stay", stay, TENANT)

    def boom(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(advance, "_sync_advance_paid", boom)
    stay.payment_state = "deposit"
    stay.save(update_fields=["payment_state"])
    advance.sync_advance_paid("stay", stay)  # не бросает
