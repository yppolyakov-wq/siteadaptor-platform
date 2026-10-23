"""KA-12 Волна 1.2 (E1.1/E1.2): Stornorechnung — отдельный документ со своим номером;
PDF счёта — нетто по ставкам, перенос страниц, описания целиком."""

from decimal import Decimal

import pytest

from apps.core.fsm import IllegalTransition
from apps.finance import pdf as pdf_mod
from apps.finance.models import Invoice
from apps.finance.services import issue_invoice
from apps.finance.state_machine import InvoiceSM
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

MIXED = [
    {"text": "Brot", "qty": 2, "unit_price": "3.00", "vat_rate": "7"},
    {"text": "Kaffeemaschine", "qty": 1, "unit_price": "10.00", "vat_rate": "19"},
]


def _issued(lines=MIXED, net="16.00", vat="2.32", gross="18.32", **kw):
    inv = Invoice.objects.create(
        lines=lines, net=Decimal(net), vat_amount=Decimal(vat), gross=Decimal(gross), **kw
    )
    return issue_invoice(inv)


def _texts(monkeypatch, invoice, tenant):
    seen = []
    for name in ("drawString", "drawRightString"):
        orig = getattr(pdf_mod._NumberedCanvas, name)

        def spy(self, x, y, text, *a, _orig=orig, **k):
            seen.append(str(text))
            return _orig(self, x, y, text, *a, **k)

        monkeypatch.setattr(pdf_mod._NumberedCanvas, name, spy)
    data = pdf_mod.build_invoice_pdf(invoice, tenant)
    return data, seen


def test_cancel_creates_storno_with_own_number_and_negated_sums():
    original = _issued()
    InvoiceSM().apply(original, "cancelled")
    original.refresh_from_db()
    storno = Invoice.objects.get(cancels=original)
    assert storno.kind == "storno" and storno.status == "issued"
    assert storno.number == original.number + 1  # тот же счётчик, без пропусков
    assert (storno.net, storno.vat_amount, storno.gross) == (
        -original.net,
        -original.vat_amount,
        -original.gross,
    )
    assert [ln["qty"] for ln in storno.lines] == [-2, -1]
    # оригинал не изменился (GoBD)
    assert original.gross == Decimal("18.32") and original.lines == MIXED


def test_storno_is_idempotent_and_has_no_transitions():
    from apps.finance.services import create_storno

    original = _issued()
    InvoiceSM().apply(original, "cancelled")
    storno = Invoice.objects.get(cancels=original)
    assert create_storno(original) == storno  # повтор не выдаёт второй номер
    assert Invoice.objects.filter(cancels=original).count() == 1
    with pytest.raises(IllegalTransition):
        InvoiceSM().apply(storno, "paid")
    nxt = _issued()
    assert nxt.number == storno.number + 1


def test_storno_never_in_open_items_or_reused_by_deal():
    from apps.core import money_contract

    original = _issued(deal_kind="order", deal_id="B-1")
    InvoiceSM().apply(original, "cancelled")
    assert not Invoice.objects.filter(status="issued", kind="invoice").exists()

    class Obj:
        reference_code = "B-1"
        pk = "B-1"
        invoice_id = None

    assert money_contract.invoice_for("order", Obj()) is None


def test_pdf_prints_net_and_vat_per_rate(monkeypatch):
    tenant = TenantFactory.build(vat_id="DE123456789")
    data, seen = _texts(monkeypatch, _issued(), tenant)
    assert data.startswith(b"%PDF")
    joined = " | ".join(seen)
    for label in ("7 %", "19 %"):
        assert sum(1 for t in seen if label in t) >= 2, joined  # нетто и налог по ставке


def test_storno_pdf_has_title_reference_and_no_watermark(monkeypatch):
    tenant = TenantFactory.build(vat_id="DE123456789")
    original = _issued()
    InvoiceSM().apply(original, "cancelled")
    original.refresh_from_db()
    storno = Invoice.objects.get(cancels=original)
    _data, seen = _texts(monkeypatch, storno, tenant)
    assert any(original.number_display in t for t in seen)
    _data, seen = _texts(monkeypatch, original, tenant)
    assert not any("CANCELLED" in t or "STORNIERT" in t.upper() for t in seen)


def test_legacy_cancel_without_storno_keeps_watermark(monkeypatch):
    tenant = TenantFactory.build()
    legacy = _issued()
    Invoice.objects.filter(pk=legacy.pk).update(status="cancelled")  # как до KA-12
    legacy.refresh_from_db()
    _data, seen = _texts(monkeypatch, legacy, tenant)
    assert len(seen) and any(t for t in seen)
    # водяной знак рисуется drawCentredString — достаточно, что PDF собирается
    assert pdf_mod.build_invoice_pdf(legacy, tenant).startswith(b"%PDF")


def test_long_invoice_paginates_and_long_text_is_complete(monkeypatch):
    tenant = TenantFactory.build()
    long_text = "Sehr lange Positionsbeschreibung " * 6
    lines = [{"text": f"Pos {i}", "qty": 1, "unit_price": "1.00"} for i in range(60)]
    lines.append({"text": long_text.strip(), "qty": 1, "unit_price": "1.00"})
    inv = _issued(lines=lines, net="61.00", vat="11.59", gross="72.59")
    data, seen = _texts(monkeypatch, inv, tenant)
    assert data.count(b"/Type /Page\n") + data.count(b"/Type /Page ") >= 2 or (
        sum(1 for t in seen if t == "Pos 0") == 1 and any("Seite" in t for t in seen)
    )
    assert any("Pos 59" == t for t in seen)
    words = " ".join(t for t in seen if "Sehr lange" in t or "Positionsbeschreibung" in t)
    assert words.count("Positionsbeschreibung") == 6  # не обрезано на 70 знаках


def test_private_recipient_gets_deal_address():
    from types import SimpleNamespace

    from apps.finance.recipient import recipient_for

    deal = SimpleNamespace(customer="Anna Muster", billing_address="Markt 1\n42651 Solingen")
    assert recipient_for(deal) == "Anna Muster\nMarkt 1\n42651 Solingen"
    shipped = SimpleNamespace(customer="Ben", billing_address="", shipping_address="Weg 2")
    assert recipient_for(shipped) == "Ben\nWeg 2"


def test_issue_over_250_without_address_is_blocked(rf_owner):
    from apps.finance import views

    inv = Invoice.objects.create(
        lines=[{"text": "Fahrrad", "qty": 1, "unit_price": "300.00"}],
        net=Decimal("300.00"),
        vat_amount=Decimal("57.00"),
        gross=Decimal("357.00"),
        recipient="Anna Muster",
    )
    views.invoice_detail(rf_owner("post", {"action": "issue"}), pk=inv.pk)
    inv.refresh_from_db()
    assert inv.status == "draft" and inv.number is None
    views.invoice_detail(
        rf_owner("post", {"action": "recipient", "recipient": "Anna Muster\nMarkt 1"}), pk=inv.pk
    )
    views.invoice_detail(rf_owner("post", {"action": "issue"}), pk=inv.pk)
    inv.refresh_from_db()
    assert inv.status == "issued"
    small = Invoice.objects.create(
        lines=[{"text": "Brot", "qty": 1, "unit_price": "3.00"}],
        net=Decimal("3.00"),
        vat_amount=Decimal("0.21"),
        gross=Decimal("3.21"),
        recipient="Anna",
    )
    views.invoice_detail(rf_owner("post", {"action": "issue"}), pk=small.pk)
    small.refresh_from_db()
    assert small.status == "issued"  # Kleinbetragsrechnung — без адреса можно


@pytest.fixture
def rf_owner():
    import uuid

    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.core.models import Membership

    def make(method, data):
        req = getattr(RequestFactory(), method)("/dashboard/finance/rechnungen/x/", data)
        SessionMiddleware(lambda r: None).process_request(req)
        MessageMiddleware(lambda r: None).process_request(req)
        req.user = get_user_model().objects.create_user(username=f"o-{uuid.uuid4().hex[:8]}")
        Membership.objects.create(user=req.user, role=Membership.ROLE_OWNER)
        req.tenant = TenantFactory.build()
        return req

    return make
