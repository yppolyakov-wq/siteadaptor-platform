from django.test import RequestFactory

from apps.billing import services, views
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
