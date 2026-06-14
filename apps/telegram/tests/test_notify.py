"""TG3: привязка Customer↔chat_id (deep-link) и доставка уведомлений в Telegram."""

import pytest

from apps.notifications.models import Notification
from apps.promotions.models import Customer
from apps.telegram import notify, services
from apps.telegram import webhook as wh
from apps.telegram.models import TelegramBot, TelegramLink

pytestmark = pytest.mark.django_db


def _bot(active=True, username="MyShopBot"):
    return TelegramBot.objects.create(token="t", bot_username=username, is_active=active)


def _customer(email="k@test.de"):
    return Customer.objects.create(name="K", email=email)


# --- deep-link + привязка ----------------------------------------------------------


def test_deep_link_empty_without_bot():
    assert notify.deep_link(_customer()) == ""


def test_deep_link_and_link_from_start():
    _bot()
    customer = _customer()
    url = notify.deep_link(customer)
    assert url.startswith("https://t.me/MyShopBot?start=")
    token = url.rsplit("=", 1)[1]
    # /start <token> привязывает chat_id
    assert notify.link_from_start(token, 555) is True
    link = TelegramLink.objects.get(customer=customer)
    assert link.chat_id == "555" and link.is_linked
    # неизвестный токен — мимо
    assert notify.link_from_start("nope", 1) is False


def test_webhook_start_with_token_links(monkeypatch):
    _bot()
    customer = _customer()
    token = notify.deep_link(customer).rsplit("=", 1)[1]
    sent = {}
    monkeypatch.setattr(
        services, "send_message", lambda tok, chat, text, reply_markup=None: sent.update(text=text)
    )
    req = type("R", (), {"build_absolute_uri": lambda self, u: "https://shop.test/"})()
    wh.handle_update(
        TelegramBot.objects.first(),
        {"message": {"chat": {"id": 777}, "text": f"/start {token}"}},
        req,
    )
    assert TelegramLink.objects.get(customer=customer).chat_id == "777"
    assert "Connected" in sent["text"] or "✅" in sent["text"]


# --- доставка уведомления ----------------------------------------------------------


def test_send_to_customer_creates_telegram_notification():
    _bot()
    customer = _customer()
    TelegramLink.objects.create(customer=customer, link_token="tok123", chat_id="999")
    notify.send_to_customer(
        customer, type="order_ready", dedupe_key="order:1:ready:tg", text="Bereit!"
    )
    n = Notification.objects.get(dedupe_key="order:1:ready:tg")
    assert n.channel == Notification.TELEGRAM
    assert n.recipient == "999"
    assert n.payload["body"] == "Bereit!"


def test_send_to_customer_skips_when_not_linked():
    _bot()
    customer = _customer()  # без TelegramLink
    notify.send_to_customer(customer, type="order_ready", dedupe_key="order:2:ready:tg", text="x")
    assert not Notification.objects.filter(dedupe_key="order:2:ready:tg").exists()


def test_send_to_customer_skips_without_active_bot():
    _bot(active=False)
    customer = _customer()
    TelegramLink.objects.create(customer=customer, link_token="t2", chat_id="1")
    notify.send_to_customer(customer, type="order_ready", dedupe_key="order:3:ready:tg", text="x")
    assert not Notification.objects.filter(dedupe_key="order:3:ready:tg").exists()


# --- адаптер доставки --------------------------------------------------------------


def test_telegram_adapter_sends_via_bot(monkeypatch):
    _bot()
    from apps.notifications import adapters

    n = Notification(channel=Notification.TELEGRAM, recipient="42", payload={"body": "Hallo"})
    calls = {}
    monkeypatch.setattr(
        services,
        "send_message",
        lambda token, chat_id, text, **k: calls.update(chat=chat_id, text=text),
    )
    adapters.send(n)
    assert calls == {"chat": "42", "text": "Hallo"}
