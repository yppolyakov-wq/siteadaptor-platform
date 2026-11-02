"""Один Telegram-бот — один хозяин (ops 2026-11-02).

На проде @a123siteadaptor_bot был подключён в двух бизнесах: Telegram шлёт сообщения на
один адрес, поэтому второе подключение молча забирало вебхук у первого, а отключение
у любого снимало его у обоих. Замки: дубль отказывается, чужой вебхук не снимается,
бот портала/платформы не уходит в бизнес и обратно.

В тестах TENANT-таблицы общие (test.py подключает их как SHARED), поэтому строка бота,
созданная один раз, видна «изнутри» любой схемы — этим и моделируется второй бизнес.
"""

from io import StringIO

import pytest
from django.core.management import call_command

from apps.aggregator.models import PortalBot
from apps.aggregator.tests.test_portal_bot import _portal
from apps.telegram import ownership, services, views
from apps.telegram.models import TelegramBot
from apps.telegram.tests.test_telegram import _request
from apps.tenants.tests.factories import DomainFactory, TenantFactory

pytestmark = pytest.mark.django_db


def test_bot_id_is_token_prefix():
    assert ownership.bot_id("123456:AA-bb") == "123456"
    assert ownership.bot_id("garbage") == ""
    assert ownership.bot_id("abc:def") == ""


def test_connect_refuses_bot_active_in_another_business(monkeypatch):
    TenantFactory(schema_name="otherbiz")
    TelegramBot.objects.create(token="777:OLD", is_active=True, bot_username="SharedBot")
    monkeypatch.setattr(services, "get_me", lambda token: {"username": "SharedBot"})
    monkeypatch.setattr(services, "tenant_base_url", lambda: "https://shop.test")
    calls = []
    monkeypatch.setattr(services, "set_webhook", lambda *a: calls.append(a))
    # Перевыпущенный токен того же бота — тот же id, тот же бот.
    req = _request("post", "/dashboard/telegram/connect/", data={"token": "777:NEW"}, user=True)
    views.connect(req)
    assert calls == []
    assert TelegramBot.objects.get().token == "777:OLD"
    text = " ".join(str(m) for m in req._messages)
    assert "otherbiz" not in text  # чужой бизнес не называем


def test_connect_allows_other_bot(monkeypatch):
    TenantFactory(schema_name="otherbiz")
    TelegramBot.objects.create(token="777:OLD", is_active=False)  # отключённый не держит
    monkeypatch.setattr(services, "get_me", lambda token: {"username": "MyBot"})
    monkeypatch.setattr(services, "tenant_base_url", lambda: "https://shop.test")
    calls = []
    monkeypatch.setattr(services, "set_webhook", lambda *a: calls.append(a))
    req = _request("post", "/dashboard/telegram/connect/", data={"token": "777:NEW"}, user=True)
    views.connect(req)
    assert calls and TelegramBot.objects.get().is_active


def test_connect_refuses_portal_bot_token(monkeypatch):
    PortalBot.objects.create(
        portal=_portal(host="own.siteadaptor.de"), token="888:P", is_active=True
    )
    monkeypatch.setattr(services, "get_me", lambda token: {"username": "PortalBot"})
    monkeypatch.setattr(services, "tenant_base_url", lambda: "https://shop.test")
    calls = []
    monkeypatch.setattr(services, "set_webhook", lambda *a: calls.append(a))
    req = _request("post", "/dashboard/telegram/connect/", data={"token": "888:P"}, user=True)
    views.connect(req)
    assert calls == []


def test_disconnect_keeps_webhook_of_other_owner(monkeypatch):
    TenantFactory(schema_name="otherbiz")
    TelegramBot.objects.create(token="777:OLD", is_active=True)
    deleted = []
    monkeypatch.setattr(services, "delete_webhook", lambda token: deleted.append(token))
    views.disconnect(_request("post", "/dashboard/telegram/disconnect/", user=True))
    assert deleted == []
    assert TelegramBot.objects.get().is_active is False


def test_disconnect_removes_webhook_when_sole_owner(monkeypatch):
    TelegramBot.objects.create(token="777:OLD", is_active=True)
    deleted = []
    monkeypatch.setattr(services, "delete_webhook", lambda token: deleted.append(token))
    views.disconnect(_request("post", "/dashboard/telegram/disconnect/", user=True))
    assert deleted == ["777:OLD"]


def test_portal_connect_refuses_business_bot(monkeypatch):
    from apps.aggregator import telegram_bot

    TenantFactory(schema_name="otherbiz")
    TelegramBot.objects.create(token="999:B", is_active=True)
    pbot = PortalBot.objects.create(portal=_portal(host="p.siteadaptor.de"), token="999:B")
    monkeypatch.setattr(services, "set_webhook", lambda *a: pytest.fail("webhook moved"))
    with pytest.raises(telegram_bot.BotAlreadyConnected):
        telegram_bot.connect_bot(pbot)


def test_platform_token_check_refuses_business_bot(monkeypatch):
    from apps.platform_bot import config

    TenantFactory(schema_name="otherbiz")
    TelegramBot.objects.create(token="555:B", is_active=True)
    monkeypatch.setattr(services, "get_me", lambda token: {"is_bot": True, "username": "X"})
    with pytest.raises(ValueError, match="bereits verbunden"):
        config.check_token("555:B")


def test_resync_skips_second_owner_of_same_bot(monkeypatch):
    # Общая строка бота видна из обеих схем — как дубль на проде.
    for schema in ("dupa", "dupb"):
        DomainFactory(tenant=TenantFactory(schema_name=schema))
    TelegramBot.objects.create(token="444:S", is_active=True)
    calls = []
    monkeypatch.setattr(services, "set_webhook", lambda *a: calls.append(a))
    out = StringIO()
    call_command("telegram_resync_webhooks", "--apply", stdout=out)
    assert len(calls) == 1
    assert "skip (same bot as dupa): dupb" in out.getvalue()
