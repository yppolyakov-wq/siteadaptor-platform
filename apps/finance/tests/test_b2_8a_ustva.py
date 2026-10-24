"""KA-12 B2-8a: срез UStVA по режиму (T-1) — Soll с Mindest-Ist, Ist по датам денег, § 19."""

from datetime import date, datetime, time
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.core.models import DealPayment
from apps.finance import ustva
from apps.finance.expenses import ExpenseEntry
from apps.finance.models import RevenueEntry
from apps.finance.services import record_revenue

pytestmark = pytest.mark.django_db

SEP = (date(2026, 9, 1), date(2026, 9, 30))
OCT = (date(2026, 10, 1), date(2026, 10, 31))
NOV = (date(2026, 11, 1), date(2026, 11, 30))


def _tenant(regime="soll", small=False):
    return SimpleNamespace(tax_regime=regime, small_business=small)


def _at(day: date):
    return timezone.make_aware(datetime.combine(day, time(12)))


def _order(lines=(("11.90", "19.00", 2),)):
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders.services import create_order

    items = [
        (ProductFactory(base_price=Decimal(price), vat_rate=Decimal(rate)), None, qty)
        for price, rate, qty in lines
    ]
    return create_order(items=items, name="Gast", email="g@t.de")


def _pay(order, cents, day, refunded=0, refunded_day=None):
    row = DealPayment.objects.create(
        deal_kind="order",
        deal_id=order.pk,
        purpose="deposit",
        method="vorkasse",
        amount_cents=cents,
        source="manual",
    )
    DealPayment.objects.filter(pk=row.pk).update(
        created_at=_at(day),
        refunded_cents=refunded,
        refunded_at=_at(refunded_day) if refunded_day else None,
    )
    return row


def _slice(tenant, period):
    von, bis = period
    entries = RevenueEntry.objects.filter(date__gte=von, date__lte=bis)
    expenses = ExpenseEntry.objects.filter(date__gte=von, date__lte=bis)
    return ustva.ustva_slice(tenant, von, bis, entries, expenses)


def _book(order, day):
    record_revenue(source="order", source_ref=str(order.id), amount=order.total)
    RevenueEntry.objects.filter(source_ref=str(order.id)).update(date=day)


def test_soll_advance_taxed_on_receipt_and_deducted_at_performance():
    order = _order()  # 23,80 € @ 19 %
    _pay(order, 1000, date(2026, 9, 10))
    _book(order, date(2026, 10, 5))
    sep, octo = _slice(_tenant(), SEP), _slice(_tenant(), OCT)
    assert sep["ust"] == Decimal("1.60")  # 10,00 brutto
    assert octo["ust"] == Decimal("2.20")  # 3,80 − 1,60
    assert sep["notes"] and octo["notes"]


def test_soll_payment_on_performance_day_is_not_an_advance():
    order = _order()
    _pay(order, 2380, date(2026, 10, 5))
    _book(order, date(2026, 10, 5))
    assert _slice(_tenant(), OCT)["ust"] == Decimal("3.80")
    assert _slice(_tenant(), SEP)["ust"] == Decimal("0")


def test_soll_refunded_advance_of_cancelled_deal_nets_out():
    order = _order()
    _pay(order, 1000, date(2026, 9, 10), refunded=1000, refunded_day=date(2026, 10, 2))
    assert _slice(_tenant(), SEP)["ust"] == Decimal("1.60")
    assert _slice(_tenant(), OCT)["ust"] == Decimal("-1.60")


def test_ist_by_payment_date_and_refund_date():
    order = _order()
    _pay(order, 2380, date(2026, 9, 10), refunded=500, refunded_day=date(2026, 11, 3))
    _book(order, date(2026, 10, 5))
    t = _tenant("ist")
    assert _slice(t, SEP)["ust"] == Decimal("3.80")
    assert _slice(t, OCT)["ust"] == Decimal("0")  # журнал покрыт фолио
    assert _slice(t, NOV)["ust"] == Decimal("-0.80")


def test_ist_rest_paid_on_site_without_folio_row_counts_on_performance():
    order = _order()
    _pay(order, 1000, date(2026, 9, 10))
    _book(order, date(2026, 10, 5))
    t = _tenant("ist")
    assert _slice(t, SEP)["ust"] == Decimal("1.60")
    assert _slice(t, OCT)["ust"] == Decimal("2.20")  # 13,80 остатка на месте


def test_ist_legacy_and_non_deal_sources_by_booking_date():
    order = _order()  # без строк фолио
    _book(order, date(2026, 10, 5))
    record_revenue(source="gift", source_ref="g1", amount=Decimal("50.00"))
    RevenueEntry.objects.filter(source_ref="g1").update(date=date(2026, 10, 6))
    res = _slice(_tenant("ist"), OCT)
    assert res["ust"] == Decimal("11.78")  # 3,80 + 7,98
    assert res["notes"]


def test_mixed_rates_split_like_the_deal():
    order = _order((("10.70", "7.00", 1), ("11.90", "19.00", 1)))  # 22,60
    _pay(order, 2260, date(2026, 9, 10))
    res = _slice(_tenant("ist"), SEP)
    by_rate = {r["rate"]: r for r in res["rows"]}
    assert by_rate[Decimal("7.00")]["gross"] == Decimal("10.70")
    assert by_rate[Decimal("19.00")]["gross"] == Decimal("11.90")
    assert res["ust"] == Decimal("2.60")  # 0,70 + 1,90


def test_kleinunternehmer_no_tax_no_input_tax():
    record_revenue(source="manual", amount=Decimal("119.00"), vat_rate=Decimal("19.00"))
    ExpenseEntry.objects.create(source="manual", amount=Decimal("23.80"), vat_rate=Decimal("19"))
    today = timezone.localdate()
    res = ustva.ustva_slice(
        _tenant(small=True),
        today,
        today,
        RevenueEntry.objects.all(),
        ExpenseEntry.objects.all(),
    )
    assert res["ust"] == res["vorsteuer"] == res["zahllast"] == Decimal("0")
    assert res["regime"] == ustva.REGIME_KLEIN


def test_apply_regime_and_regime_of():
    t = _tenant()
    assert ustva.apply_regime(t, "ist") and t.tax_regime == "ist" and not t.small_business
    assert ustva.regime_of(t) == "ist"
    assert ustva.apply_regime(t, "klein") and t.small_business
    assert t.tax_regime == "ist"  # § 19 режим не стирает
    assert ustva.regime_of(t) == "klein"
    assert not ustva.apply_regime(t, "bogus")
    assert ustva.regime_of(None) == "soll"


def test_partial_refund_stamps_refunded_at():
    from apps.core import folio

    order = _order()
    row = _pay(order, 2380, date(2026, 9, 10))
    DealPayment.objects.filter(pk=row.pk).update(stripe_payment_intent="pi_x", method="stripe")
    folio.mark_refunded("order", order, intent="pi_x")
    row.refresh_from_db()
    assert row.refunded_cents == 2380 and row.refunded_at is not None
    stamp = row.refunded_at
    folio.mark_refunded("order", order, intent="pi_x")  # повтор не сдвигает дату
    row.refresh_from_db()
    assert row.refunded_at == stamp


def _owner_req(path, tenant, data):
    import uuid

    from django.contrib.auth import get_user_model
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.core.models import Membership

    user = get_user_model().objects.create_user(
        username=f"o-{uuid.uuid4().hex[:8]}", password="pw12345678"
    )
    Membership.objects.create(user=user, role=Membership.ROLE_OWNER)
    req = RequestFactory().post(path, data)
    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.user, req.tenant = user, tenant
    return req


def test_legal_docs_radio_writes_regime(settings):
    from apps.core.views import legal_docs_view
    from apps.tenants.tests.factories import TenantFactory

    settings.ROOT_URLCONF = "config.urls_tenant"
    t = TenantFactory(schema_name="ust_recht", slug="ust-recht", small_business=True)
    legal_docs_view(_owner_req("/dashboard/recht/", t, {"sec_steuer": "1", "tax_regime": "ist"}))
    t.refresh_from_db()
    assert (t.tax_regime, t.small_business) == ("ist", False)
    legal_docs_view(_owner_req("/dashboard/recht/", t, {"sec_steuer": "1", "tax_regime": "klein"}))
    t.refresh_from_db()
    assert (t.tax_regime, t.small_business) == ("ist", True)
    body = legal_docs_view(_get_req(t)).content.decode()
    assert "data-tax-regime" in body and 'value="klein" checked' in body


def _get_req(tenant):
    req = _owner_req("/dashboard/recht/x", tenant, {})
    req.method = "GET"
    req.POST = req.POST.copy()
    req.POST.clear()
    return req


def test_lite_business_radio_writes_regime(settings):
    from apps.core import lite_cabinet
    from apps.tenants.tests.factories import TenantFactory

    settings.ROOT_URLCONF = "config.urls_tenant"
    t = TenantFactory(schema_name="ust_lite", slug="ust-lite", name="Krume")
    t.site_config = {"profile": "aktionen"}
    t.save()
    data = {
        "name": "Krume",
        "address": "Markt 1, Solingen",
        "contact_phone": "0212 1",
        "contact_email": "i@k.example.com",
        "tax_choice": "ist",
    }
    resp = lite_cabinet.lite_business(_owner_req("/dashboard/geschaeft/", t, data))
    assert resp.status_code == 302
    t.refresh_from_db()
    assert t.tax_regime == "ist" and not t.small_business
    del data["tax_choice"]  # без поля — режим не трогаем
    lite_cabinet.lite_business(_owner_req("/dashboard/geschaeft/2", t, data))
    t.refresh_from_db()
    assert t.tax_regime == "ist"
