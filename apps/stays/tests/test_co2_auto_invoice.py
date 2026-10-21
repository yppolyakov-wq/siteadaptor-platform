"""CO-2d: «Kauf auf Rechnung» у брони номера и записи — счёт выпускается сам при
подтверждении (решение владельца В-1: автоподтверждение = сразу; иначе — когда отель
подтвердит; отклонённый запрос счёта не оставляет). План —
docs/co2-v2-company-billing-plan-2026-10-21.md.
"""

from datetime import date, timedelta
from pathlib import Path

import pytest

from apps.finance.models import Invoice
from apps.stays.models import StayUnit
from apps.stays.services import book_stay
from apps.stays.state_machine import StayBookingSM

pytestmark = pytest.mark.django_db


def _book(auto_confirm, method="invoice", customer_type="company"):
    unit = StayUnit.objects.create(name="Z", quantity=1, price_cents=10000, max_guests=2)
    arrival = date(2030, 6, 3)
    return book_stay(
        unit,
        arrival=arrival,
        departure=arrival + timedelta(days=2),
        name="Anna Gast",
        email="einkauf@example.com",
        auto_confirm=auto_confirm,
        payment_method=method,
        customer_type=customer_type,
        billing_company="Muster GmbH",
        billing_vat_id="DE123456789",
    )


def test_auto_confirmed_company_stay_gets_one_issued_invoice(django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        booking = _book(auto_confirm=True)
    inv = Invoice.objects.get(deal_kind="stay", deal_id=booking.reference_code)
    assert inv.status == "issued" and inv.recipient.startswith("Muster GmbH")
    assert "USt-IdNr: DE123456789" in inv.recipient


def test_pending_request_gets_invoice_only_when_confirmed(django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        booking = _book(auto_confirm=False)
    assert not Invoice.objects.filter(deal_kind="stay").exists()
    with django_capture_on_commit_callbacks(execute=True):
        StayBookingSM().apply(booking, "confirmed")
    assert Invoice.objects.filter(deal_kind="stay", deal_id=booking.reference_code).count() == 1


def test_declined_request_leaves_no_invoice(django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        booking = _book(auto_confirm=False)
        StayBookingSM().apply(booking, "cancelled")
    assert not Invoice.objects.filter(deal_kind="stay").exists()


def test_other_payment_methods_get_no_invoice(django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        _book(auto_confirm=True, method="on_site", customer_type="private")
    assert not Invoice.objects.exists()


def test_invoice_and_vorkasse_never_go_to_stripe():
    """Фирма выбрала «Rechnung» при тарифе с предоплатой — без перехода в Stripe."""
    root = Path(__file__).resolve().parents[2]
    for path in (root / "stays" / "public_views.py", root / "booking" / "public_views.py"):
        assert "offline_payment(" in path.read_text(), path


def test_card_draft_is_issued_not_duplicated(django_capture_on_commit_callbacks):
    """Ревью: черновик кнопкой на карточке + подтверждение = один счёт, а не два."""
    from apps.finance.services import invoice_from_stay

    with django_capture_on_commit_callbacks(execute=True):
        booking = _book(auto_confirm=False)
    draft = invoice_from_stay(booking)
    booking.invoice_id = draft.pk
    booking.save(update_fields=["invoice_id"])
    with django_capture_on_commit_callbacks(execute=True):
        StayBookingSM().apply(booking, "confirmed")
    # Черновик мог устареть — выпускается свежий, но счёт на сделку ровно один.
    assert Invoice.objects.count() == 1
    inv = Invoice.objects.get()
    assert inv.status == "issued" and inv.deal_kind == "stay"
    booking.refresh_from_db()
    assert booking.invoice_id == inv.pk


def test_invoice_mail_is_throttled_per_address():
    import uuid

    from apps.finance.services import _invoice_mail_allowed

    addr = f"spam-{uuid.uuid4().hex[:8]}@example.com"  # Redis общий между прогонами
    assert [_invoice_mail_allowed(addr) for _ in range(4)] == [True, True, True, False]
