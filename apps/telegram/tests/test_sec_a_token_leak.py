"""SEC-A1 (аудит безопасности 2026-11-01): токен бота не покидает `apps.telegram.services`.

Текст `requests.HTTPError` несёт URL `https://api.telegram.org/bot<TOKEN>/…`. Раньше три
приёмника писали его как есть: `logger.exception` в вебхуке бота бизнеса и в мосте группы
поездки, `Notification.last_error` в задаче доставки. Замки класса: исключение сервиса
без токена и без цепочки; Sentry вырезает токен из текста исключений и логов; в модулях с
вызовами Telegram нет `logger.exception`.
"""

import json
import logging
import re
from pathlib import Path

import pytest
import requests
from django.http import Http404
from django.test import RequestFactory

from apps.telegram import public_views, services
from apps.telegram.models import TelegramBot
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db
TOKEN = "123456:ABC-DEF_ghi"
ROOT = Path(__file__).resolve().parents[3]


class _Resp:
    def __init__(self, status):
        self.status_code = status
        self.url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} for url {self.url}", response=self)

    def json(self):
        return {"result": {}}


def test_service_error_has_no_token_and_no_chain(monkeypatch):
    monkeypatch.setattr(services.requests, "post", lambda *a, **k: _Resp(403))
    with pytest.raises(requests.RequestException) as info:
        services.send_message(TOKEN, 1, "x")
    exc = info.value
    assert TOKEN not in str(exc) and TOKEN not in repr(exc)
    assert exc.__cause__ is None and exc.__context__ is None
    assert getattr(exc, "status", None) == 403
    assert getattr(getattr(exc, "response", None), "status_code", None) == 403


def test_connection_error_is_sanitized_too(monkeypatch):
    def boom(url, **k):
        raise requests.ConnectionError(f"failed {url}")

    monkeypatch.setattr(services.requests, "post", boom)
    with pytest.raises(requests.RequestException) as info:
        services.send_message(TOKEN, 1, "x")
    assert TOKEN not in str(info.value) and info.value.__cause__ is None


def test_scrub_masks_token_in_text():
    text = f"GET https://api.telegram.org/bot{TOKEN}/getMe failed"
    assert TOKEN not in services.scrub(text)
    assert "api.telegram.org" in services.scrub(text)


def _webhook_request(bot, body, header=None):
    req = RequestFactory().post(
        f"/tg/{bot.webhook_secret}/", data=body, content_type="application/json"
    )
    req.tenant = TenantFactory.build()
    req.META["HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN"] = (
        bot.webhook_secret if header is None else header
    )
    return req


def test_tenant_webhook_log_has_no_token(monkeypatch, caplog, settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    bot = TelegramBot.objects.create(token=TOKEN, is_active=True)

    def boom(*a, **k):
        raise requests.HTTPError(f"403 for url https://api.telegram.org/bot{TOKEN}/sendMessage")

    monkeypatch.setattr(public_views, "handle_update", boom)
    body = json.dumps({"update_id": 1, "message": {"chat": {"id": 5}, "text": "hi"}})
    with caplog.at_level(logging.WARNING):
        resp = public_views.webhook(_webhook_request(bot, body), secret=bot.webhook_secret)
    assert resp.status_code == 200
    assert TOKEN not in caplog.text
    assert caplog.text  # сбой всё же записан (тип ошибки)


def test_tenant_webhook_non_ascii_header_is_404_not_500(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    bot = TelegramBot.objects.create(token=TOKEN, is_active=True)
    with pytest.raises(Http404):
        public_views.webhook(
            _webhook_request(bot, "{}", header="секрет"), secret=bot.webhook_secret
        )


def test_tenant_webhook_repeated_update_id_handled_once(monkeypatch, settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    bot = TelegramBot.objects.create(token=TOKEN, is_active=True)
    calls = []
    monkeypatch.setattr(public_views, "handle_update", lambda b, u, r: calls.append(u))
    body = json.dumps({"update_id": 777, "message": {"chat": {"id": 5}, "text": "hi"}})
    for _ in range(2):
        public_views.webhook(_webhook_request(bot, body), secret=bot.webhook_secret)
    assert len(calls) == 1


def test_bridge_push_log_has_no_token(monkeypatch, caplog):
    from types import SimpleNamespace

    from apps.community import telegram_bridge

    monkeypatch.setattr(
        "apps.telegram.notify.active_bot", lambda: SimpleNamespace(token=TOKEN, bot_username="b")
    )

    def boom(*a, **k):
        raise requests.HTTPError(f"403 for url https://api.telegram.org/bot{TOKEN}/sendMessage")

    monkeypatch.setattr("apps.telegram.services.send_message", boom)
    post = SimpleNamespace(
        pk=1,
        author_label="A",
        body="b",
        source="web",
        space=SimpleNamespace(tg_chat_id="9", is_open=True),
    )
    with caplog.at_level(logging.WARNING):
        assert telegram_bridge.push_to_group(post) is False
    assert TOKEN not in caplog.text


def test_notification_last_error_has_no_token(monkeypatch):
    from apps.notifications import adapters, tasks
    from apps.notifications.models import Notification

    n = Notification.objects.create(
        dedupe_key="sec-a1", type="x", recipient="5", channel=Notification.TELEGRAM, payload={}
    )

    def boom(notification):
        raise requests.HTTPError(f"403 for url https://api.telegram.org/bot{TOKEN}/sendMessage")

    monkeypatch.setattr(adapters, "send", boom)
    tasks.deliver.run(notification_id=n.pk) if hasattr(tasks.deliver, "run") else tasks.deliver(
        notification_id=n.pk
    )
    n.refresh_from_db()
    assert TOKEN not in (n.last_error or "")


def test_sentry_before_send_scrubs_tokens_and_task_kwargs():
    from config.settings import production

    event = {
        "exception": {"values": [{"value": f"403 for url https://api.telegram.org/bot{TOKEN}/x"}]},
        "logentry": {"message": f"bot{TOKEN} failed", "formatted": f"bot{TOKEN} failed"},
        "breadcrumbs": {"values": [{"message": f"url bot{TOKEN}"}]},
        "extra": {"celery-job": {"task_name": "t", "args": ["x"], "kwargs": {"email": "a@b.de"}}},
        "request": {"url": "https://example.test/x", "headers": {}},
    }
    out = production._sentry_before_send(event, {})
    dumped = json.dumps(out)
    assert TOKEN not in dumped
    assert "a@b.de" not in dumped


TELEGRAM_CALLERS = [
    "apps/telegram/public_views.py",
    "apps/telegram/webhook.py",
    "apps/telegram/notify.py",
    "apps/community/telegram_bridge.py",
    "apps/notifications/adapters.py",
    "apps/notifications/tasks.py",
    "apps/platform_bot/handler.py",
    "apps/platform_bot/tasks.py",
    "apps/aggregator/telegram_bot.py",
    "apps/aggregator/portal_bot.py",
    "apps/aggregator/follow_digest.py",
    "apps/promotions/telegram_promo.py",
    "apps/promotions/telegram_actions.py",
]


@pytest.mark.parametrize("rel", TELEGRAM_CALLERS)
def test_no_logger_exception_near_telegram_calls(rel):
    """`logger.exception` пишет трейсбэк и текст исключения — с токеном бота внутри."""
    src = (ROOT / rel).read_text(encoding="utf-8")
    assert not re.search(r"logger\.exception\(", src), rel
