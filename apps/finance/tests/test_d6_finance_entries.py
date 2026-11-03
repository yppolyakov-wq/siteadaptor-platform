"""UX-D D6.5: Finanzen — «＋ Buchung»/«＋ Ausgabe» шторками, «＋ Neue Rechnung» страницей.

Раньше формы висели раскрытыми под списками, а ошибка ввода (редирект с сообщением)
стирала введённое — у счёта до 8 строк."""

import json
import re
import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.core.models import Membership
from apps.finance import entry_views as ev
from apps.finance import views
from apps.finance.models import ExpenseEntry, Invoice, RevenueEntry
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _req(path, method="get", data=None, drawer=False):
    extra = {"HTTP_X_SF_DRAWER": "1"} if drawer else {}
    req = getattr(RequestFactory(), method)(path, data or {}, **extra)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    tag = uuid.uuid4().hex[:8]
    req.user = get_user_model().objects.create_user(username=f"u-{tag}", password="pw12345678")
    Membership.objects.get_or_create(user=req.user, defaults={"role": Membership.ROLE_OWNER})
    req.tenant = TenantFactory.build(disabled_modules=[])
    return req


# --- списки без раскрытых форм ------------------------------------------------------


@pytest.mark.parametrize(
    "view, path, button",
    [
        (views.journal, "/dashboard/finance/", "/dashboard/finance/buchung/neu/"),
        (views.expenses, "/dashboard/finance/ausgaben/", "/dashboard/finance/ausgaben/neu/"),
    ],
)
def test_lists_have_no_inline_create_form_but_a_drawer_button(view, path, button):
    html = view(_req(path)).content.decode()
    assert 'name="amount"' not in html
    assert re.search(rf'<a href="{button}" data-drawer', html)
    assert "data-drawer-refresh" in html


def test_invoice_list_has_no_inline_form_but_a_page_button():
    html = views.invoices(_req("/dashboard/finance/rechnungen/")).content.decode()
    assert 'name="line_text_1"' not in html
    assert 'href="/dashboard/finance/rechnungen/neu/"' in html


# --- «＋ Buchung» -------------------------------------------------------------------


def test_journal_new_fragment_and_create():
    resp = ev.journal_new(_req("/dashboard/finance/buchung/neu/", drawer=True))
    html = resp.content.decode()
    assert resp["X-Sf-Fragment"] == "1" and "<script" not in html
    resp = ev.journal_new(
        _req(
            "/dashboard/finance/buchung/neu/",
            "post",
            {
                "amount": "1.234,50",
                "vat_rate": "7.00",
                "date": "2026-10-01",
                "next": "/dashboard/finance/",
            },
            drawer=True,
        )
    )
    entry = RevenueEntry.objects.get()
    assert json.loads(resp.content)["ok"] is True
    assert (entry.amount, entry.vat_rate) == (Decimal("1234.50"), Decimal("7.00"))


@pytest.mark.parametrize(
    "data, field",
    [
        ({"amount": "NaN"}, "amount"),
        ({"amount": "0"}, "amount"),
        ({"amount": "10", "date": "31.02.2026"}, "date"),
        ({"amount": "10", "vat_rate": "33"}, "vat"),
    ],
)
def test_journal_new_errors_keep_input(data, field):
    resp = ev.journal_new(
        _req("/dashboard/finance/buchung/neu/", "post", {"note": "Kasse", **data}, drawer=True)
    )
    html = resp.content.decode()
    assert resp.status_code == 200 and f'id="jn-{field}-err"' in html
    assert 'value="Kasse"' in html and not RevenueEntry.objects.exists()


# --- «＋ Ausgabe» -------------------------------------------------------------------


def test_expense_new_creates_with_due_date_open():
    ev.expense_new(
        _req(
            "/dashboard/finance/ausgaben/neu/",
            "post",
            {"amount": "99,90", "vat_rate": "19.00", "due_date": "2026-12-01", "note": "Miete"},
        )
    )
    e = ExpenseEntry.objects.get()
    assert e.amount == Decimal("99.90") and e.paid_at is None and str(e.due_date) == "2026-12-01"


@pytest.mark.parametrize(
    "data, field",
    [
        ({"amount": "abc"}, "amount"),
        ({"amount": "10", "due_date": "bald"}, "due"),
        ({"amount": "10", "supplier": str(uuid.uuid4())}, "supplier"),
    ],
)
def test_expense_new_errors_keep_input(data, field):
    resp = ev.expense_new(
        _req("/dashboard/finance/ausgaben/neu/", "post", {"note": "Miete", **data}, drawer=True)
    )
    html = resp.content.decode()
    assert f'id="en-{field}-err"' in html and 'value="Miete"' in html
    assert not ExpenseEntry.objects.exists()


# --- «＋ Neue Rechnung» -------------------------------------------------------------


def test_invoice_new_page_has_eight_lines():
    html = ev.invoice_new(_req("/dashboard/finance/rechnungen/neu/")).content.decode()
    assert 'name="line_text_8"' in html and 'name="line_text_9"' not in html


def test_invoice_new_creates_draft_with_negative_discount_line():
    resp = ev.invoice_new(
        _req(
            "/dashboard/finance/rechnungen/neu/",
            "post",
            {
                "line_text_1": "Catering",
                "line_qty_1": "2",
                "line_price_1": "1.000,00",
                "line_text_2": "Rabatt",
                "line_qty_2": "1",
                "line_price_2": "-50",
                "vat_rate": "19.00",
            },
        )
    )
    inv = Invoice.objects.get()
    assert resp.status_code == 302 and [ln["unit_price"] for ln in inv.lines] == ["1000.00", "-50"]


def test_invoice_new_error_keeps_all_lines_and_marks_the_field():
    resp = ev.invoice_new(
        _req(
            "/dashboard/finance/rechnungen/neu/",
            "post",
            {
                "line_text_1": "Catering",
                "line_price_1": "120",
                "line_text_2": "Getränke",
                "line_price_2": "1,234",
                "recipient": "Firma Muster",
            },
        )
    )
    html = resp.content.decode()
    assert resp.status_code == 200 and not Invoice.objects.exists()
    assert 'value="Catering"' in html and 'value="Getränke"' in html and "Firma Muster" in html
    assert 'id="inv-l2-err"' in html


def test_invoice_new_garbage_qty_is_an_error():
    resp = ev.invoice_new(
        _req(
            "/dashboard/finance/rechnungen/neu/",
            "post",
            {"line_text_1": "A", "line_qty_1": "²", "line_price_1": "5"},
        )
    )
    assert 'id="inv-l1-err"' in resp.content.decode() and not Invoice.objects.exists()


def test_drawers_and_permissions():
    from apps.core import drawer, view_perms

    code = drawer.drawer_aware(lambda r: r).__code__
    for view in (ev.journal_new, ev.expense_new):
        chain = [view]
        while hasattr(chain[-1], "__wrapped__"):
            chain.append(chain[-1].__wrapped__)
        assert chain[-2].__code__ is code
    r = view_perms.RULES
    assert r["finance:journal-new"] == r["finance:journal"]
    assert r["finance:expense-new"] == r["finance:expenses"]
    assert r["finance:invoice-new"] == r["finance:invoices"]


@pytest.mark.parametrize("lang", ["de", "en", "ru"])
def test_vat_options_round_trip_in_cabinet_language(lang):
    """Ревью D6.5 (HIGH): option value локализовался («19,00»), строгий белый список
    отклонял каждую запись в de/ru/tr/uk. Значение, которое шлёт браузер, — принимается."""
    from django.utils import translation

    with translation.override(lang):
        html = ev.journal_new(_req("/dashboard/finance/buchung/neu/", drawer=True)).content.decode()
        values = re.findall(r'<option value="([^"]+)"', html.split('name="vat_rate"', 1)[1])
        assert values
        for value in values:
            ev.journal_new(
                _req("/dashboard/finance/buchung/neu/", "post", {"amount": "10", "vat_rate": value})
            )
    assert RevenueEntry.objects.count() == len(values)
    assert {str(e.vat_rate) for e in RevenueEntry.objects.all()} == {
        str(r) for r in RevenueEntry.VAT_RATES
    }


def test_vat_comma_is_accepted():
    ev.journal_new(
        _req("/dashboard/finance/buchung/neu/", "post", {"amount": "10", "vat_rate": "7,00"})
    )
    assert RevenueEntry.objects.get().vat_rate == Decimal("7.00")
