"""T-8.10h H-1: вид бота (свой | платформы) — поведение своего бота прежнее."""

import pytest

from apps.promotions import tasks
from apps.promotions import telegram_promo as tp
from apps.promotions.tests.test_telegram_promo import OWNER, _msg, tg  # noqa: F401
from apps.telegram import bots

pytestmark = pytest.mark.django_db


def test_platform_bot_off_by_default(settings):
    settings.TELEGRAM_PLATFORM_BOT_ENABLED = False
    assert bots.platform_bot() is None
    assert bots.for_kind("platform") is None


def test_platform_bot_from_settings(settings):
    settings.TELEGRAM_PLATFORM_BOT_ENABLED = True
    settings.TELEGRAM_PLATFORM_BOT_TOKEN = "123:abc"
    settings.TELEGRAM_PLATFORM_BOT_USERNAME = "PlattformBot"
    bot = bots.for_kind("platform")
    assert bot == bots.BotRef("platform", "123:abc", "PlattformBot")


def test_unknown_kind_means_tenant_bot(tg):  # noqa: F811
    for kind in (None, "", "tenant", "junk"):
        assert bots.for_kind(kind).kind == "tenant"


def test_draft_remembers_its_bot(tg):  # noqa: F811
    slim = tp.slim_update(_msg("Brötchen −30 % heute"))
    assert tp._handle(tg["bot"], tg["tenant"], "public", str(OWNER), slim) == "preview"
    token = tg["sent"][-1]["markup"]["inline_keyboard"][0][0]["callback_data"].split(":")[2]
    assert tp.load_draft("public", str(OWNER), token)["bot"] == "tenant"


def test_tasks_accept_old_kwargs_without_bot_kind(monkeypatch):
    """Сообщения, уже лежащие в очереди до деплоя, не знают bot_kind."""
    seen = {}
    monkeypatch.setattr(
        tp, "handle_owner_message", lambda s, u, k="tenant": seen.setdefault("m", k)
    )
    monkeypatch.setattr(tp, "handle_confirm", lambda *a: seen.setdefault("c", a[-1]))
    tasks.telegram_owner_message.run(schema="s", update={})
    tasks.telegram_owner_confirm.run(schema="s", chat="1", token="t", message_id=1)
    assert seen == {"m": "tenant", "c": "tenant"}


def test_enqueue_passes_bot_kind(tg, monkeypatch):  # noqa: F811
    calls = []
    monkeypatch.setattr(
        "apps.promotions.tasks.telegram_owner_message.delay", lambda **kw: calls.append(kw)
    )
    tp.enqueue_owner_message(tg["bot"], _msg("Brot −10 %"), tg["tenant"])
    assert calls[0]["bot_kind"] == "tenant"
    platform = bots.BotRef("platform", "t", "P")
    tp.enqueue_owner_message(platform, _msg("Brot −10 %", update_id=2), tg["tenant"])
    assert calls[1]["bot_kind"] == "platform"
