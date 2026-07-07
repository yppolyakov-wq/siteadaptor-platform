"""UD4b: гейтинг каналов на уровне enqueue — отключённый канал не отправляется."""

from decimal import Decimal

import pytest

from apps.catalog.tests.factories import ProductFactory
from apps.notifications.models import Notification
from apps.orders import notifications as onot
from apps.orders.services import create_order
from apps.telegram.models import TelegramBot, TelegramLink
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _configured_tenant(cfg):
    t = TenantFactory.build(business_type="restaurant")
    t.site_config = {"notify": cfg}
    return t


def test_customer_telegram_suppressed_when_disabled(monkeypatch):
    TelegramBot.objects.create(token="t", bot_username="B", is_active=True)
    order = create_order(
        items=[(ProductFactory(base_price=Decimal("8.00")), 1)], name="M", email="m@test.de"
    )
    TelegramLink.objects.create(customer=order.customer, link_token="tk", chat_id="123")
    tenant = _configured_tenant({"customer": {"order:ready": {"email": True, "telegram": False}}})
    monkeypatch.setattr(onot, "_tenant", lambda schema: tenant)

    onot.enqueue_order_email(order, "ready")
    # Telegram отключён → нет tg-уведомления; email включён → есть customer-письмо
    assert not Notification.objects.filter(dedupe_key=f"order:{order.id}:ready:tg").exists()
    assert Notification.objects.filter(dedupe_key=f"order:{order.id}:ready:customer").exists()


def test_customer_email_suppressed_when_disabled(monkeypatch):
    TelegramBot.objects.create(token="t", bot_username="B", is_active=True)
    order = create_order(
        items=[(ProductFactory(base_price=Decimal("8.00")), 1)], name="M2", email="m2@test.de"
    )
    TelegramLink.objects.create(customer=order.customer, link_token="tk2", chat_id="124")
    tenant = _configured_tenant({"customer": {"order:ready": {"email": False, "telegram": True}}})
    monkeypatch.setattr(onot, "_tenant", lambda schema: tenant)

    onot.enqueue_order_email(order, "ready")
    assert not Notification.objects.filter(dedupe_key=f"order:{order.id}:ready:customer").exists()
    assert Notification.objects.filter(dedupe_key=f"order:{order.id}:ready:tg").exists()


def test_unconfigured_tenant_sends_both_channels(monkeypatch):
    TelegramBot.objects.create(token="t", bot_username="B", is_active=True)
    order = create_order(
        items=[(ProductFactory(base_price=Decimal("8.00")), 1)], name="M3", email="m3@test.de"
    )
    TelegramLink.objects.create(customer=order.customer, link_token="tk3", chat_id="125")
    monkeypatch.setattr(onot, "_tenant", lambda schema: _configured_tenant({}))

    onot.enqueue_order_email(order, "ready")
    assert Notification.objects.filter(dedupe_key=f"order:{order.id}:ready:customer").exists()
    assert Notification.objects.filter(dedupe_key=f"order:{order.id}:ready:tg").exists()
