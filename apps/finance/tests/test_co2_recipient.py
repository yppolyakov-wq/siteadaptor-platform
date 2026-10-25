"""CO-2a: получатель счёта — фирма со сделки, а не имя гостя (§ 14 UStG).

План — docs/co2-v2-company-billing-plan-2026-10-21.md. Один выбор получателя на все
построители счёта: заказ, бронь номера, запись, старый счёт брони из кабинета.
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.finance.recipient import recipient_for


def _deal(**kw):
    base = {
        "customer": "Anna Gast",
        "customer_type": "",
        "billing_company": "",
        "billing_vat_id": "",
    }
    base.update(kw)
    return SimpleNamespace(**base)


class _Company:
    name = "Müller Maschinenbau GmbH"
    street = "Werkstraße 1"
    postal_code = "40721"
    city = "Hilden"
    vat_id = "DE111111111"

    @property
    def invoice_recipient(self):
        return (
            f"{self.name}\n{self.street}\n{self.postal_code} {self.city}\nUSt-IdNr: {self.vat_id}"
        )


class _Customer:
    def __init__(self, company=None):
        self.company = company

    def __str__(self):
        return "Anna Gast"


def test_private_deal_keeps_customer_name():
    assert recipient_for(_deal(customer=_Customer())) == "Anna Gast"


def test_company_deal_uses_company_and_vat_from_deal():
    deal = _deal(
        customer=_Customer(),
        customer_type="company",
        billing_company="Muster GmbH",
        billing_vat_id="DE123456789",
    )
    assert recipient_for(deal) == "Muster GmbH\nUSt-IdNr: DE123456789"


def test_company_deal_takes_address_from_directory_and_deal_vat_wins():
    deal = _deal(
        customer=_Customer(_Company()),
        customer_type="company",
        billing_company="Müller Maschinenbau GmbH",
        billing_vat_id="DE999999999",
    )
    assert recipient_for(deal) == (
        "Müller Maschinenbau GmbH\nWerkstraße 1\n40721 Hilden\nUSt-IdNr: DE999999999"
    )


def test_linked_company_without_deal_fields():
    deal = _deal(customer=_Customer(_Company()))
    assert recipient_for(deal).startswith("Müller Maschinenbau GmbH\nWerkstraße 1")


def test_explicit_payer_of_order_stays_first():
    deal = _deal(
        customer=_Customer(_Company()),
        billing_name="Einkauf Muster",
        billing_address="Postfach 1\n10115 Berlin",
        customer_type="company",
        billing_company="Muster GmbH",
        billing_vat_id="DE123456789",
    )
    assert recipient_for(deal) == "Einkauf Muster\nPostfach 1\n10115 Berlin\nUSt-IdNr: DE123456789"


def test_company_type_without_name_falls_back():
    assert recipient_for(_deal(customer=_Customer(), customer_type="company")) == "Anna Gast"


@pytest.mark.django_db
def test_order_invoice_for_company_buyer_carries_vat_id():
    from apps.catalog.models import Product
    from apps.finance.services import invoice_from_order
    from apps.orders import services as order_services

    product = Product.objects.create(
        name={"de": "Saft"}, base_price=Decimal("10.00"), stock_quantity=10
    )
    order = order_services.create_order(
        items=[(product, 1)],
        name="Anna Gast",
        email="firma@example.com",
        customer_type="company",
        billing_company="Muster GmbH",
        billing_vat_id="DE123456789",
        payment_method="invoice",
    )
    invoice = invoice_from_order(order)
    assert invoice.recipient.startswith("Muster GmbH")
    assert "USt-IdNr: DE123456789" in invoice.recipient


def test_builders_use_the_shared_recipient():
    """Замок класса: ни один построитель не собирает получателя сам."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    finance = (root / "finance" / "services.py").read_text()
    stays = (root / "stays" / "services.py").read_text()
    assert "recipient=str(booking.customer)" not in finance
    assert "recipient=str(booking.customer)" not in stays
    # KA-12 Z-1: у броней номера свой построитель счёта удалён (DF-Z2) — счета
    # строит только finance (один источник получателя).
    assert finance.count("recipient_for(") >= 3
    assert "Invoice.objects.create" not in stays
