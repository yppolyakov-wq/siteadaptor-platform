"""NT-A4: бот портала — категории раздела ☐/✅, страницы списка, «Alle beenden».

Замки: переключатели ничего не пишут до согласия; сохранение меняет только категории ЭТОГО
раздела; согласие одноразовое; «Alle beenden» не трогает e-mail-подписки жителя; нажатия ≤ 64 байт.
"""

import uuid

import pytest
from django.utils import timezone

from apps.aggregator import portal_bot
from apps.aggregator.models import FollowSubscription, PortalChat
from apps.aggregator.tests.test_portal_bot_v2 import (
    UID,
    _bot,
    _buttons,
    _cb,
    _env,  # noqa: F401 — автофикстура
)
from apps.aggregator.tests.test_portal_bot_v2 import sent as sent  # noqa: F401, F811

pytestmark = pytest.mark.django_db
FOOD = "lebensmittel-getraenke"


def _open(sent, bot):
    assert portal_bot.handle(bot.pk, _cb(f"kc:{FOOD}")) == "categories"
    return _buttons(sent[-1])


def _press(bot, data, message_id=7):
    upd = _cb(data)
    upd["callback"]["message_id"] = message_id
    return portal_bot.handle(bot.pk, upd)


def test_toggles_write_nothing_until_consent(sent, monkeypatch):
    from apps.telegram import services

    edits = []
    monkeypatch.setattr(services, "edit_message_reply_markup", lambda *a, **k: edits.append(a))
    bot = _bot()
    buttons = _open(sent, bot)
    toggles = [b["callback_data"] for b in buttons if b["callback_data"].startswith("kt:")]
    assert all(len(d.encode()) <= 64 for d in toggles)
    assert _press(bot, toggles[0]) == "category_toggled" and edits
    assert _press(bot, toggles[1]) == "category_toggled"
    save = [b for b in _buttons({"markup": edits[-1][3]}) if b["callback_data"].startswith("ks:")]
    assert "(2)" in save[0]["text"]
    assert not FollowSubscription.objects.exists()
    assert portal_bot.handle(bot.pk, _cb(save[0]["callback_data"])) == "categories_asked"
    yes = [b for b in _buttons(sent[-1]) if b["callback_data"].startswith("fy:")][0]
    assert not FollowSubscription.objects.exists()
    assert portal_bot.handle(bot.pk, _cb(yes["callback_data"])) == "categories_saved"
    kinds = set(FollowSubscription.objects.values_list("target_kind", "channel"))
    assert kinds == {("category", "telegram")}
    assert FollowSubscription.objects.count() == 2
    assert portal_bot.handle(bot.pk, _cb(yes["callback_data"])) == "stale"  # одноразово


def test_save_changes_only_this_section(sent):
    bot = _bot()
    chat = portal_bot.chat_user(bot, UID)
    other = FollowSubscription.objects.create(
        user=chat.user,
        target_kind="category",
        target_key="mode-damen",
        city="Solingen",
        channel="telegram",
        portal=bot.portal,
        token=uuid.uuid4().hex,
        confirmed_at=timezone.now(),
    )
    buttons = _open(sent, bot)
    save = [b for b in buttons if b["callback_data"].startswith("ks:")][0]
    portal_bot.handle(bot.pk, _cb(save["callback_data"]))  # пустой выбор раздела
    yes = [b for b in _buttons(sent[-1]) if b["callback_data"].startswith("fy:")][0]
    portal_bot.handle(bot.pk, _cb(yes["callback_data"]))
    assert FollowSubscription.objects.filter(pk=other.pk).exists()


def test_alle_beenden_keeps_email_follows(sent):
    bot = _bot()
    chat = portal_bot.chat_user(bot, UID)
    for channel in ("telegram", "email"):
        FollowSubscription.objects.create(
            user=chat.user,
            target_kind="tag",
            target_key="vegan",
            city="Solingen",
            channel=channel,
            portal=bot.portal,
            token=uuid.uuid4().hex,
            confirmed_at=timezone.now(),
        )
    portal_bot.handle(bot.pk, _cb("ls"))
    assert any(b["callback_data"] == "wo" for b in _buttons(sent[-1]))
    assert portal_bot.handle(bot.pk, _cb("wo")) == "objection_asked"
    assert portal_bot.handle(bot.pk, _cb("wx")) == "objected"
    assert list(FollowSubscription.objects.values_list("channel", flat=True)) == ["email"]
    assert PortalChat.objects.filter(pk=chat.pk).exists()


def test_list_pages(sent):
    bot = _bot()
    chat = portal_bot.chat_user(bot, UID)
    for i in range(12):
        FollowSubscription.objects.create(
            user=chat.user,
            target_kind="brand",
            target_key=f"m{i}",
            city="Solingen",
            channel="telegram",
            portal=bot.portal,
            token=uuid.uuid4().hex,
            confirmed_at=timezone.now(),
        )
    portal_bot.handle(bot.pk, _cb("ls"))
    first = _buttons(sent[-1])
    assert sum(1 for b in first if b["callback_data"].startswith("u:")) == 10
    assert any(b["callback_data"] == "ls:1" for b in first)
    portal_bot.handle(bot.pk, _cb("ls:1"))
    assert sum(1 for b in _buttons(sent[-1]) if b["callback_data"].startswith("u:")) == 2
