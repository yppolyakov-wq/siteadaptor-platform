"""KA-MC: сквозной денежный инвариант для 6 видов сделок.

План — docs/ka-mc-money-contract-plan-2026-10-23.md. После КАЖДОГО шага сценария
(оплата вебхуком, ручная отметка, банк, переход FSM, отмена с возвратом)
проверяются четыре правила; фаза шага задаётся сценарием явно:

- I-C: 0 ≤ возвращено ≤ оплачено ≤ итог; отменено → ждём 0.
- I-J: журнал при исполнении (решение владельца MC-D1): «open» → 0,
  «done» → проведённое = положенное к проведению, «cancel» → оплачено − возвращено.
- I-OP: в Offene Posten у сделки не больше одной строки, и её сумма = «ждём».
- I-X1: исполнено и оплата «на месте» → оплачено полностью (решение владельца X1).

Известные пробелы помечены strict-xfail с ID (MC-E8 и др.): когда пробел закроют,
параметр покраснеет и метку придётся снять.
"""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core import money_contract, transactions
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ZERO = Decimal("0")


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture(autouse=True)
def _stripe(monkeypatch):
    monkeypatch.setattr("apps.billing.connect.refund", lambda **kw: None)


@pytest.fixture
def tenant():
    return TenantFactory(schema_name="public", stripe_connect_id="acct_mc")


# --- конструкторы сделок ------------------------------------------------------------


def _order(method="on_site", **kw):
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders.services import create_order

    product = ProductFactory(base_price=Decimal("12.50"))
    order = create_order(items=[(product, 2)], name="Max", email="max@test.de", **kw)
    if method:
        order.payment_method = method
        order.save(update_fields=["payment_method"])
    return order


def _booking(deposit=0, method=""):
    from apps.booking import services
    from apps.booking.models import Resource

    res = Resource.objects.create(name=f"R {uuid.uuid4().hex[:6]}")
    start = timezone.make_aware(datetime(2027, 3, 1, 12, 0))
    b = services.book(
        res, start=start, end=start + timedelta(hours=1), name="Gast", price_cents=4000
    )
    b.payment_method = method
    b.deposit_cents = deposit  # снимок, как его ставит витрина
    b.save(update_fields=["payment_method", "deposit_cents"])
    return b


def _stay(deposit=0, method=""):
    from apps.stays import services
    from apps.stays.models import StayUnit

    unit = StayUnit.objects.create(name=f"Zimmer {uuid.uuid4().hex[:6]}", price_cents=8000)
    arrival = timezone.localdate() + timedelta(days=10)
    s = services.book_stay(
        unit, arrival=arrival, departure=arrival + timedelta(days=2), name="Gast"
    )
    s.deposit_cents = deposit
    s.payment_method = method
    s.save(update_fields=["deposit_cents", "payment_method"])
    return s


def _ticket(deposit=0, method=""):
    from apps.events.models import Event
    from apps.events.services import book_ticket

    event = Event.objects.create(
        title="Workshop",
        starts_at=timezone.now() + timedelta(days=5),
        status=Event.STATUS_PUBLISHED,
        price_cents=2000,
        deposit_percent=deposit,
        capacity=10,
    )
    t = book_ticket(event, name="K", email="k@test.de", quantity=2)
    if method:
        t.payment_method = method
        t.payment_state = t.PAYMENT_PENDING  # ждём перевод
        t.save(update_fields=["payment_method", "payment_state"])
    return t


def _job():
    from apps.jobs import services

    job = services.create_job(title="Bad streichen", name="Kunde", email="kunde@test.de")
    services.set_lines(
        job, [{"text": "Arbeit", "qty": "2", "unit_price": "50.00"}], vat_rate=Decimal("19")
    )
    return job


def _reservation():
    from apps.promotions import services
    from apps.promotions.tests.factories import PromotionFactory

    promo = PromotionFactory(price_override=Decimal("3.50"))
    return services.reserve(promo, name="Gast", email="res@test.de", quantity=2)


MAKERS = {
    "order": _order,
    "booking": _booking,
    "stay": _stay,
    "ticket": _ticket,
    "job": _job,
    "reservation": _reservation,
}


# --- шаги ---------------------------------------------------------------------------


def go(target, **extra):
    def step(kind, obj, tenant):
        transactions.apply_action(kind, obj, target, extra=extra, tenant=tenant)

    step.label = target
    return step


def pay_online(kind, obj, tenant):
    """Настоящий вебхук вида сделки (Stripe Checkout завершён)."""
    from django.db import connection

    schema = connection.schema_name
    ident = str(obj.id)
    if kind == "order":
        from apps.orders.payments import mark_order_paid

        mark_order_paid(tenant_schema=schema, order_id=ident, payment_intent="pi_mc")
    elif kind == "booking":
        from apps.booking.payments import mark_deposit_paid

        mark_deposit_paid(tenant_schema=schema, booking_id=ident, payment_intent="pi_mc")
    elif kind == "stay":
        from apps.stays.payments import mark_stay_paid

        mark_stay_paid(tenant_schema=schema, booking_id=ident, payment_intent="pi_mc")
    elif kind == "ticket":
        from apps.events.payments import mark_ticket_paid

        mark_ticket_paid(tenant_schema=schema, ticket_id=ident, payment_intent="pi_mc")
    elif kind == "job":
        from apps.jobs.payments import mark_deposit_paid

        mark_deposit_paid(tenant_schema=schema, job_id=ident, payment_intent="pi_mc")


pay_online.label = "pay_online"


def pay_cash(kind, obj, tenant):
    """Ручная отметка «bezahlt» в кабинете (касса/перевод) — единый путь контракта."""
    money_contract.settle_payment(kind, obj, source="manual")


pay_cash.label = "pay_cash"


def pay_bank(kind, obj, tenant):
    """Сопоставление банковской выписки (ERP-2) — тем же путём, что кнопка в кабинете."""
    from apps.finance import bank
    from apps.finance.models import BankTransaction

    obj.refresh_from_db()
    tx = BankTransaction.objects.create(
        date=timezone.localdate(),
        amount=money_contract.money_state(kind, obj).due,
        purpose=f"Zahlung {obj.reference_code}",
        import_hash=uuid.uuid4().hex,
    )
    bank.apply_match(tx, kind, obj)


pay_bank.label = "pay_bank"


def quote_and_accept(kind, obj, tenant):
    transactions.apply_action("job", obj, "quoted", tenant=tenant)
    transactions.apply_action("job", obj, "accepted", tenant=tenant)


quote_and_accept.label = "quoted+accepted"


def invoice_job(kind, obj, tenant):
    """Счёт из заявки: черновик → выставлен (выручка в журнал, KA-D2)."""
    from apps.finance.services import issue_invoice
    from apps.jobs.services import quote_to_invoice

    obj.refresh_from_db()
    inv = quote_to_invoice(obj)
    issue_invoice(inv, tenant=tenant)
    transactions.sm_for("job").apply(obj, "invoiced")


invoice_job.label = "invoice"


def pay_invoice(kind, obj, tenant):
    from apps.finance.state_machine import InvoiceSM

    inv = money_contract.invoice_for(kind, obj)
    InvoiceSM().apply(inv, "paid")


pay_invoice.label = "invoice_paid"


def issue_deal_invoice(kind, obj, tenant):
    """Счёт фирме по сделке (SH-23b/CO-2): «Kauf auf Rechnung»."""
    from apps.finance.services import issue_invoice_for_deal

    obj.refresh_from_db()
    issue_invoice_for_deal(kind, obj, tenant, send_email=False)


issue_deal_invoice.label = "issue_invoice"


def voucher_discount(kind, obj, tenant):
    """Скидка ваучером (снимок на сделке, как его пишет чекаут)."""
    obj.discount_cents = 1000
    obj.save(update_fields=["discount_cents"])


voucher_discount.label = "voucher"


# --- проверка -----------------------------------------------------------------------


def _open_rows(kind, obj, tenant):
    from apps.finance import bank

    ref = str(obj.reference_code)
    rows = []
    for row in bank.open_items(tenant):
        if row["kind"] == kind and row["obj"].pk == obj.pk:
            rows.append(row)
        elif row["kind"] == "invoice" and getattr(row["obj"], "deal_id", "") == ref:
            rows.append(row)
    return rows


def check(kind, obj, phase, tenant, where=""):
    obj.refresh_from_db()
    ms = money_contract.money_state(kind, obj)
    msg = f"{kind} {where}: {ms}"
    # I-C
    assert ZERO <= ms.refunded <= ms.paid <= ms.total, msg
    if phase == "cancel":
        assert ms.due == ZERO, msg
    # I-J
    if phase == "open":
        assert ms.posted == ZERO, msg
    elif phase == "done":
        assert ms.posted == ms.recognized, msg
    elif phase == "cancel":
        assert ms.posted == ms.paid - ms.refunded, msg
    # I-OP
    rows = _open_rows(kind, obj, tenant)
    assert len(rows) <= 1, f"{msg} rows={rows}"
    if rows:
        assert rows[0]["amount"] == ms.due, f"{msg} row={rows[0]['amount']}"
    elif kind != "job":
        # Сделка вне Offene Posten обязана не ждать денег через перевод/счёт.
        method = getattr(obj, "payment_method", "")
        if method in money_contract.TRANSFER_METHODS and phase != "cancel":
            assert ms.due == ZERO, f"{msg} (vorkasse/invoice due but not listed)"
    # I-X1
    if phase == "done" and kind != "job":
        method = getattr(obj, "payment_method", "") or "on_site"
        if method == "on_site":
            assert ms.paid == ms.total, f"{msg} (cash at delivery not settled)"


# --- матрица ------------------------------------------------------------------------

S = [
    # order
    (
        "order-cash-pickup",
        "order",
        {},
        [(go("confirmed"), "open"), (go("ready"), "open"), (go("picked_up"), "done")],
    ),
    (
        "order-stripe-pickup",
        "order",
        {"method": "stripe"},
        [(pay_online, "open"), (go("ready"), "open"), (go("picked_up"), "done")],
    ),
    (
        "order-vorkasse-bank",
        "order",
        {"method": "vorkasse"},
        [(pay_bank, "open"), (go("ready"), "open"), (go("picked_up"), "done")],
    ),
    (
        "order-stripe-cancel",
        "order",
        {"method": "stripe"},
        [(pay_online, "open"), (go("cancelled"), "cancel")],
    ),
    ("order-cash-cancel", "order", {}, [(go("cancelled"), "cancel")]),
    (
        "order-stripe-return",
        "order",
        {"method": "stripe"},
        [
            (pay_online, "open"),
            (go("ready"), "open"),
            (go("picked_up"), "done"),
            (go("returned"), "cancel"),
        ],
    ),
    (
        "order-invoice-paid",
        "order",
        {"method": "invoice"},
        [
            (issue_deal_invoice, "open"),
            (pay_invoice, "open"),
            (go("ready"), "open"),
            (go("picked_up"), "done"),
        ],
    ),
    (
        "order-invoice-bank-on-deal",
        "order",
        {"method": "invoice"},
        [(issue_deal_invoice, "open"), (pay_bank, "open")],
    ),
    # booking
    (
        "booking-invoice-paid",
        "booking",
        {"method": "invoice"},
        [
            (go("confirmed"), "open"),
            (issue_deal_invoice, "open"),
            (pay_invoice, "open"),
            (go("fulfilled"), "done"),
        ],
    ),
    ("booking-cash", "booking", {}, [(go("confirmed"), "open"), (go("fulfilled"), "done")]),
    (
        "booking-deposit-fulfilled",
        "booking",
        {"deposit": 1000},
        [(pay_online, "open"), (go("fulfilled"), "done")],
    ),
    (
        "booking-deposit-cancel",
        "booking",
        {"deposit": 1000},
        [(pay_online, "open"), (go("cancelled"), "cancel")],
    ),
    (
        "booking-deposit-noshow",
        "booking",
        {"deposit": 1000},
        [(pay_online, "open"), (go("no_show"), "cancel")],
    ),
    (
        "booking-deposit-cash-rest",
        "booking",
        {"deposit": 1000},
        [(pay_online, "open"), (pay_cash, "open"), (go("fulfilled"), "done")],
    ),
    # stay
    ("stay-cash", "stay", {}, [(go("confirmed"), "open"), (go("fulfilled"), "done")]),
    (
        "stay-deposit-fulfilled",
        "stay",
        {"deposit": 3000},
        [(pay_online, "open"), (go("fulfilled"), "done")],
    ),
    (
        "stay-deposit-cancel-refund",
        "stay",
        {"deposit": 3000},
        [(pay_online, "open"), (go("cancelled", refund="1"), "cancel")],
    ),
    (
        "stay-deposit-cancel-keep",
        "stay",
        {"deposit": 3000},
        [(pay_online, "open"), (go("cancelled", refund="0"), "cancel")],
    ),
    (
        "stay-deposit-noshow",
        "stay",
        {"deposit": 3000},
        [(pay_online, "open"), (go("no_show"), "cancel")],
    ),
    (
        "stay-invoice-paid",
        "stay",
        {"method": "invoice"},
        [
            (go("confirmed"), "open"),
            (issue_deal_invoice, "open"),
            (pay_invoice, "open"),
            (go("fulfilled"), "done"),
        ],
    ),
    # ticket (выручка при подтверждении, исполнение — attended)
    ("ticket-online", "ticket", {}, [(pay_online, "done"), (go("attended"), "done")]),
    ("ticket-online-cancel", "ticket", {}, [(pay_online, "done"), (go("cancelled"), "cancel")]),
    (
        "ticket-deposit-cash-attended",
        "ticket",
        {"deposit": 1000},
        [(pay_online, "done"), (pay_cash, "done"), (go("attended"), "done")],
    ),
    (
        "ticket-deposit-cancel",
        "ticket",
        {"deposit": 1000},
        [(pay_online, "done"), (go("cancelled"), "cancel")],
    ),
    (
        "ticket-voucher-vorkasse",
        "ticket",
        {"method": "vorkasse"},
        [(voucher_discount, "start"), (pay_bank, "done"), (go("attended"), "done")],
    ),
    # job (выручка при выставлении счёта)
    (
        "job-invoice-paid",
        "job",
        {},
        [
            (quote_and_accept, "open"),
            (go("done"), "open"),
            (invoice_job, "done"),
            (pay_invoice, "done"),
        ],
    ),
    (
        "job-deposit-cancel",
        "job",
        {},
        [(quote_and_accept, "open"), (pay_online, "open"), (go("cancelled"), "cancel")],
    ),
    # reservation
    (
        "reservation-fulfilled",
        "reservation",
        {},
        [(go("confirmed"), "open"), (go("fulfilled"), "done")],
    ),
    ("reservation-expired", "reservation", {}, [(go("expired"), "cancel")]),
]

KNOWN = {}


def _params():
    out = []
    for name, kind, kw, steps in S:
        marks = ()
        if name in KNOWN:
            marks = (pytest.mark.xfail(strict=True, reason=KNOWN[name]),)
        out.append(pytest.param(kind, kw, steps, id=name, marks=marks))
    return out


@pytest.mark.parametrize("kind,kw,steps", _params())
def test_money_invariant(kind, kw, steps, tenant):
    obj = MAKERS[kind](**kw)
    if kind == "job":
        obj.deposit_cents = 3000
        obj.save(update_fields=["deposit_cents"])
    check(kind, obj, "open" if kind != "ticket" else "start", tenant, where="created")
    for step, phase in steps:
        step(kind, obj, tenant)
        check(kind, obj, phase, tenant, where=getattr(step, "label", step.__name__))


def test_every_transaction_kind_has_a_money_contract():
    """Седьмой вид сделки не проскочит мимо контракта."""
    covered = {kind for _n, kind, _kw, _s in S}
    assert covered == set(transactions.TRANSACTION_KINDS)


# --- свои статусы владельца (эффекты по роли, `status_effects`) -----------------------


def _custom_tenant(monkeypatch, kind, code, role, src):
    from apps.core import status_registry

    t = TenantFactory(
        schema_name="public",
        stripe_connect_id="acct_mc",
        site_config={
            "status_defs": {kind: [status_registry.def_from_role(code, code, role, kind)]},
            "status_edges": {kind: [{"src": src, "dst": code}]},
        },
    )
    monkeypatch.setattr(status_registry, "_current_tenant", lambda: t)
    return t


def test_custom_done_status_posts_revenue_and_settles_cash(monkeypatch):
    t = _custom_tenant(monkeypatch, "order", "bar_abgeholt", "done", "ready")
    order = _order()
    for target in ("confirmed", "ready", "bar_abgeholt"):
        transactions.apply_action("order", order, target, tenant=t)
    check("order", order, "done", t, where="custom done")


def test_custom_cancel_after_deposit_keeps_journal_consistent(monkeypatch):
    t = _custom_tenant(monkeypatch, "booking", "kulanz_storno", "cancelled", "confirmed")
    booking = _booking(deposit=1000)
    pay_online("booking", booking, t)
    booking.refresh_from_db()
    transactions.apply_action("booking", booking, "kulanz_storno", tenant=t)
    check("booking", booking, "cancel", t, where="custom cancel")


# --- ревью KA-MC ------------------------------------------------------------------------


def test_paying_deal_with_issued_invoice_confirms_once(tenant, monkeypatch):
    """Оплата сделки закрывает её счёт, а оплата счёта — сделку: подтверждение одно."""
    from apps.orders.state_machine import OrderSM

    calls = []
    original = OrderSM.on_transition

    def spy(self, instance, t, **kw):
        calls.append(t.dst)
        return original(self, instance, t, **kw)

    monkeypatch.setattr(OrderSM, "on_transition", spy)
    order = _order(method="invoice")
    issue_deal_invoice("order", order, tenant)
    order.refresh_from_db()
    assert order.status == "new"
    money_contract.settle_payment("order", order)
    order.refresh_from_db()
    assert calls.count("confirmed") == 1 and order.payment_state == "paid"
    assert money_contract.invoice_for("order", order).status == "paid"


def test_cancelled_deal_is_not_marked_paid(tenant):
    order = _order()
    transactions.apply_action("order", order, "cancelled", tenant=tenant)
    order.refresh_from_db()
    assert money_contract.settle_payment("order", order) is False
    order.refresh_from_db()
    assert order.payment_state == "unpaid"


def test_outgoing_bank_payment_cannot_settle_a_deal(tenant):
    from apps.finance import bank
    from apps.finance.models import BankTransaction

    order = _order(method="vorkasse")
    tx = BankTransaction.objects.create(
        date=timezone.localdate(),
        amount=Decimal("-25.00"),
        purpose=order.reference_code,
        import_hash=uuid.uuid4().hex,
    )
    assert bank.apply_match(tx, "order", order) is False
    order.refresh_from_db()
    tx.refresh_from_db()
    assert order.payment_state == "unpaid" and tx.matched_kind == ""
