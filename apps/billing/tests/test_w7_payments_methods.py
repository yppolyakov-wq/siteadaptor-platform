"""W7a (аудит 2026-08-05): легаси-эндпоинт billing-payments-methods больше не пишет —
форма Stripe-методов живёт на едином экране «Zahlung & Versand» (W4-3), а живой
приёмник без формы обнулял stripe_payment_methods пустым POST."""

import pytest
from django.test import RequestFactory

from apps.billing import views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


class _User:
    is_authenticated = True
    is_active = True


def test_empty_post_no_longer_wipes_methods():
    tenant = TenantFactory(business_type="bakery")
    tenant.stripe_payment_methods = ["card", "paypal"]
    tenant.save(update_fields=["stripe_payment_methods"])
    req = RequestFactory().post("/dashboard/billing/payments/methods/", {})
    req.user = _User()
    req.tenant = tenant
    resp = views.payments_methods(req)
    assert resp.status_code == 302
    assert resp["Location"].endswith("/dashboard/settings/payments/")
    tenant.refresh_from_db()
    assert tenant.stripe_payment_methods == ["card", "paypal"]
