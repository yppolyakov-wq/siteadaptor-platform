"""MX-7: цифровые Вещи (сертификат/абонемент) и Offer — в общий учёт."""

import pytest

from apps.finance.models import RevenueEntry
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def test_gift_paid_writes_revenue_idempotently():
    from apps.loyalty.gift import create_gift_voucher, mark_gift_voucher_paid

    TenantFactory(schema_name="public")
    gift = create_gift_voucher(amount_cents=5000, buyer_name="A", buyer_email="a@t.de", message="")
    for _ in range(2):  # повтор вебхука
        mark_gift_voucher_paid(tenant_schema="public", gift_id=str(gift.pk))
    entries = RevenueEntry.objects.filter(source="gift")
    assert entries.count() == 1 and entries.get().amount == 50


def test_pass_purchase_writes_revenue():
    from apps.booking.models import PassPlan
    from apps.booking.pass_payments import purchase_pass

    TenantFactory(schema_name="public")
    plan = PassPlan.objects.create(label="10er-Karte", credits=10, price_cents=20000)
    ok = purchase_pass(
        tenant_schema="public",
        plan_id=str(plan.pk),
        name="B",
        email="b@t.de",
        payment_intent="pi_test_1",
    )
    assert ok
    entries = RevenueEntry.objects.filter(source="pass")
    assert entries.count() == 1 and entries.get().amount == 200
    # повтор вебхука (тот же intent) не плодит ни карту, ни выручку
    purchase_pass(
        tenant_schema="public",
        plan_id=str(plan.pk),
        name="B",
        email="b@t.de",
        payment_intent="pi_test_1",
    )
    assert RevenueEntry.objects.filter(source="pass").count() == 1


def test_digital_shelf_lists_plans_and_gift():
    from apps.booking.models import PassPlan
    from apps.core import sellable_manage as sm

    tenant = TenantFactory(enabled_modules=["booking", "gift"])
    PassPlan.objects.create(label="5er-Karte", credits=5, price_cents=9000)
    shelf = sm.digital_shelf(tenant)
    labels = [str(s["label"]) for s in shelf]
    assert any("Mehrfachkarten" in x for x in labels)
    assert any("Geschenkgutscheine" in x for x in labels)


def test_offer_appears_in_palette_deals():
    from apps.core import palette_search
    from apps.orders.models import Offer

    tenant = TenantFactory(enabled_modules=["orders"])
    Offer.objects.create(customer_name="Fahrrad Meier", customer_email="m@t.de")
    rows = palette_search._deals(tenant, "Fahrrad")
    assert any("Angebot ·" in r["label"] for r in rows)
