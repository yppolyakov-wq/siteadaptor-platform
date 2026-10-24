"""KA-12 E2.9: список счетов — чипы статуса/вида, «überfällig», поиск, период,
сортировка по белому списку; счётчики чипов совпадают со строками."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.finance import invoice_list, views
from apps.finance.models import Invoice
from apps.finance.tests.test_invoices import _req

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _inv(**kw):
    kw.setdefault("lines", [{"text": "Brot", "qty": 1, "unit_price": "1.00"}])
    kw.setdefault("gross", Decimal("10.00"))
    return Invoice.objects.create(**kw)


def _pks(qs):
    return {i.pk for i in qs}


def test_status_chip_filters():
    paid = _inv(status=Invoice.STATUS_PAID, number=1)
    _inv(status=Invoice.STATUS_DRAFT)
    qs, state = invoice_list.filtered(Invoice.objects.all(), {"status": "paid"})
    assert _pks(qs) == {paid.pk}
    assert state["status"] == "paid"


def test_overdue_chip_only_issued_past_due():
    late = _inv(status=Invoice.STATUS_ISSUED, number=1, due_date=date.today() - timedelta(days=1))
    _inv(status=Invoice.STATUS_ISSUED, number=2, due_date=date.today() + timedelta(days=3))
    _inv(status=Invoice.STATUS_PAID, number=3, due_date=date.today() - timedelta(days=9))
    qs, _state = invoice_list.filtered(Invoice.objects.all(), {"status": "ueberfaellig"})
    assert _pks(qs) == {late.pk}


def test_kind_chip_filters():
    credit = _inv(kind=Invoice.KIND_ADVANCE, number=1)
    _inv(number=2)
    qs, _state = invoice_list.filtered(Invoice.objects.all(), {"art": "advance"})
    assert _pks(qs) == {credit.pk}


def test_unknown_chips_are_ignored():
    a = _inv(number=1)
    qs, state = invoice_list.filtered(
        Invoice.objects.all(), {"status": "<x>", "art": "drop", "sort": "__x"}
    )
    assert a.pk in _pks(qs)
    assert state["status"] == "" and state["art"] == "" and state["sort"] == ""


def test_search_by_number_and_recipient_not_email():
    from apps.promotions.models import Customer

    cust = Customer.objects.create(name="Erika Muster", email="geheim@kunde.de")
    by_number = _inv(number=4711)
    by_recipient = _inv(number=1, recipient="Bäckerei Krume GmbH")
    by_customer = _inv(number=2, customer=cust)
    assert _pks(invoice_list.filtered(Invoice.objects.all(), {"q": "4711"})[0]) == {by_number.pk}
    assert _pks(
        invoice_list.filtered(Invoice.objects.all(), {"q": "krume"}, full_search=True)[0]
    ) == {by_recipient.pk}
    assert _pks(invoice_list.filtered(Invoice.objects.all(), {"q": "Erika"})[0]) == {by_customer.pk}
    # KA-H11: поиск по e-mail даёт сотруднику способ угадывать адреса.
    assert _pks(invoice_list.filtered(Invoice.objects.all(), {"q": "geheim@"})[0]) == set()


def test_period_filter_and_junk_dates():
    old = _inv(number=1)
    Invoice.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=40))
    fresh = _inv(number=2)
    since = (date.today() - timedelta(days=5)).isoformat()
    assert _pks(invoice_list.filtered(Invoice.objects.all(), {"von": since})[0]) == {fresh.pk}
    qs, state = invoice_list.filtered(Invoice.objects.all(), {"von": "kaputt", "bis": "31.13."})
    assert _pks(qs) == {old.pk, fresh.pk}
    assert state["von"] == "" and state["bis"] == ""


def test_sort_by_amount_and_number():
    small = _inv(number=2, gross=Decimal("5.00"))
    big = _inv(number=1, gross=Decimal("90.00"))
    assert list(invoice_list.filtered(Invoice.objects.all(), {"sort": "summe"})[0])[:2] == [
        big,
        small,
    ]
    assert list(invoice_list.filtered(Invoice.objects.all(), {"sort": "nummer"})[0])[:2] == [
        small,
        big,
    ]


def test_chip_counts_match_rows():
    _inv(status=Invoice.STATUS_PAID, number=1)
    _inv(status=Invoice.STATUS_PAID, number=2)
    _inv(status=Invoice.STATUS_ISSUED, number=3, due_date=date.today() - timedelta(days=2))
    _inv(status=Invoice.STATUS_DRAFT)
    counts = invoice_list.status_counts(Invoice.objects.all(), {})
    assert counts["paid"] == 2 and counts["issued"] == 1 and counts["draft"] == 1
    assert counts["ueberfaellig"] == 1
    assert counts[""] == 4


def test_view_renders_chips_and_filters():
    _inv(status=Invoice.STATUS_PAID, number=1, recipient="Erste Firma")
    _inv(status=Invoice.STATUS_DRAFT, recipient="Zweite Firma")
    resp = views.invoices(_req(data={"status": "paid"}))
    html = resp.content.decode()
    assert resp.status_code == 200
    assert "Erste Firma" in html and "Zweite Firma" not in html
    assert "data-invoice-chip" in html


def test_view_junk_params_do_not_crash():
    resp = views.invoices(_req(data={"von": "x", "sort": "';--", "seite": "abc", "art": "?"}))
    assert resp.status_code == 200


def test_staff_cannot_probe_emails_through_recipient():
    """Security-ревью: у клиента без имени получатель счёта = его e-mail
    (Customer.__str__). Поиск по получателю сотруднику давал бы подбор адресов."""
    _inv(number=1, recipient="ivan.geheim@gmail.com")
    staff_qs, _state = invoice_list.filtered(Invoice.objects.all(), {"q": "ivan.geheim"})
    assert not staff_qs.exists()
    assert invoice_list.status_counts(Invoice.objects.all(), {"q": "ivan.geheim"})[""] == 0
    owner_qs, _state = invoice_list.filtered(
        Invoice.objects.all(), {"q": "ivan.geheim"}, full_search=True
    )
    assert owner_qs.exists()
