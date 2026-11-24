"""FB-33 D4a (стопка 13): автоотмена брошенного заказа закрывает его сессии Stripe.

Id сессии Checkout запоминается в кэше (`order-sessions:{schema}:{pk}:*`, не больше
`ORDER_SESSIONS_MAX`, атомарно — `cache.incr`), вместе с аккаунтом. После транзакции отмены
`payments.expire_open_sessions` закрывает их на connected account бизнеса (аккаунт — из
`Tenant`). «Не ответил ≠ отказал»: `unknown` ничего не помечает и останавливает проход по
схеме; закрытые (`expired`/`closed`) id убираются из кэша. Потолок вызовов и бюджет времени.
"""

import logging
import threading

import pytest
import stripe
from django.db import connection
from django.utils import timezone

from apps.billing import connect
from apps.orders import payments, tasks
from apps.orders.models import Order
from apps.orders.tests.test_fb33_m2i71_abandoned import _order
from apps.tenants.tests.factories import TenantFactory

pytestmark = [
    pytest.mark.django_db(transaction=False),
    pytest.mark.xfail(strict=True, reason="FB-33 D4a: до правки"),
]

ACCOUNT = "acct_d4a_exp"


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture(autouse=True)
def _clean_cache():
    from django.core.cache import cache

    cache.clear()


@pytest.fixture
def biz():
    return TenantFactory(
        schema_name=connection.schema_name,
        stripe_connect_id=ACCOUNT,
        orders_prepay=True,
        payments_enabled=True,
    )


class _FakeStripe:
    """`Session.create` и `Session.expire` без сети; `errors` — исключение по id."""

    def __init__(self):
        self.created = 0
        self.expired = []
        self.errors = {}
        self.atomic_depth = []

    def create(self, **kw):
        self.created += 1
        return {"id": f"cs_{self.created}", "url": f"https://stripe.test/{self.created}"}

    def expire(self, session_id, **kw):
        self.atomic_depth.append(len(connection.atomic_blocks))
        self.expired.append((session_id, kw.get("stripe_account")))
        exc = self.errors.get(session_id)
        if exc is not None:
            raise exc
        return {"id": session_id, "status": "expired"}


@pytest.fixture
def fake(monkeypatch):
    f = _FakeStripe()

    class _Session:
        create = staticmethod(f.create)
        expire = staticmethod(f.expire)

    class _Checkout:
        Session = _Session

    class _Client:
        checkout = _Checkout

    monkeypatch.setattr(connect, "_client", lambda: _Client)
    return f


def _checkout(order, biz, n=1):
    for _ in range(n):
        payments.order_checkout_url(
            order, biz, success_url="https://s/ok", cancel_url="https://s/x"
        )


def test_connected_checkout_returns_url_and_id(fake):
    url, sid = connect.connected_checkout(
        connect_id=ACCOUNT,
        amount_cents=1000,
        product_name="x",
        metadata={},
        success_url="https://s/ok",
        cancel_url="https://s/x",
    )
    assert (url, sid) == ("https://stripe.test/1", "cs_1")


def test_expire_on_connected_account(biz, fake):
    order = _order()
    _checkout(order, biz, n=3)
    assert tasks.expire_abandoned_online() == 1
    assert sorted(fake.expired) == [(f"cs_{i}", ACCOUNT) for i in (1, 2, 3)]


def test_expire_after_commit(biz, fake):
    base = len(connection.atomic_blocks)
    order = _order()
    _checkout(order, biz)
    tasks.expire_abandoned_online()
    assert fake.atomic_depth == [base]


def test_expired_ids_leave_the_cache(biz, fake):
    order = _order()
    _checkout(order, biz, n=2)
    tasks.expire_abandoned_online()
    assert payments.remembered_sessions(order.pk) == []


def test_expire_errors_logged_not_raised(biz, fake, caplog):
    order = _order()
    _checkout(order, biz, n=2)
    fake.errors["cs_1"] = stripe.error.InvalidRequestError(
        "No such checkout.session", "session", code="resource_missing"
    )
    fake.errors["cs_2"] = stripe.error.APIConnectionError("timeout")
    with caplog.at_level(logging.INFO):
        assert tasks.expire_abandoned_online() == 1
    order.refresh_from_db()
    assert order.status == Order.STATUS_CANCELLED
    levels = {r.levelno for r in caplog.records if "session" in r.getMessage()}
    assert logging.INFO in levels and logging.WARNING in levels


def test_expire_session_outcomes(fake):
    fake.errors["cs_gone"] = stripe.error.InvalidRequestError(
        "No such checkout.session", "session", code="resource_missing"
    )
    fake.errors["cs_net"] = stripe.error.APIConnectionError("timeout")
    assert connect.expire_session(connect_id=ACCOUNT, session_id="cs_ok") == "expired"
    assert connect.expire_session(connect_id=ACCOUNT, session_id="cs_gone") == "closed"
    assert connect.expire_session(connect_id=ACCOUNT, session_id="cs_net") == "unknown"


def test_expire_invalid_request_other_code_is_unknown(fake):
    fake.errors["cs_x"] = stripe.error.InvalidRequestError(
        "Invalid API key", "key", code="api_key_invalid"
    )
    assert connect.expire_session(connect_id=ACCOUNT, session_id="cs_x") == "unknown"


def test_expire_already_complete_is_closed(fake):
    fake.errors["cs_done"] = stripe.error.InvalidRequestError(
        'Only Checkout Sessions with a status in ["open"] can be expired. This Checkout '
        'Session has a status of "complete".',
        None,
    )
    assert connect.expire_session(connect_id=ACCOUNT, session_id="cs_done") == "closed"


def test_session_ids_capped(biz, fake, caplog):
    order = _order(hours_ago=1)
    with caplog.at_level(logging.WARNING):
        _checkout(order, biz, n=payments.ORDER_SESSIONS_MAX + 3)
    assert len(payments.remembered_sessions(order.pk)) == payments.ORDER_SESSIONS_MAX
    assert any("session" in r.getMessage() for r in caplog.records)


def test_remember_sessions_concurrent(biz):
    order = _order(hours_ago=1)
    schema = connection.schema_name

    def worker(start):
        for i in range(4):
            payments._remember_session(order, f"cs_t{start}_{i}", ACCOUNT, schema=schema)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ids = {s["id"] for s in payments.remembered_sessions(order.pk)}
    assert len(ids) == 8


def test_expire_stops_after_unknown(biz, fake):
    orders = [_order(hours_ago=30 - i) for i in range(3)]
    for order in orders:
        _checkout(order, biz)
    fake.errors["cs_1"] = stripe.error.APIConnectionError("timeout")
    tasks.expire_abandoned_online()
    assert [sid for sid, _acct in fake.expired] == ["cs_1"]
    assert payments.remembered_sessions(orders[0].pk)  # не помечено — осталось


def test_expire_calls_capped(biz, fake, monkeypatch):
    monkeypatch.setattr(payments, "EXPIRE_CALLS_MAX", 2)
    order = _order()
    _checkout(order, biz, n=5)
    tasks.expire_abandoned_online()
    assert len(fake.expired) == 2


def test_expire_pass_bounded_by_budget(biz, fake, monkeypatch):
    clock = iter([0.0, 0.0, 1000.0, 1000.0, 1000.0, 1000.0, 1000.0])
    monkeypatch.setattr(payments, "_monotonic", lambda: next(clock, 1000.0))
    order = _order()
    _checkout(order, biz, n=3)
    tasks.expire_abandoned_online()
    assert len(fake.expired) == 1


def test_foreign_remembered_account_is_skipped(biz, fake):
    order = _order()
    payments._remember_session(order, "cs_old", "acct_old", schema=connection.schema_name)
    tasks.expire_abandoned_online()
    assert fake.expired == []


def test_unpaid_live_order_sessions_untouched(biz, fake):
    order = _order(hours_ago=1)
    _checkout(order, biz)
    tasks.expire_abandoned_online(timezone.now())
    assert fake.expired == []
    assert payments.remembered_sessions(order.pk)
