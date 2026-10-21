"""CO-2c: покупатель-фирма привязывается к справочнику только по точному USt-IdNr
(решение владельца В-3: без автосоздания компаний)."""

from decimal import Decimal

import pytest

from apps.crm.companies import link_by_vat, normalize_vat
from apps.crm.models import Company

pytestmark = pytest.mark.django_db


def _order(vat, customer_type="company", email="einkauf@mueller.example"):
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
    c = Company.objects.create(
        name="Müller GmbH", vat_id="DE 123 456 789", email="info@mueller.example"
    )
    order = _order("de123456789")
    order.customer.refresh_from_db()
    assert order.customer.company_id == c.pk


def test_no_match_creates_nothing():
    _order("DE000000000")
    assert Company.objects.count() == 0


def test_existing_link_is_not_overwritten():
    a = Company.objects.create(name="A", vat_id="DE111", email="x@mueller.example")
    Company.objects.create(name="B", vat_id="DE222", email="x@mueller.example")
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


def test_public_vat_without_company_mail_domain_links_nothing():
    """Ревью безопасности: чужой публичный USt-IdNr не даёт посетителю адрес фирмы."""
    Company.objects.create(name="Müller GmbH", vat_id="DE123456789", email="info@mueller.example")
    order = _order("DE123456789", email="fremd@gmail.example")
    order.customer.refresh_from_db()
    assert order.customer.company_id is None


def test_clean_vat_id_format():
    from apps.core.payment_methods import clean_vat_id

    assert clean_vat_id(" de 123.456.789 ") == "DE123456789"
    assert clean_vat_id("Bitte zahlen Sie an IBAN …") == ""


def test_freemail_domain_is_no_proof():
    Company.objects.create(name="Klein GmbH", vat_id="DE444444444", email="klein@gmail.com")
    order = _order("DE444444444", email="irgendwer@gmail.com")
    order.customer.refresh_from_db()
    assert order.customer.company_id is None


def test_swiss_uid_is_kept():
    from apps.core.payment_methods import clean_vat_id

    assert clean_vat_id("CHE-123.456.789 MWST") == "CHE123456789MWST"
