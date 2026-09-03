"""SH-23d: паритет покупки по акции, экран «Zahlungen» по всем видам и снятие
удержания по прошедшему сроку оплаты (решение владельца Р-4).

План — `docs/order-feedback-plan-2026-09-03.md` §6.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core import payment_holds, payment_methods as pm, payments_page
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _tenant(**kw):
    kw.setdefault("disabled_modules", [])
    kw.setdefault("vorkasse_enabled", True)
    kw.setdefault("bank_iban", "DE89370400440532013000")
    return TenantFactory(**kw)


def _stay(tenant, **kw):
    from apps.stays.models import StayUnit
    from apps.stays.services import book_stay

    unit = StayUnit.objects.create(name="EZ", price_cents=6000, max_guests=2, quantity=3)
    return book_stay(
        unit,
        arrival=date.today() + timedelta(days=10),
        departure=date.today() + timedelta(days=12),
        name="Gast",
        **kw,
    )


# ─────────────────────────── удержание (Р-4) ───────────────────────────


def test_overdue_unpaid_booking_is_released():
    tenant = _tenant(schema_name="sh23u", slug="sh23u")
    booking = _stay(
        tenant,
        payment_method=pm.VORKASSE,
        payment_due_at=timezone.now() - timedelta(hours=1),
    )
    assert payment_holds.expire_overdue(tenant) == 1
    booking.refresh_from_db()
    assert booking.status == "cancelled"


def test_deal_without_a_due_date_is_never_touched():
    """Оплата на месте и онлайн срока не имеют — их держать нечем и не нужно."""
    tenant = _tenant(schema_name="sh23v", slug="sh23v")
    booking = _stay(tenant, payment_method=pm.ON_SITE)
    assert booking.payment_due_at is None
    assert payment_holds.expire_overdue(tenant) == 0
    booking.refresh_from_db()
    assert booking.status != "cancelled"


def test_future_due_date_is_not_released_and_pass_is_idempotent():
    tenant = _tenant(schema_name="sh23w", slug="sh23w")
    fresh = _stay(
        tenant, payment_method=pm.VORKASSE, payment_due_at=timezone.now() + timedelta(days=2)
    )
    overdue = _stay(
        tenant, payment_method=pm.VORKASSE, payment_due_at=timezone.now() - timedelta(minutes=5)
    )
    assert payment_holds.expire_overdue(tenant) == 1
    assert payment_holds.expire_overdue(tenant) == 0  # второй проход — no-op
    fresh.refresh_from_db()
    overdue.refresh_from_db()
    assert fresh.status != "cancelled" and overdue.status == "cancelled"


def test_paid_deal_survives_even_with_a_past_due_date():
    """Оплату «в последнюю минуту» экспирация не затирает."""
    from apps.stays.models import StayBooking

    tenant = _tenant(schema_name="sh23x", slug="sh23x")
    booking = _stay(
        tenant, payment_method=pm.VORKASSE, payment_due_at=timezone.now() - timedelta(days=1)
    )
    StayBooking.objects.filter(pk=booking.pk).update(payment_state="paid")
    assert payment_holds.expire_overdue(tenant) == 0
    booking.refresh_from_db()
    assert booking.status != "cancelled"


# ─────────────────────────── экран «Zahlungen» ───────────────────────────


def test_payment_rows_filter_by_method_across_kinds():
    """До SH-23d фильтр по способу выбрасывал все виды кроме заказа."""
    tenant = _tenant(schema_name="sh23y", slug="sh23y")
    _stay(tenant, payment_method=pm.VORKASSE)
    rows = payments_page.payment_rows(tenant, state="", method=pm.VORKASSE)
    kinds = {r["kind"] for r in rows}
    assert "stay" in kinds
    assert all(r["payment_method"] == pm.VORKASSE for r in rows)
    labels = {r["payment_method_label"] for r in rows}
    assert labels and "" not in labels  # подпись способа есть у не-заказов


def test_payment_rows_expose_the_due_date():
    tenant = _tenant(schema_name="sh23z", slug="sh23z")
    due = timezone.now() + timedelta(days=5)
    _stay(tenant, payment_method=pm.VORKASSE, payment_due_at=due)
    row = next(r for r in payments_page.payment_rows(tenant, state="") if r["kind"] == "stay")
    assert row["payment_due_at"] == due


# ─────────────────────────── покупка по акции ───────────────────────────


def test_promo_purchase_carries_the_payment_choice():
    from apps.catalog.models import Product
    from apps.promotions.models import Promotion
    from apps.promotions.services import purchase

    _tenant(schema_name="sh24a2", slug="sh24a2")
    product = Product.objects.create(
        name={"de": "Saft"}, base_price=Decimal("2.49"), stock_quantity=20
    )
    promo = Promotion.objects.create(
        title={"de": "Saft-Deal"},
        status="active",
        product=product,
        price_override=Decimal("1.99"),
        compare_at_price=product.base_price,
    )
    order = purchase(
        promo,
        quantity=1,
        name="Kunde",
        payment_method=pm.VORKASSE,
        customer_type=pm.COMPANY,
        billing_company="Muster GmbH",
        payment_due_at=timezone.now() + timedelta(days=3),
    )
    assert order.payment_method == pm.VORKASSE
    assert order.customer_type == pm.COMPANY and order.billing_company == "Muster GmbH"
    assert order.payment_due_at is not None


def test_promo_detail_renders_the_payment_picker():
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.promotions import public_views
    from apps.promotions.models import Promotion

    tenant = _tenant(schema_name="sh24b2", slug="sh24b2", invoice_b2b_enabled=True)
    promo = Promotion.objects.create(
        title={"de": "Freie Aktion"}, status="active", available_quantity=5
    )
    request = RequestFactory().get(f"/p/{promo.pk}/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = tenant
    body = public_views.promotion_detail(request, pk=promo.pk).content.decode()
    assert 'name="payment"' in body and 'value="invoice"' in body
    assert 'name="customer_type"' in body
