"""B2.1 — напоминание о незавершённой Stripe-оплате заказа: окно/фильтры/дедуп,
письмо со ссылкой, «Jetzt bezahlen» перегенерирует Checkout."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.catalog.tests.factories import ProductFactory
from apps.notifications.models import Notification
from apps.orders import services, tasks
from apps.orders.models import Order

pytestmark = pytest.mark.django_db


def _stripe_order(hours_ago=30, **kw):
    order = services.create_order(items=[(ProductFactory(), 1)], name="Kim", email="kim@test.de")
    Order.objects.filter(pk=order.pk).update(
        payment_method=kw.pop("payment_method", Order.METHOD_STRIPE),
        created_at=timezone.now() - timedelta(hours=hours_ago),
        **kw,
    )
    order.refresh_from_db()
    return order


def test_reminder_sent_once_with_pay_link():
    from apps.tenants.models import Domain
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(schema_name="public", slug="payrem-t")
    Domain.objects.create(domain="shop.test", tenant=tenant, is_primary=True)
    order = _stripe_order()
    assert tasks.send_due_payment_reminders() == 1
    n = Notification.objects.get(type="order_payment_reminder")
    assert order.reference_code in n.subject
    assert f"https://shop.test/bestellung/{order.reference_code}/" in n.payload["body"]
    assert tasks.send_due_payment_reminders() == 0  # дедуп


def test_reminder_skips_on_site_paid_and_fresh():
    _stripe_order(payment_method=Order.METHOD_ON_SITE)  # оплата на месте — норма
    _stripe_order(payment_state=Order.PAYMENT_PAID)  # уже оплачен
    _stripe_order(hours_ago=1)  # свежий — окно не наступило
    assert tasks.send_due_payment_reminders() == 0


def test_order_pay_regenerates_checkout(monkeypatch):
    import uuid

    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    from apps.orders import public_views
    from apps.tenants.tests.factories import TenantFactory

    monkeypatch.setattr(
        "apps.orders.payments.order_checkout_url", lambda *a, **k: "https://stripe.test/pay"
    )
    order = _stripe_order()

    def _req(tenant):
        r = RequestFactory().get(f"/bestellung/{order.reference_code}/bezahlen/")
        r.META["REMOTE_ADDR"] = f"10.9.{uuid.uuid4().int % 250}.9"
        SessionMiddleware(lambda x: None).process_request(r)
        MessageMiddleware(lambda x: None).process_request(r)
        r.tenant = tenant
        return r

    on = TenantFactory.build(payments_enabled=True)
    resp = public_views.order_pay(_req(on), code=order.reference_code)
    assert resp.status_code == 302 and resp.url == "https://stripe.test/pay"
    # уже оплаченный → назад на подтверждение, не в Stripe
    Order.objects.filter(pk=order.pk).update(payment_state=Order.PAYMENT_PAID)
    resp = public_views.order_pay(_req(on), code=order.reference_code)
    assert resp.url.endswith(f"/bestellung/{order.reference_code}/")
