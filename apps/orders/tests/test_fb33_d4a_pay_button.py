"""FB-33 D4a (стопка 13): «Jetzt bezahlen» — одно условие на три места.

`payments.pay_state(order, tenant)` — "open" (кнопка) · "processing" (оплата «в пути») ·
"closed" (минуты до автоотмены) · "unavailable" (онлайн-оплата у бизнеса выключена) ·
"cancelled" (stripe-заказ отменён — «Bestellung storniert», а не «Pay in store at pickup.») ·
"" (не онлайн-заказ / уже оплачен). Зовут `order_pay`, offer action pay и подтверждение.
"""

import pytest
from django.contrib.messages import get_messages
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection
from django.test import RequestFactory
from django.utils import translation

from apps.orders import payments, public_views
from apps.orders.models import Offer, Order
from apps.orders.tests.test_fb33_m2i71_abandoned import _order
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ACCOUNT = "acct_d4a_btn"
STRIPE_URL = "https://stripe.test/pay"

TEXTS = {
    "processing": "Ihre Zahlung wird bereits verarbeitet.",
    "closed": "Diese Bestellung kann nicht mehr online bezahlt werden. Bitte bestellen Sie neu.",
    "unavailable": "Payment is temporarily unavailable. Please try again later.",
    "cancelled": "Bestellung storniert",
}


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


@pytest.fixture(autouse=True)
def _clean_cache():
    from django.core.cache import cache

    cache.clear()


def _biz(enabled=True):
    from apps.tenants.models import Tenant

    Tenant.objects.filter(schema_name=connection.schema_name).delete()
    return TenantFactory(
        schema_name=connection.schema_name,
        stripe_connect_id=ACCOUNT,
        orders_prepay=True,
        payments_enabled=enabled,
    )


def _state_order(state):
    if state == "open":
        return _order(hours_ago=1)
    if state == "processing":
        return _order(hours_ago=1, stripe_payment_intent="pi_sepa")
    if state == "closed":
        return _order(hours_ago=23.9)
    if state == "cancelled":
        order = _order(hours_ago=1)
        Order.objects.filter(pk=order.pk).update(
            status=Order.STATUS_CANCELLED, payment_state=Order.PAYMENT_REFUNDED
        )
        order.refresh_from_db()
        return order
    if state == "paid":
        return _order(hours_ago=1, payment_state=Order.PAYMENT_PAID)
    if state == "unavailable":
        return _order(hours_ago=1)
    raise AssertionError(state)


def _request(path, biz, method="get", data=None):
    request = getattr(RequestFactory(), method)(path, data or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.tenant = biz
    return request


STATES = ["open", "processing", "closed", "cancelled", "paid", "unavailable"]
EXPECTED = {
    "open": "open",
    "processing": "processing",
    "closed": "closed",
    "cancelled": "cancelled",
    "paid": "",
    "unavailable": "unavailable",
}


@pytest.mark.parametrize("state", STATES)
def test_pay_state_one_source(monkeypatch, state):
    biz = _biz(enabled=state != "unavailable")
    order = _state_order(state)
    assert payments.pay_state(order, biz) == EXPECTED[state]
    monkeypatch.setattr(payments, "order_checkout_url", lambda *a, **kw: STRIPE_URL)
    monkeypatch.setattr(public_views, "_require_orders_active", lambda r: None)

    resp = public_views.order_pay(
        _request(f"/bestellung/{order.reference_code}/bezahlen/", biz), order.reference_code
    )
    assert (resp.url == STRIPE_URL) is (state == "open")

    from apps.orders.tests.test_offer_page import _offer

    offer = _offer()
    Offer.objects.filter(pk=offer.pk).update(status=Offer.STATUS_ACCEPTED, order=order)
    resp = public_views.offer_page(
        _request("/o/x/", biz, "post", {"action": "pay"}), token=offer.token
    )
    assert (resp.url == STRIPE_URL) is (state == "open")

    with translation.override("de"):
        html = public_views.order_confirmation(
            _request(f"/bestellung/{order.reference_code}/", biz), code=order.reference_code
        ).content.decode()
    pay_href = f'href="/bestellung/{order.reference_code}/bezahlen/"'
    assert (pay_href in html) is (state == "open")
    if state in TEXTS:
        with translation.override("de"):
            assert translation.gettext(TEXTS[state]) in html


def test_cancelled_stripe_order_is_not_pay_in_store():
    biz = _biz()
    order = _state_order("cancelled")
    with translation.override("de"):
        html = public_views.order_confirmation(
            _request(f"/bestellung/{order.reference_code}/", biz), code=order.reference_code
        ).content.decode()
    assert "Bestellung storniert" in html
    assert "Zahlung bei Abholung" not in html and "Pay in store at pickup." not in html


def test_order_pay_unavailable_says_so(monkeypatch):
    biz = _biz(enabled=False)
    order = _state_order("unavailable")
    monkeypatch.setattr(public_views, "_require_orders_active", lambda r: None)
    request = _request(f"/bestellung/{order.reference_code}/bezahlen/", biz)
    with translation.override("en"):
        public_views.order_pay(request, order.reference_code)
    assert [str(m) for m in get_messages(request)] == [TEXTS["unavailable"]]


def test_on_site_order_confirmation_unchanged():
    """Контроль: заказ «на месте» — без кнопки и без текстов состояний."""
    biz = _biz()
    order = _order(hours_ago=1, method=Order.METHOD_ON_SITE)
    assert payments.pay_state(order, biz) == "" if hasattr(payments, "pay_state") else True
    with translation.override("de"):
        html = public_views.order_confirmation(
            _request(f"/bestellung/{order.reference_code}/", biz), code=order.reference_code
        ).content.decode()
    assert "/bezahlen/" not in html
    with translation.override("de"):
        for text in TEXTS.values():
            assert translation.gettext(text) not in html
