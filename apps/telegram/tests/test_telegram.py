"""M23/TG1: Telegram-бот — webhook-обработчик, публичный endpoint, кабинет.

Внешние вызовы Bot API застаблены (реальный токен не нужен)."""

import json

import pytest
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory

from apps.telegram import public_views, services, views
from apps.telegram import webhook as wh
from apps.telegram.models import TelegramBot
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


class _User:
    is_authenticated = True
    is_active = True


def _request(method, path, *, body=None, data=None, user=False):
    rf = getattr(RequestFactory(), method)
    if body is not None:
        request = rf(path, data=body, content_type="application/json")
    else:
        request = rf(path, data or {})
    request.tenant = TenantFactory.build()
    if user:
        SessionMiddleware(lambda r: None).process_request(request)
        MessageMiddleware(lambda r: None).process_request(request)
        request.user = _User()
    return request


# --- обработчик апдейтов ----------------------------------------------------------


def test_handle_start_sends_webapp_button(monkeypatch):
    bot = TelegramBot(token="t", webhook_secret="s", is_active=True)
    sent = {}
    monkeypatch.setattr(
        services,
        "send_message",
        lambda token, chat_id, text, reply_markup=None: sent.update(
            chat_id=chat_id, markup=reply_markup
        ),
    )
    req = _request("post", "/tg/s/")
    result = wh.handle_update(bot, {"message": {"chat": {"id": 99}, "text": "/start"}}, req)
    assert result == "sent"
    assert sent["chat_id"] == 99
    # кнопка открывает витрину как Telegram Web App
    button = sent["markup"]["inline_keyboard"][0][0]
    assert "web_app" in button and button["web_app"]["url"].startswith("http")


def test_handle_update_without_chat_is_skip(monkeypatch):
    monkeypatch.setattr(
        services, "send_message", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no send"))
    )
    bot = TelegramBot(token="t", webhook_secret="s")
    assert wh.handle_update(bot, {"edited_message": {}}, _request("post", "/tg/s/")) == "skip"


# --- публичный webhook ------------------------------------------------------------


def test_webhook_unknown_secret_404():
    req = _request("post", "/tg/nope/", body="{}")
    with pytest.raises(Http404):
        public_views.webhook(req, secret="nope")


def test_webhook_valid_calls_handler(monkeypatch):
    bot = TelegramBot.objects.create(token="t", is_active=True)
    called = {}
    monkeypatch.setattr(public_views, "handle_update", lambda b, u, r: called.update(ok=True))
    body = json.dumps({"message": {"chat": {"id": 5}, "text": "/start"}})
    req = _request("post", f"/tg/{bot.webhook_secret}/", body=body)
    req.META["HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN"] = bot.webhook_secret
    resp = public_views.webhook(req, secret=bot.webhook_secret)
    assert resp.status_code == 200
    assert called.get("ok") is True


def test_webhook_missing_secret_header_404():
    # без заголовка X-Telegram-Bot-Api-Secret-Token — 404 (обход пустым заголовком закрыт)
    bot = TelegramBot.objects.create(token="t", is_active=True)
    req = _request("post", f"/tg/{bot.webhook_secret}/", body="{}")
    with pytest.raises(Http404):
        public_views.webhook(req, secret=bot.webhook_secret)


def test_webhook_inactive_bot_404():
    bot = TelegramBot.objects.create(token="t", is_active=False)
    req = _request("post", f"/tg/{bot.webhook_secret}/", body="{}")
    with pytest.raises(Http404):
        public_views.webhook(req, secret=bot.webhook_secret)


# --- кабинет: подключение ---------------------------------------------------------


def test_connect_validates_token_and_sets_webhook(monkeypatch):
    monkeypatch.setattr(services, "get_me", lambda token: {"username": "MyShopBot"})
    monkeypatch.setattr(services, "tenant_base_url", lambda: "https://shop.test")
    hooks = {}
    monkeypatch.setattr(
        services, "set_webhook", lambda token, url, secret: hooks.update(url=url, secret=secret)
    )
    req = _request("post", "/dashboard/telegram/connect/", data={"token": "123:ABC"}, user=True)
    views.connect(req)
    bot = TelegramBot.objects.first()
    assert bot.bot_username == "MyShopBot"
    assert bot.is_active is True
    assert hooks["url"].endswith(f"/tg/{bot.webhook_secret}/")


def test_connect_blank_token_noop(monkeypatch):
    req = _request("post", "/dashboard/telegram/connect/", data={"token": "  "}, user=True)
    views.connect(req)
    assert not TelegramBot.objects.exclude(token="").exists()
