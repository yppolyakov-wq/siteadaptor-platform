"""T-8.10h H-7i: права субъекта данных в общем боте (Art. 15/16/18/20/21 DSGVO).

План — docs/t8-10h-h7-owner-bot-ux-plan-2026-10-20.md §2.
"""

import json

import pytest

from apps.platform_bot import handler, links, privacy, rights
from apps.platform_bot.models import OwnerBotPrefs
from apps.platform_bot.tests.test_h5b_second_business_email import (  # noqa: F401
    USER,
    _cb,
    _msg,
    bot,
)
from apps.platform_bot.tests.test_h7_menu import _owner

pytestmark = pytest.mark.django_db


@pytest.fixture
def docs(monkeypatch):
    sent = []
    monkeypatch.setattr(
        "apps.telegram.services.send_document",
        lambda token, chat, name, content, caption="": sent.append((chat, name, content)) or {},
    )
    return sent


def test_export_contains_only_own_data(bot, docs):  # noqa: F811
    tenant = _owner()
    other = _owner_other()
    assert handler.handle(_msg("/meine_daten")) == "exported"
    chat, name, content = docs[-1]
    data = json.loads(content)
    assert chat == USER and name == "meine-daten.json"
    assert data["telegram_user_id"] == USER
    assert [b["name"] for b in data["businesses"]] == [tenant.name]
    assert other.name not in content.decode()


def _owner_other():
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(schema_name="fremd1", slug="fremd-1", name="Fremder Laden")
    links.bind(777000111, tenant)
    return tenant


def test_export_rate_limited(bot, docs):  # noqa: F811
    for _i in range(rights.EXPORT_LIMIT):
        assert handler.handle(_msg("/meine_daten")) == "exported"
    assert handler.handle(_msg("/meine_daten")) == "limited"


def test_restriction_survives_messages_and_blocks_processing(bot):  # noqa: F811
    _owner()
    assert handler.handle(_msg("/einschraenken")) == "restricted"
    # обычное сообщение (текст акции) — не обрабатывается; пометка блокировки бота её не снимает
    assert handler.handle(_msg("Brötchen 2,50 € heute bis 18 Uhr", update_id=2)) == "restricted"
    assert handler.handle(_msg("/hilfe", update_id=3)) == "restricted"
    assert handler.handle(_cb("pm:k")) == "restricted"
    assert rights.is_restricted(USER)
    # права и удаление работают и при ограничении
    assert handler.handle(_msg("/datenschutz", update_id=4)) == "privacy_info"
    assert handler.handle(_msg("/freigeben", update_id=5)) == "released"
    assert handler.handle(_msg("/hilfe", update_id=6)) == "help"


def test_restricted_owner_gets_no_platform_notifications(bot):  # noqa: F811
    from types import SimpleNamespace

    from apps.notifications import adapters

    _owner()  # схема бизнеса — public (как у текущего соединения теста)
    rights._set(USER, restricted_at=_now())
    note = SimpleNamespace(recipient=str(USER), payload={"bot": "platform", "body": "Neu"})
    with pytest.raises(RuntimeError, match="eingeschränkt"):
        adapters._send_platform(note)


def _now():
    from django.utils import timezone

    return timezone.now()


def test_language_correction(bot):  # noqa: F811
    _owner()
    assert handler.handle(_msg("/berichtigen")) == "correct_menu"
    assert handler.handle(_cb("pr:l:ru")) == "locale_set"
    assert rights.preferred_locale(USER) == "ru"
    assert handler.handle(_cb("pr:l:xx")) == "skip"


def test_unlink_wrong_business_only_own(bot):  # noqa: F811
    tenant = _owner()
    link = links.active_links(USER).first()
    foreign = _owner_other()
    foreign_link = links.OwnerTelegramLink.objects.get(tenant=foreign)
    assert handler.handle(_cb(f"pr:U:{foreign_link.pk}")) == "denied"
    assert links.is_owner(777000111, foreign)
    assert handler.handle(_cb(f"pr:u:{link.pk}")) == "unlink_asked"
    assert links.is_owner(USER, tenant)
    assert handler.handle(_cb(f"pr:U:{link.pk}")) == "unlinked"
    assert not links.is_owner(USER, tenant)


def test_objection_toggles_and_ai_fill_respects_it(bot, monkeypatch):  # noqa: F811
    _owner()
    assert handler.handle(_msg("/widerspruch")) == "objection_menu"
    handler.handle(_cb("pr:o:ai"))
    assert rights.ai_objected(USER)
    from apps.promotions import telegram_promo

    monkeypatch.setattr("apps.ai.api.is_enabled", lambda *a, **k: True)
    assert telegram_promo.ai_fill(None, None, {}, "P1", chat=str(USER)) is False
    handler.handle(_cb("pr:o:ai"))
    assert not rights.ai_objected(USER)


def test_reminder_objection_silences_pending_reminder(bot, monkeypatch):  # noqa: F811
    from apps.platform_bot import signup

    rights._set(USER, reminders_objected_at=_now())
    monkeypatch.setattr(links, "pending_for", lambda uid: 1 / 0)
    assert signup.remind_pending(None, USER, USER) == ""


def test_erase_deletes_prefs(bot):  # noqa: F811
    _owner()
    rights._set(USER, locale="en")
    privacy.erase(bot_obj(), USER, USER)
    assert not OwnerBotPrefs.objects.filter(tg_user_id=USER).exists()


def bot_obj():
    from apps.telegram import bots

    return bots.platform_bot()


def test_foreign_chat_callbacks_skip(bot):  # noqa: F811
    from apps.platform_bot import webhook

    upd = webhook.slim(
        {
            "update_id": 99,
            "callback_query": {
                "id": "c",
                "from": {"id": USER},
                "message": {"chat": {"id": 1234}, "message_id": 1},
                "data": "pr:o:ai",
            },
        }
    )
    assert handler.handle(upd) == "skip"
    assert not rights.ai_objected(USER)


def test_restricted_background_messages_are_silent(bot):  # noqa: F811
    """Ревью H-7i: фон (итог регистрации, ✅ из Celery) ограничившему — не уходит."""
    rights._set(USER, restricted_at=_now())
    assert handler.send(bot_obj(), USER, "Hintergrund") is False
    with rights.inbound():
        assert handler.send(bot_obj(), USER, "Antwort") is True


def test_restricted_message_does_not_touch_links(bot):  # noqa: F811
    from django.utils import timezone

    _owner()
    links.OwnerTelegramLink.objects.filter(tg_user_id=USER).update(blocked_at=timezone.now())
    rights._set(USER, restricted_at=_now())
    handler.handle(_msg("hallo", update_id=8))
    assert links.OwnerTelegramLink.objects.filter(
        tg_user_id=USER, blocked_at__isnull=False
    ).exists()


@pytest.mark.parametrize("data", ["ps:go", "pm:k", "g:00000000-0000-0000-0000-000000000000"])
def test_restricted_callbacks_ignored(bot, data):  # noqa: F811
    rights._set(USER, restricted_at=_now())
    assert handler.handle(_cb(data)) == "restricted"


def test_chosen_language_applies_to_all_callbacks(bot):  # noqa: F811
    _owner()
    rights._set(USER, locale="ru")
    handler.handle(_cb("pm:h"))
    assert "Как работать" in bot["sent"][-1]["text"]
