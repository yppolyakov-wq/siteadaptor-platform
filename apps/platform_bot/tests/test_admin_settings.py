"""T-8.10h: экран «Plattform-Bot» в админке платформы (только суперпользователь)."""

from unittest import mock

import pytest
from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory

from apps.platform_bot import config
from apps.platform_bot.admin import OwnerTelegramLinkAdmin
from apps.platform_bot.models import OwnerTelegramLink
from apps.secrets.models import PlatformSecret
from apps.telegram import bots

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _public(settings):
    settings.ROOT_URLCONF = "config.urls_public"
    settings.TELEGRAM_PLATFORM_BOT_ENABLED = False
    settings.TELEGRAM_PLATFORM_BOT_TOKEN = ""
    settings.TELEGRAM_PLATFORM_BOT_USERNAME = ""
    settings.TELEGRAM_PLATFORM_WEBHOOK_SECRET = ""


def _admin():
    return OwnerTelegramLinkAdmin(OwnerTelegramLink, site)


def _req(method="get", data=None, superuser=True):
    user = get_user_model().objects.create_user(
        username=f"adm-{superuser}-{method}", password="pw12345678", is_staff=True
    )
    user.is_superuser = superuser
    user.save()
    req = getattr(RequestFactory(), method)(
        "/admin/platform_bot/ownertelegramlink/einstellungen/", data or {}
    )
    SessionMiddleware(lambda r: None).process_request(req)
    req._messages = FallbackStorage(req)
    req.user = user
    req._dont_enforce_csrf_checks = True
    return req


def test_env_still_works_without_admin_values(settings):
    settings.TELEGRAM_PLATFORM_BOT_ENABLED = True
    settings.TELEGRAM_PLATFORM_BOT_TOKEN = "1:env"
    settings.TELEGRAM_PLATFORM_BOT_USERNAME = "@EnvBot"
    bot = bots.platform_bot()
    assert bot.token == "1:env" and bot.username == "EnvBot"


def test_admin_values_override_env_and_are_encrypted(settings):
    settings.TELEGRAM_PLATFORM_BOT_ENABLED = True
    settings.TELEGRAM_PLATFORM_BOT_TOKEN = "1:env"
    config.set_token("2:admin")
    config.set_enabled(False)
    assert bots.platform_bot() is None  # «выключить» в админке сильнее .env
    config.set_enabled(True)
    assert bots.platform_bot().token == "2:admin"
    row = PlatformSecret.objects.get(key=config.KEY_TOKEN)
    assert "2:admin" not in row.value_encrypted


def test_screen_is_superuser_only():
    with pytest.raises(PermissionDenied):
        _admin().settings_view(_req(superuser=False))
    resp = _admin().settings_view(_req())
    resp.render()
    html = resp.content.decode()
    assert "data-platform-bot-settings" in html and "Webhook setzen" in html


def test_save_checks_token_and_takes_bot_name():
    with mock.patch(
        "apps.telegram.services.get_me", return_value={"is_bot": True, "username": "SolBot"}
    ):
        _admin().settings_view(_req("post", {"action": "save", "token": "3:new", "enabled": "on"}))
    assert config.token() == "3:new" and config.username() == "SolBot" and config.enabled()


def test_bad_token_is_not_saved_and_not_echoed():
    with mock.patch(
        "apps.telegram.services.get_me", side_effect=RuntimeError("https://x/bot3:bad/getMe")
    ):
        req = _req("post", {"action": "save", "token": "3:bad", "enabled": "on"})
        _admin().settings_view(req)
    assert config.token() == ""
    assert all("3:bad" not in str(m) for m in req._messages)


def test_empty_token_field_keeps_current_token():
    config.set_token("4:keep")
    _admin().settings_view(_req("post", {"action": "save", "token": "", "enabled": "on"}))
    assert config.token() == "4:keep" and config.enabled()


def test_set_webhook_generates_secret_and_uses_it_in_view():
    config.set_token("5:t")
    with mock.patch("apps.telegram.services.set_webhook") as setter:
        _admin().settings_view(_req("post", {"action": "webhook"}))
    url, secret = setter.call_args.args[1], setter.call_args.args[2]
    assert url.endswith("/tg/plattform/") and len(secret) >= 24
    assert config.webhook_secret() == secret


def test_webhook_marks_last_update(settings):
    import json

    from apps.platform_bot import webhook

    config.set_enabled(True)
    config.set_token("6:t")
    secret = config.ensure_secret()
    req = RequestFactory().post(
        "/tg/plattform/",
        data=json.dumps({"update_id": 1}),
        content_type="application/json",
        HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=secret,
    )
    with mock.patch("apps.platform_bot.tasks.platform_bot_update.delay"):
        assert webhook.webhook(req).status_code == 200
    assert config.last_update()
