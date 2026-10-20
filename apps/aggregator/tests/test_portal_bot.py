"""TG4: Telegram-бот портала — webhook /start → Mini App портала, connect."""

import pytest
from django.http import Http404
from django.test import RequestFactory

from apps.aggregator import telegram_bot
from apps.aggregator.models import AggregatorPortal, PortalBot
from apps.telegram import services

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _portal_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_portal"


def _portal(host="muenchen.siteadaptor.de"):
    return AggregatorPortal.objects.create(host=host, kind="city", city="München")


def test_webhook_unknown_secret_404():
    req = RequestFactory().post("/tg/nope/", data="{}", content_type="application/json")
    with pytest.raises(Http404):
        telegram_bot.webhook(req, secret="nope")


def test_connect_bot_sets_webhook(monkeypatch):
    bot = PortalBot.objects.create(portal=_portal(host="koeln.siteadaptor.de"), token="t")
    monkeypatch.setattr(services, "get_me", lambda token: {"username": "KoelnBot"})
    hooks = {}
    monkeypatch.setattr(services, "set_webhook", lambda token, url, secret: hooks.update(url=url))
    monkeypatch.setattr(services, "set_my_commands", lambda *a, **k: hooks.setdefault("cmd", 0))
    telegram_bot.connect_bot(bot)
    bot.refresh_from_db()
    assert bot.bot_username == "KoelnBot"
    assert bot.is_active is True
    assert hooks["url"] == f"https://koeln.siteadaptor.de/tg/{bot.webhook_secret}/"
