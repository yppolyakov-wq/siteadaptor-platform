"""Тесты доп.адаптеров M23: Telegram-канал и Pinterest. HTTP застаблен."""

import pytest

from apps.promotions.models import Promotion
from apps.publishing import adapters
from apps.publishing.models import Channel, Publication

pytestmark = pytest.mark.django_db


class _Resp:
    def __init__(self, data=None, status=200):
        self._data = data or {}
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        return self._data


def _publication(type_, config=None, external_ref="", images=None):
    channel = Channel.objects.create(type=type_, is_enabled=True, config=config or {})
    promo = Promotion.objects.create(
        status="active",
        title={"de": "Brötchen -20%"},
        description={"de": "Nur heute"},
        images=images or [],
    )
    return Publication.objects.create(
        promotion=promo,
        channel=channel,
        external_ref=external_ref,
        dedupe_key=f"publish:{promo.id}:{channel.id}",
    )


# --- Telegram ----------------------------------------------------------------


def test_tg_publish_text_without_image(monkeypatch):
    pub = _publication("telegram", config={"bot_token": "tok", "chat_id": "@kanal"})
    calls = []

    def _post(url, **kw):
        calls.append((url, kw))
        return _Resp({"result": {"message_id": 42}})

    monkeypatch.setattr(adapters.requests, "post", _post)
    assert adapters.publish(pub) == "@kanal:42"
    assert calls[0][0].endswith("/bottok/sendMessage")
    assert "Brötchen" in calls[0][1]["data"]["text"]


def test_tg_publish_photo_when_image(monkeypatch):
    pub = _publication(
        "telegram",
        config={"bot_token": "tok", "chat_id": "@kanal"},
        images=[{"url": "https://cdn.example/x.jpg", "is_primary": True}],
    )
    calls = []
    monkeypatch.setattr(
        adapters.requests,
        "post",
        lambda url, **kw: calls.append((url, kw)) or _Resp({"result": {"message_id": 7}}),
    )
    assert adapters.publish(pub) == "@kanal:7"
    assert calls[0][0].endswith("/sendPhoto")
    assert calls[0][1]["data"]["photo"] == "https://cdn.example/x.jpg"


def test_tg_publish_without_config_raises():
    pub = _publication("telegram", config={})
    with pytest.raises(RuntimeError, match="nicht konfiguriert"):
        adapters.publish(pub)


def test_tg_remove_deletes_message(monkeypatch):
    pub = _publication(
        "telegram", config={"bot_token": "tok", "chat_id": "@kanal"}, external_ref="@kanal:42"
    )
    calls = []
    monkeypatch.setattr(
        adapters.requests, "post", lambda url, **kw: calls.append((url, kw)) or _Resp()
    )
    adapters.remove(pub)
    assert calls[0][0].endswith("/deleteMessage")
    assert calls[0][1]["data"]["message_id"] == "42"


def test_tg_remove_without_ref_is_noop(monkeypatch):
    pub = _publication("telegram", config={"bot_token": "tok"})

    def _boom(*a, **k):
        raise AssertionError("no API call without external_ref")

    monkeypatch.setattr(adapters.requests, "post", _boom)
    adapters.remove(pub)


# --- Pinterest ---------------------------------------------------------------


def test_pinterest_publish_creates_pin(monkeypatch):
    pub = _publication(
        "pinterest",
        config={"access_token": "tok", "board_id": "b1"},
        images=[{"url": "https://cdn.example/x.jpg", "is_primary": True}],
    )
    calls = []

    def _post(url, **kw):
        calls.append((url, kw))
        return _Resp({"id": "pin99"})

    monkeypatch.setattr(adapters.requests, "post", _post)
    assert adapters.publish(pub) == "pin99"
    assert calls[0][0].endswith("/pins")
    body = calls[0][1]["json"]
    assert body["board_id"] == "b1"
    assert body["media_source"]["url"] == "https://cdn.example/x.jpg"
    assert calls[0][1]["headers"]["Authorization"] == "Bearer tok"


def test_pinterest_publish_without_image_raises():
    pub = _publication("pinterest", config={"access_token": "tok", "board_id": "b1"})
    with pytest.raises(RuntimeError, match="Bild"):
        adapters.publish(pub)


def test_pinterest_remove_deletes_pin(monkeypatch):
    pub = _publication(
        "pinterest", config={"access_token": "tok", "board_id": "b1"}, external_ref="pin99"
    )
    deleted = []
    monkeypatch.setattr(
        adapters.requests, "delete", lambda url, **kw: deleted.append(url) or _Resp()
    )
    adapters.remove(pub)
    assert deleted and deleted[0].endswith("/pins/pin99")
