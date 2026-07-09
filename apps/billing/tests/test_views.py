import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from apps.billing import connect, services, views
from apps.billing.state_machine import ACTIVE, TRIAL
from apps.tenants.tests.factories import TenantFactory


class _User:
    is_authenticated = True


def _request(method, path, tenant):
    request = getattr(RequestFactory(), method)(path)
    request.user = _User()
    request.tenant = tenant
    return request


def test_billing_page_renders():
    tenant = TenantFactory.build(subscription_status=TRIAL)
    resp = views.billing(_request("get", "/dashboard/billing/", tenant))
    assert resp.status_code == 200
    assert b"Billing" in resp.content


def test_checkout_redirects_to_stripe(monkeypatch, settings):
    settings.STRIPE_PRICE_ID = "price_123"
    tenant = TenantFactory.build(subscription_status=TRIAL, stripe_customer_id="cus_1")
    monkeypatch.setattr(services, "create_checkout_session", lambda t, **kw: "https://checkout/s")
    resp = views.checkout(_request("post", "/dashboard/billing/checkout/", tenant))
    assert resp.status_code == 302
    assert resp.url == "https://checkout/s"


def test_checkout_without_price_redirects_back(settings):
    settings.STRIPE_PRICE_ID = ""
    tenant = TenantFactory.build(subscription_status=TRIAL)
    request = _request("post", "/dashboard/billing/checkout/", tenant)
    # сообщение об ошибке кладётся в messages — нужен storage без session
    from django.contrib.messages.storage.cookie import CookieStorage

    request._messages = CookieStorage(request)
    resp = views.checkout(request)
    assert resp.status_code == 302  # назад на billing, без вызова Stripe


def test_portal_redirects_to_stripe(monkeypatch):
    tenant = TenantFactory.build(subscription_status=ACTIVE, stripe_customer_id="cus_1")
    monkeypatch.setattr(
        services, "create_billing_portal_session", lambda t, **kw: "https://portal/s"
    )
    resp = views.portal(_request("post", "/dashboard/billing/portal/", tenant))
    assert resp.status_code == 302
    assert resp.url == "https://portal/s"


# --- P2.5a: приём оплаты клиентов через Stripe Connect --------------------


def _req_full(method, path, tenant, params=None):
    """Запрос с реальной сессией + messages (для Connect-OAuth вьюх)."""
    request = getattr(RequestFactory(), method)(path, params or {})
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = _User()
    request.tenant = tenant
    return request


def _configure_connect(settings):
    settings.STRIPE_LIVE_MODE = False
    settings.STRIPE_TEST_SECRET_KEY = "sk_test_x"
    settings.STRIPE_CONNECT_CLIENT_ID = "ca_test"


def test_payments_page_renders(settings):
    _configure_connect(settings)
    tenant = TenantFactory.build(business_type="cafe")
    resp = views.payments(_req_full("get", "/dashboard/billing/payments/", tenant))
    assert resp.status_code == 200
    assert b"Stripe" in resp.content


def test_payments_connect_redirects_to_oauth(settings):
    _configure_connect(settings)
    tenant = TenantFactory.build()
    req = _req_full("post", "/dashboard/billing/payments/connect/", tenant)
    resp = views.payments_connect(req)
    assert resp.status_code == 302
    assert resp.url.startswith("https://connect.stripe.com/oauth/authorize")
    assert req.session["stripe_connect_state"]  # state сохранён для callback


def test_payments_connect_not_configured(settings):
    settings.STRIPE_LIVE_MODE = False
    settings.STRIPE_TEST_SECRET_KEY = ""
    settings.STRIPE_CONNECT_CLIENT_ID = ""
    tenant = TenantFactory.build()
    resp = views.payments_connect(_req_full("post", "/x/", tenant))
    assert resp.status_code == 302
    assert "stripe.com" not in (resp.url or "")  # без OAuth-редиректа


@pytest.mark.django_db
def test_payments_callback_stores_account(settings, monkeypatch):
    _configure_connect(settings)
    tenant = TenantFactory()
    monkeypatch.setattr(connect, "complete_oauth", lambda code: "acct_777")
    req = _req_full(
        "get",
        "/dashboard/billing/payments/callback/",
        tenant,
        params={"code": "c1", "state": "s1"},
    )
    req.session["stripe_connect_state"] = "s1"
    resp = views.payments_callback(req)
    assert resp.status_code == 302
    tenant.refresh_from_db()
    assert tenant.stripe_connect_id == "acct_777"
    assert tenant.payments_enabled is True


@pytest.mark.django_db
def test_payments_callback_bad_state_rejected(settings, monkeypatch):
    _configure_connect(settings)
    called = {"x": False}
    monkeypatch.setattr(
        connect, "complete_oauth", lambda code: called.__setitem__("x", True) or "acct"
    )
    tenant = TenantFactory()
    req = _req_full(
        "get",
        "/dashboard/billing/payments/callback/",
        tenant,
        params={"code": "c1", "state": "WRONG"},
    )
    req.session["stripe_connect_state"] = "s1"
    resp = views.payments_callback(req)
    assert resp.status_code == 302
    assert called["x"] is False  # обмен кода не выполнялся
    tenant.refresh_from_db()
    assert tenant.stripe_connect_id == ""


# --- E7-3: способы оплаты Stripe Checkout (payment_method_types) -----------


@pytest.mark.django_db
def test_payments_methods_saves_valid_and_drops_garbage():
    tenant = TenantFactory()
    request = _req_full(
        "post",
        "/dashboard/billing/payments/methods/",
        tenant,
        {"methods": ["card", "klarna", "bitcoin"]},
    )
    views.payments_methods(request)
    tenant.refresh_from_db()
    assert tenant.stripe_payment_methods == ["card", "klarna"]  # мусор отброшен


@pytest.mark.django_db
def test_payments_methods_empty_resets_to_default():
    tenant = TenantFactory(stripe_payment_methods=["card"])
    request = _req_full("post", "/dashboard/billing/payments/methods/", tenant)
    views.payments_methods(request)
    tenant.refresh_from_db()
    assert tenant.stripe_payment_methods == []  # пусто = дефолт Stripe Dashboard


def test_payments_page_links_to_unified_payment_settings(settings):
    # W4-3: выбор способов переехал в единый экран «Zahlung & Versand»; billing-
    # payments теперь ведёт туда ссылкой (Stripe-методы больше не тут).
    _configure_connect(settings)
    tenant = TenantFactory.build(
        business_type="cafe", stripe_connect_id="acct_1", payments_enabled=True
    )
    body = views.payments(_req_full("get", "/dashboard/billing/payments/", tenant)).content.decode()
    assert "/dashboard/settings/payments/" in body  # ссылка на единый экран
    assert 'name="methods"' not in body  # чекбоксы способов тут больше не рендерятся
