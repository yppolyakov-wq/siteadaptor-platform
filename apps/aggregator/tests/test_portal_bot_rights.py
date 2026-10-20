"""T-8.10h H-7i: права жителя в боте портала (Art. 15/16/18/20/21 DSGVO).

План — docs/t8-10h-h7-owner-bot-ux-plan-2026-10-20.md §2.
"""

import json

import pytest

from apps.aggregator import follow_digest, portal_bot
from apps.aggregator.models import FollowSubscription, PortalChat
from apps.aggregator.tests.test_portal_bot_v2 import (  # noqa: F401
    UID,
    _bot,
    _cb,
    _env,
    _listing,
    _msg,
    _tg_follower,
    sent,
)
from apps.telegram import services

pytestmark = pytest.mark.django_db


@pytest.fixture
def docs(monkeypatch):
    out = []
    monkeypatch.setattr(
        services,
        "send_document",
        lambda token, chat, name, content, caption="": out.append((chat, name, content)) or {},
    )
    return out


def test_export_lists_only_own_subscriptions(sent, docs):  # noqa: F811
    bot = _bot()
    _listing()
    _tg_follower(sent, bot)
    assert portal_bot.handle(bot.pk, _msg("/meine_daten")) == "exported"
    chat, name, content = docs[-1]
    data = json.loads(content)
    assert chat == UID and name == "meine-daten.json"
    assert data["telegram_user_id"] == UID and len(data["subscriptions"]) == 1


def test_export_without_data(sent, docs):  # noqa: F811
    bot = _bot()
    assert portal_bot.handle(bot.pk, _msg("/meine_daten")) == "nothing"
    assert not docs


def test_pause_silences_digest_keeps_subscriptions(sent):  # noqa: F811
    bot = _bot()
    _listing()
    user = _tg_follower(sent, bot)
    assert portal_bot.handle(bot.pk, _msg("/pausieren")) == "paused"
    assert FollowSubscription.objects.filter(user=user).exists()
    assert not follow_digest.daily_candidates().filter(pk=user.pk).exists()
    # сообщение жителя паузу не снимает (в отличие от blocked_at)
    portal_bot.handle(bot.pk, _msg("Brot"))
    assert PortalChat.objects.get().paused_at is not None
    assert portal_bot.handle(bot.pk, _msg("/fortsetzen")) == "resumed"
    assert follow_digest.daily_candidates().filter(pk=user.pk).exists()


def test_language_correction(sent):  # noqa: F811
    bot = _bot()
    _listing()
    _tg_follower(sent, bot)
    assert portal_bot.handle(bot.pk, _msg("/berichtigen")) == "correct_menu"
    assert portal_bot.handle(bot.pk, _cb("pl:ru")) == "locale_set"
    chat = PortalChat.objects.get()
    assert chat.locale == "ru" and chat.user.locale == "ru"
    assert portal_bot.handle(bot.pk, _cb("pl:xx")) == "skip"


def test_objection_ends_all_subscriptions(sent):  # noqa: F811
    bot = _bot()
    _listing()
    _tg_follower(sent, bot)
    assert portal_bot.handle(bot.pk, _msg("/widerspruch")) == "objection_asked"
    assert FollowSubscription.objects.exists()
    assert portal_bot.handle(bot.pk, _cb("wx")) == "objected"
    assert not FollowSubscription.objects.exists()


def test_rights_commands_listed():
    names = {c["command"] for c in portal_bot.commands()}
    assert {"meine_daten", "pausieren"} <= names


def test_first_contact_language_does_not_stick(sent):  # noqa: F811
    """Ревью H-7i: язык первого контакта не «залипает» — только явный выбор."""
    bot = _bot()
    _listing()
    _tg_follower(sent, bot)
    PortalChat.objects.update(locale="de")
    portal_bot.handle(bot.pk, _msg("/start", lang="en"))
    assert "Welcome" in sent[-1]["text"]
    portal_bot.handle(bot.pk, _cb("pl:ru"))
    portal_bot.handle(bot.pk, _msg("/start", lang="en"))
    assert "Добро" in sent[-1]["text"]


def test_objection_keeps_email_subscriptions(sent):  # noqa: F811
    bot = _bot()
    _listing()
    user = _tg_follower(sent, bot)
    FollowSubscription.objects.filter(user=user).update(channel="email")
    portal_bot.handle(bot.pk, _cb("wx"))
    assert FollowSubscription.objects.filter(user=user).exists()


def test_privacy_link_points_to_platform_page(sent):  # noqa: F811
    bot = _bot()
    portal_bot.handle(bot.pk, _msg("/datenschutz"))
    assert "/datenschutz/#telegram-portal" in sent[-1]["text"]
    assert bot.portal.host not in sent[-1]["text"]
