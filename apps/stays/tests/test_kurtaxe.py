"""H5 (adults/children) + H9 (Kurtaxe) — разбивка гостей и курортный сбор."""

import uuid
from datetime import date, timedelta

import pytest

from apps.stays import pricing, services
from apps.stays.models import StaySettings, StayUnit

pytestmark = pytest.mark.django_db

D0 = date(2026, 9, 1)


def _unit(**kwargs):
    kwargs.setdefault("price_cents", 10000)
    kwargs.setdefault("max_guests", 4)
    return StayUnit.objects.create(name=f"Zimmer {uuid.uuid4().hex[:6]}", **kwargs)


def _book(unit, nights=2, **kwargs):
    kwargs.setdefault("name", "Gast")
    return services.book_stay(unit, arrival=D0, departure=D0 + timedelta(days=nights), **kwargs)


# --- H5: adults / children --------------------------------------------------------


def test_adults_children_split_sets_guests_total():
    unit = _unit(max_guests=4)
    b = _book(unit, adults=2, children=2)
    assert b.adults == 2 and b.children == 2 and b.guests == 4


def test_capacity_uses_total_guests():
    unit = _unit(max_guests=3)
    with pytest.raises(services.MaxGuests):
        _book(unit, adults=2, children=2)  # 4 > 3


def test_legacy_guests_contract_still_works():
    unit = _unit()
    b = _book(unit, guests=3)  # без adults → adults=3, children=0
    assert b.adults == 3 and b.children == 0 and b.guests == 3


# --- H9: Kurtaxe ------------------------------------------------------------------


def test_kurtaxe_total_helper():
    s = StaySettings(kurtaxe_cents=250)
    assert pricing.kurtaxe_total_cents(2, 3, settings=s) == 1500  # 2 × 3 × 2,50 €
    assert pricing.kurtaxe_total_cents(2, 3, settings=StaySettings(kurtaxe_cents=0)) == 0


def test_booking_includes_kurtaxe_for_adults_only():
    StaySettings.objects.create(kurtaxe_cents=250)  # 2,50 €/Erw./Nacht
    unit = _unit(price_cents=10000, max_guests=4)
    b = _book(unit, nights=2, adults=2, children=1)
    # проживание 2×100 = 200 €; Kurtaxe 2 взр. × 2 ночи × 2,50 = 10 € (дети бесплатно)
    assert b.kurtaxe_cents == 1000
    assert b.total_cents == 21000


def test_move_recomputes_kurtaxe_by_nights():
    StaySettings.objects.create(kurtaxe_cents=250)
    unit = _unit(price_cents=10000, max_guests=4)
    b = _book(unit, nights=2, adults=2)
    services.move_stay(b, arrival=D0, departure=D0 + timedelta(days=4))
    b.refresh_from_db()
    assert b.kurtaxe_cents == 2000  # 2 × 4 × 2,50
    assert b.total_cents == 42000  # 4×100 + 20


def test_invoice_separates_kurtaxe_line_without_vat():
    StaySettings.objects.create(kurtaxe_cents=250)
    unit = _unit(price_cents=10000, max_guests=4)
    b = _book(unit, nights=2, adults=2)  # total 220 €, Kurtaxe 10 €
    inv = services.stay_to_invoice(b)
    # отдельная строка Kurtaxe; gross = итог брони; НДС только на проживание (210 €)
    assert any("Kurtaxe" in line["text"] for line in inv.lines)
    assert inv.gross == b.total_eur
    # 7 % только на 210 € Beherbergung → нетто ~196.26, НДС ~13.74
    assert inv.vat_amount < 14
