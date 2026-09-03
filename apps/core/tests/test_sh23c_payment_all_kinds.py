"""SH-23c: способ оплаты и тип покупателя ЕСТЬ У ВСЕХ видов сделок.

До волны способ знал только заказ: у брони номера «100 % предоплаты» означало
«только картой» (решение владельца Р-5 требует и банковский перевод), у записи и
заявки способа не было вовсе. Здесь — снимок на четырёх доменных моделях, разбор
POST одним хелпером и срок удержания места (Р-4).

План — `docs/order-feedback-plan-2026-09-03.md` §6.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core import payment_methods as pm
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _tenant(**kw):
    kw.setdefault("disabled_modules", [])
    kw.setdefault("vorkasse_enabled", True)
    kw.setdefault("bank_iban", "DE89370400440532013000")
    return TenantFactory(**kw)


def test_every_deal_model_carries_the_payment_snapshot():
    """Один набор полей у всех видов — иначе «Zahlungen» и счёт врут по частям."""
    from apps.booking.models import Booking
    from apps.events.models import Ticket
    from apps.jobs.models import Job
    from apps.orders.models import Order
    from apps.stays.models import StayBooking

    for model in (Order, Booking, StayBooking, Ticket, Job):
        names = {f.name for f in model._meta.get_fields()}
        missing = {
            "payment_method",
            "customer_type",
            "billing_company",
            "billing_vat_id",
            "payment_due_at",
        } - names
        assert not missing, (model.__name__, missing)


def test_service_booking_keeps_the_chosen_method_and_due_date():
    from apps.booking.models import Resource, Service
    from apps.booking.services import book

    _tenant(schema_name="sh23m", slug="sh23m", vorkasse_hold_days=4)
    resource = Resource.objects.create(name="Stuhl 1")
    service = Service.objects.create(name="Haarschnitt", duration_minutes=30, price_cents=3900)
    start = timezone.now() + timedelta(days=1)
    booking = book(
        resource,
        start=start,
        end=start + timedelta(minutes=30),
        name="Kunde",
        service=service,
        payment_method=pm.VORKASSE,
        customer_type=pm.COMPANY,
        billing_company="Muster GmbH",
        payment_due_at=timezone.now() + timedelta(days=4),
    )
    assert booking.payment_method == pm.VORKASSE
    assert booking.customer_type == pm.COMPANY and booking.billing_company == "Muster GmbH"
    assert booking.payment_due_at is not None


def test_stay_booking_accepts_bank_transfer_for_full_prepayment():
    """Р-5: 100 % предоплаты отелю можно платить переводом, не только картой."""
    from apps.stays.models import StayUnit
    from apps.stays.services import book_stay

    _tenant(schema_name="sh23n", slug="sh23n")
    unit = StayUnit.objects.create(name="Doppelzimmer", price_cents=9000, max_guests=2, quantity=2)
    booking = book_stay(
        unit,
        arrival=date.today() + timedelta(days=7),
        departure=date.today() + timedelta(days=9),
        name="Gast",
        payment_method=pm.VORKASSE,
    )
    assert booking.payment_method == pm.VORKASSE
    assert booking.total_cents > 0


def test_legacy_calls_keep_the_previous_behaviour():
    """Вызовы без новых аргументов создают сделку как раньше (пустой способ)."""
    from apps.stays.models import StayUnit
    from apps.stays.services import book_stay

    _tenant(schema_name="sh23o", slug="sh23o")
    unit = StayUnit.objects.create(name="EZ", price_cents=5000, max_guests=1, quantity=1)
    booking = book_stay(
        unit,
        arrival=date.today() + timedelta(days=3),
        departure=date.today() + timedelta(days=4),
        name="Gast",
    )
    assert booking.payment_method == ""
    assert booking.customer_type == pm.PRIVATE
    assert booking.payment_due_at is None


def test_picker_context_hides_a_single_method_and_gates_the_invoice():
    plain = TenantFactory(schema_name="sh23p", slug="sh23p", disabled_modules=[])
    ctx = pm.picker_context(plain, "stay")
    assert ctx["payment_methods"] == []  # единственный способ — пикера нет
    assert ctx["billing_party_enabled"] is False

    rich = _tenant(schema_name="sh23q", slug="sh23q", invoice_b2b_enabled=True)
    ctx2 = pm.picker_context(rich, "stay")
    codes = [m["code"] for m in ctx2["payment_methods"]]
    assert pm.VORKASSE in codes and pm.INVOICE in codes and pm.ON_SITE in codes
    assert ctx2["billing_party_enabled"] is True


def test_buybox_tail_renders_the_picker_and_party_block():
    from django.template.loader import render_to_string

    tenant = _tenant(schema_name="sh23r", slug="sh23r", invoice_b2b_enabled=True)
    html = render_to_string(
        "storefront/_buybox_contact_fields.html",
        {"submit_label": "Buchen", **pm.picker_context(tenant, "stay")},
    )
    assert 'name="payment"' in html and 'value="invoice"' in html
    assert 'name="customer_type"' in html and 'name="billing_company"' in html
    # поля живут в форме buy-box (хвост может рендериться в портированном диалоге)
    assert html.count('form="buybox-form"') >= 6


def test_hold_window_is_computed_from_the_method():
    tenant = _tenant(schema_name="sh23s", slug="sh23s", invoice_terms_days=10, vorkasse_hold_days=2)
    assert pm.hold_days(tenant, pm.INVOICE) == 10
    assert pm.hold_days(tenant, pm.VORKASSE) == 2
    assert pm.hold_days(tenant, pm.ON_SITE) == 0


def test_amount_stays_untouched_by_the_payment_choice():
    """Способ оплаты не влияет на деньги сделки (иначе итог разъехался бы)."""
    from apps.stays.models import StayUnit
    from apps.stays.services import book_stay

    _tenant(schema_name="sh23t", slug="sh23t")
    unit = StayUnit.objects.create(name="EZ", price_cents=4000, max_guests=1, quantity=2)
    kwargs = dict(
        arrival=date.today() + timedelta(days=5),
        departure=date.today() + timedelta(days=6),
        name="Gast",
    )
    plain = book_stay(unit, **kwargs)
    with_method = book_stay(unit, payment_method=pm.VORKASSE, **kwargs)
    assert Decimal(plain.total_cents) == Decimal(with_method.total_cents)
