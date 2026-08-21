"""ERP-2: Offene Posten + импорт банковской выписки + сопоставление.

План docs/erp-wave-plan-2026-08-21.md §ERP-2.
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.catalog.tests.factories import ProductFactory
from apps.finance import bank
from apps.finance.models import BankTransaction
from apps.orders import services as order_services
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


SPARKASSE = (
    "Buchungstag;Betrag;Verwendungszweck;Beguenstigter/Zahlungspflichtiger\n"
    "21.08.2026;27,50;Bestellung O-ABC123 Danke;Max Mustermann\n"
    "20.08.2026;1.234,56;Miete August;Vermieter GmbH\n"
).encode("cp1252")


def test_parse_german_csv_semicolon_cp1252():
    rows = bank.parse_csv(SPARKASSE)
    assert len(rows) == 2
    assert rows[0]["amount"] == Decimal("27.50")
    assert rows[1]["amount"] == Decimal("1234.56")
    assert "O-ABC123" in rows[0]["purpose"]


def test_parse_unknown_columns_raises():
    with pytest.raises(bank.BankImportError):
        bank.parse_csv(b"foo,bar\n1,2\n")


def test_import_rows_dedupes_on_reimport():
    rows = bank.parse_csv(SPARKASSE)
    assert bank.import_rows(rows) == 2
    assert bank.import_rows(rows) == 0  # повторный импорт того же файла
    assert BankTransaction.objects.count() == 2


def _order(total_eur="27.50", code_suffix=None):
    p = ProductFactory(base_price=Decimal(total_eur), name={"de": "Ware"})
    order = order_services.create_order(items=[(p, 1)], name="Max", email="m@t.de")
    return order


def test_open_items_lists_unpaid_order_and_match_by_code_sets_paid():
    tenant = TenantFactory(schema_name="public")
    order = _order()
    items = bank.open_items(tenant)
    assert any(i["kind"] == "order" and i["obj"].pk == order.pk for i in items)

    tx = BankTransaction.objects.create(
        date="2026-08-21",
        amount=order.total,
        purpose=f"Bestellung {order.reference_code} Danke",
        import_hash="x" * 32,
    )
    sugs = bank.suggestions(tx, items)
    assert sugs and sugs[0]["strong"] and sugs[0]["item"]["obj"].pk == order.pk

    bank.apply_match(tx, "order", order)
    order.refresh_from_db()
    tx.refresh_from_db()
    assert order.payment_state == "paid"
    assert tx.matched_kind == "order" and str(order.pk) == tx.matched_id
    # оплаченный заказ ушёл из открытых
    assert not any(
        i["kind"] == "order" and i["obj"].pk == order.pk for i in bank.open_items(tenant)
    )


def test_bank_view_import_and_match_endpoint():
    tenant = TenantFactory(schema_name="public")
    order = _order()
    from apps.finance import views as finance_views

    def _req(method, data=None):
        request = getattr(RequestFactory(), method)("/dashboard/finance/bank/", data or {})
        SessionMiddleware(lambda r: None).process_request(request)
        MessageMiddleware(lambda r: None).process_request(request)
        request.user = get_user_model().objects.create_user(
            username=f"o{method}{BankTransaction.objects.count()}",
            email="o@t.de",
            password="pw12345678",
        )
        request.tenant = tenant
        return request

    from django.core.files.uploadedfile import SimpleUploadedFile

    csv_bytes = (
        "Buchungstag;Betrag;Verwendungszweck\n"
        f"21.08.2026;{str(order.total).replace('.', ',')};Zahlung {order.reference_code}\n"
    ).encode("cp1252")
    request = _req("post", {"action": "import"})
    request.FILES["file"] = SimpleUploadedFile("auszug.csv", csv_bytes, content_type="text/csv")
    finance_views.bank_import(request)
    tx = BankTransaction.objects.get()

    request = _req(
        "post", {"action": "match", "tx": str(tx.pk), "kind": "order", "obj": str(order.pk)}
    )
    finance_views.bank_import(request)
    order.refresh_from_db()
    assert order.payment_state == "paid"
