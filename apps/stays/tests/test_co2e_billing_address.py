"""CO-2e (решение владельца В-2): адрес фирмы для счёта (§ 14 UStG) — вводится на
витрине и правится на карточке; счёт берёт его раньше справочника компаний."""

from datetime import date, timedelta
from pathlib import Path

import pytest

from apps.finance.recipient import recipient_for
from apps.stays.models import StayUnit
from apps.stays.services import book_stay

pytestmark = pytest.mark.django_db
ROOT = Path(__file__).resolve().parents[3]


def test_stay_keeps_billing_address_and_invoice_uses_it():
    unit = StayUnit.objects.create(name="Z", quantity=1, price_cents=10000, max_guests=2)
    arrival = date(2030, 6, 3)
    booking = book_stay(
        unit,
        arrival=arrival,
        departure=arrival + timedelta(days=2),
        name="Anna Gast",
        email="a@example.com",
        customer_type="company",
        billing_company="Muster GmbH",
        billing_vat_id="DE123456789",
        billing_address="Werkstraße 1\n40721 Hilden",
    )
    booking.refresh_from_db()
    assert booking.billing_address == "Werkstraße 1\n40721 Hilden"
    assert recipient_for(booking) == (
        "Muster GmbH\nWerkstraße 1\n40721 Hilden\nUSt-IdNr: DE123456789"
    )


def test_booking_model_has_billing_address():
    from apps.booking.models import Booking

    assert Booking._meta.get_field("billing_address")


def test_storefront_forms_ask_for_the_address():
    for name in ("_billing_party.html", "_buybox_contact_fields.html"):
        assert 'name="billing_address"' in (ROOT / "templates" / "storefront" / name).read_text()
    card = (ROOT / "templates" / "core" / "_deal_billing_card.html").read_text()
    assert 'name="billing_address"' in card
