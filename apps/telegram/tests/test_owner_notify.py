"""UD4c: привязка Telegram владельца (deep-link owner-<token>) + пуш владельцу."""

import pytest

from apps.notifications.models import Notification
from apps.telegram import notify
from apps.telegram import webhook as wh
from apps.telegram.models import TelegramBot
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _bot(active=True, username="OwnerBot"):
    return TelegramBot.objects.create(token="t", bot_username=username, is_active=active)


def test_owner_deep_link_empty_without_bot():
    assert notify.owner_deep_link(TenantFactory()) == ""


def test_owner_deep_link_and_link_sets_chat_id():
    _bot()
    tenant = TenantFactory()
    url = notify.owner_deep_link(tenant)
    assert url.startswith("https://t.me/OwnerBot?start=owner-")
    token = url.rsplit("start=owner-", 1)[1]
    assert notify.link_owner_from_start(f"owner-{token}", 42, tenant) is True
    assert notify.owner_chat_id(tenant) == "42"


def test_link_owner_rejects_wrong_token_and_non_owner_payload():
    _bot()
    tenant = TenantFactory()
    notify.owner_deep_link(tenant)  # завести токен
    assert notify.link_owner_from_start("owner-wrong", 1, tenant) is False
    assert notify.link_owner_from_start("customer-token", 1, tenant) is False


def test_webhook_routes_owner_token(monkeypatch):
    from apps.telegram import services

    _bot()
    tenant = TenantFactory()
    token = notify.owner_deep_link(tenant).rsplit("start=owner-", 1)[1]
    monkeypatch.setattr(services, "send_message", lambda *a, **k: None)
    req = type(
        "R", (), {"build_absolute_uri": lambda self, u: "https://shop.test/", "tenant": tenant}
    )()
    wh.handle_update(
        TelegramBot.objects.first(),
        {"message": {"chat": {"id": 888}, "text": f"/start owner-{token}"}},
        req,
    )
    assert notify.owner_chat_id(tenant) == "888"


def test_send_to_owner_creates_notification_when_linked():
    _bot()
    tenant = TenantFactory()
    token = notify.owner_deep_link(tenant).rsplit("start=owner-", 1)[1]
    notify.link_owner_from_start(f"owner-{token}", 555, tenant)
    notify.send_to_owner(
        tenant, type="order_created_owner", dedupe_key="order:x:created:owner:tg", text="Neu!"
    )
    n = Notification.objects.get(dedupe_key="order:x:created:owner:tg")
    assert n.channel == Notification.TELEGRAM and n.recipient == "555"


def test_send_to_owner_skips_when_unlinked():
    _bot()
    notify.send_to_owner(TenantFactory(), type="x", dedupe_key="order:y:created:owner:tg", text="x")
    assert not Notification.objects.filter(dedupe_key="order:y:created:owner:tg").exists()
