"""T-8.10h H-2: вебхук общего бота — секрет, дедуп, группы, приветствие, привязка."""

import json
from unittest import mock

import pytest
from django.test import RequestFactory

from apps.platform_bot import handler, links, webhook
from apps.platform_bot.models import OwnerTelegramLink
from apps.tenants.tests.factories import TenantFactory

# Настройки бота читаются из админки (секреты в БД) — БД нужна и вебхук-тестам.
pytestmark = pytest.mark.django_db

SECRET = "s" * 32
USER = 777000111222  # > 2**31


@pytest.fixture
def on(settings):
    settings.TELEGRAM_PLATFORM_BOT_ENABLED = True
    settings.TELEGRAM_PLATFORM_BOT_TOKEN = "123:abc"
    settings.TELEGRAM_PLATFORM_BOT_USERNAME = "PlattformBot"
    settings.TELEGRAM_PLATFORM_WEBHOOK_SECRET = SECRET
    return settings


def _post(body, header=SECRET):
    request = RequestFactory().post(
        "/tg/plattform/",
        data=json.dumps(body),
        content_type="application/json",
        HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=header,
    )
    return webhook.webhook(request)


def _private(text="/start", uid=USER, update_id=1):
    return {
        "update_id": update_id,
        "message": {
            "chat": {"id": uid, "type": "private"},
            "from": {"id": uid, "is_bot": False, "language_code": "de"},
            "text": text,
        },
    }


@pytest.mark.parametrize("header", ["", "y", "x" * 32, "ü" * 32])
def test_wrong_secret_is_404(on, header):
    from django.http import Http404

    with pytest.raises(Http404):
        _post(_private(), header=header)


def test_get_and_short_secret_are_404(on):
    from django.http import Http404

    with pytest.raises(Http404):
        webhook.webhook(RequestFactory().get("/tg/plattform/"))
    on.TELEGRAM_PLATFORM_WEBHOOK_SECRET = "short"
    with pytest.raises(Http404):
        _post(_private(), header="short")


def test_non_int_update_id_is_ignored(on):
    with mock.patch("apps.platform_bot.tasks.platform_bot_update.delay") as delay:
        assert _post({"update_id": {"x": 1}}).status_code == 200
    delay.assert_not_called()


def test_disabled_bot_is_404(on):
    from django.http import Http404

    on.TELEGRAM_PLATFORM_BOT_ENABLED = False
    with pytest.raises(Http404):
        _post(_private())


def test_update_is_queued_with_update_id_dedupe(on):
    with mock.patch("apps.platform_bot.tasks.platform_bot_update.delay") as delay:
        assert _post(_private(update_id=42)).status_code == 200
    assert delay.call_args.kwargs["dedupe_key"] == "tgplat:42"
    assert delay.call_args.kwargs["update"]["message"]["text"] == "/start"


def test_broker_down_asks_telegram_to_retry(on):
    with mock.patch(
        "apps.platform_bot.tasks.platform_bot_update.delay", side_effect=ConnectionError
    ):
        assert _post(_private()).status_code == 503


@pytest.fixture
def sent(on, monkeypatch):
    out = []
    monkeypatch.setattr(
        "apps.telegram.services.send_message",
        lambda token, chat, text, reply_markup=None: out.append((chat, text, reply_markup)),
    )
    return out


@pytest.mark.django_db
def test_start_without_business_gets_onboarding(sent):
    assert handler.handle(webhook.slim(_private())) == "onboarding"
    # H-5: первая кнопка — регистрация прямо в чате, вторая — веб-форма.
    rows = sent[-1][2]["inline_keyboard"]
    assert rows[0][0]["callback_data"] == "ps:go"
    assert rows[1][0]["url"].endswith("/aktion-starten/")


@pytest.mark.django_db
def test_group_is_left_and_not_answered(sent, monkeypatch):
    left = []
    monkeypatch.setattr("apps.telegram.services.leave_chat", lambda t, c: left.append(c))
    update = {
        "update_id": 3,
        "my_chat_member": {
            "chat": {"id": -100, "type": "supergroup"},
            "from": {"id": USER},
            "new_chat_member": {"status": "member"},
        },
    }
    assert handler.handle(webhook.slim(update)) == "left"
    assert left == [-100]
    group_msg = _private()
    group_msg["message"]["chat"] = {"id": -100, "type": "group"}
    assert handler.handle(webhook.slim(group_msg)) == "skip"
    assert sent == []


@pytest.mark.django_db
def test_spoofed_sender_in_foreign_chat_is_skipped(sent):
    msg = _private()
    msg["message"]["chat"]["id"] = 5
    assert handler.handle(webhook.slim(msg)) == "skip"


@pytest.mark.django_db
def test_bind_writes_both_sides_and_unbind_clears_them():
    tenant = TenantFactory()
    links.bind(USER, tenant)
    tenant.refresh_from_db()
    node = tenant.site_config["notify"]
    assert node["owner_chat_id"] == str(USER) and node["owner_bot"] == "platform"
    assert links.is_owner(USER, tenant)
    links.unbind(tenant)
    tenant.refresh_from_db()
    assert "owner_chat_id" not in tenant.site_config["notify"]
    assert not links.is_owner(USER, tenant)
    assert OwnerTelegramLink.objects.filter(tenant=tenant, is_active=True).count() == 0


@pytest.mark.django_db
def test_rebinding_to_other_chat_revokes_ownership():
    tenant = TenantFactory()
    links.bind(USER, tenant)
    links.bind(USER + 1, tenant)
    assert not links.is_owner(USER, tenant)
    assert links.is_owner(USER + 1, tenant)


@pytest.mark.django_db
def test_blocking_the_bot_stops_links(sent):
    tenant = TenantFactory()
    links.bind(USER, tenant)
    update = {
        "update_id": 9,
        "my_chat_member": {
            "chat": {"id": USER, "type": "private"},
            "from": {"id": USER},
            "new_chat_member": {"status": "kicked"},
        },
    }
    assert handler.handle(webhook.slim(update)) == "blocked"
    assert not links.is_owner(USER, tenant)


@pytest.mark.django_db
def test_returning_owner_is_greeted(sent):
    tenant = TenantFactory()
    links.bind(USER, tenant)
    # H-4: обычный текст привязанного владельца идёт в акции; приветствие — на /start.
    assert handler.handle(webhook.slim(_private("/start"))) == "welcome_back"


# --- правки ревью Django (2026-10-19) -------------------------------------------------


@pytest.mark.django_db
def test_unblocking_or_writing_again_restores_delivery(sent):
    tenant = TenantFactory()
    links.bind(USER, tenant)
    member = {
        "update_id": 10,
        "my_chat_member": {
            "chat": {"id": USER, "type": "private"},
            "from": {"id": USER},
            "new_chat_member": {"status": "kicked"},
        },
    }
    handler.handle(webhook.slim(member))
    member["my_chat_member"]["new_chat_member"]["status"] = "member"
    assert handler.handle(webhook.slim(member)) == "unblocked"
    assert links.is_owner(USER, tenant)
    member["my_chat_member"]["new_chat_member"]["status"] = "kicked"
    handler.handle(webhook.slim(member))
    # H-4: обычный текст привязанного владельца идёт в акции; приветствие — на /start.
    assert handler.handle(webhook.slim(_private("/start"))) == "welcome_back"
    assert links.is_owner(USER, tenant)


@pytest.mark.django_db
def test_unbind_keeps_owner_of_own_business_bot():
    """Отключение общего бота не трогает владельца, подключённого к своему боту."""
    tenant = TenantFactory()
    tenant.site_config = {"notify": {"owner_chat_id": "42", "owner_bot": "tenant"}}
    tenant.save()
    links.unbind(tenant)
    tenant.refresh_from_db()
    assert tenant.site_config["notify"] == {"owner_chat_id": "42", "owner_bot": "tenant"}


def test_malformed_nested_objects_do_not_crash_slim():
    bad = {"update_id": 1, "message": {"chat": "x", "from": 5, "photo": "y"}}
    out = webhook.slim(bad)["message"]
    assert out["chat_id"] is None and out["from_id"] is None and out["photo"] == ""
    webhook.slim({"update_id": 2, "callback_query": {"from": [], "message": {"chat": 1}}})
    webhook.slim({"update_id": 3, "my_chat_member": {"chat": 1, "new_chat_member": "z"}})


@pytest.mark.django_db
def test_handler_failure_releases_dedupe_lock(on, monkeypatch):
    from django.core.cache import cache

    from apps.platform_bot import tasks

    key = f"job_lock:{tasks.dedupe_key(55)}"
    cache.delete(key)
    monkeypatch.setattr(handler, "handle", mock.Mock(side_effect=RuntimeError("db")))
    with pytest.raises(RuntimeError):
        tasks.platform_bot_update(dedupe_key=tasks.dedupe_key(55), update={"update_id": 55})
    assert cache.get(key) is None  # повтор пройдёт мимо дедупа
