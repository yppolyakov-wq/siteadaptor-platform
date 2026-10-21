"""CO-2c: покупатель-фирма привязывается к справочнику только по точному USt-IdNr
(решение владельца В-3: без автосоздания компаний)."""

from decimal import Decimal

import pytest

from apps.crm.companies import link_by_vat, normalize_vat
from apps.crm.models import Company

pytestmark = pytest.mark.django_db


def _order(vat, customer_type="company", email="einkauf@example.com"):
    from apps.catalog.models import Product
    from apps.orders import services

    product = Product.objects.create(
        name={"de": "Saft"}, base_price=Decimal("10.00"), stock_quantity=10
    )
    return services.create_order(
        items=[(product, 1)],
        name="Anna Gast",
        email=email,
        customer_type=customer_type,
        billing_company="Müller GmbH",
        billing_vat_id=vat,
        payment_method="invoice",
    )


def test_normalize_vat():
    assert normalize_vat(" de 123.456-789 ") == "DE123456789"


def test_company_buyer_linked_by_normalized_vat():
    c = Company.objects.create(name="Müller GmbH", vat_id="DE 123 456 789")
    order = _order("de123456789")
    order.customer.refresh_from_db()
    assert order.customer.company_id == c.pk


def test_no_match_creates_nothing():
    _order("DE000000000")
    assert Company.objects.count() == 0


def test_existing_link_is_not_overwritten():
    a = Company.objects.create(name="A", vat_id="DE111")
    Company.objects.create(name="B", vat_id="DE222")
    order = _order("DE111")
    customer = order.customer
    assert link_by_vat(customer, "DE222") is None
    customer.refresh_from_db()
    assert customer.company_id == a.pk


def test_private_buyer_is_never_linked():
    Company.objects.create(name="Müller GmbH", vat_id="DE123456789")
    order = _order("DE123456789", customer_type="private")
    order.customer.refresh_from_db()
    assert order.customer.company_id is None


def test_ambiguous_vat_links_nothing():
    Company.objects.create(name="A", vat_id="DE555")
    Company.objects.create(name="B", vat_id="de 555")
    order = _order("DE555")
    order.customer.refresh_from_db()
    assert order.customer.company_id is None
