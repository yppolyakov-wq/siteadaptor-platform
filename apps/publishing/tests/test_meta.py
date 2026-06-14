"""Тесты соц-адаптеров Meta (Facebook/Instagram, M23a). Как и GBP, внешние
вызовы Graph API застаблены — реальные токены не нужны (настройка —
docs/meta-social-setup.md)."""

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


# --- Facebook ----------------------------------------------------------------


def test_fb_publish_without_image_posts_to_feed(monkeypatch):
    pub = _publication("facebook", config={"page_id": "111", "access_token": "tok"})
    calls = []

    def _post(url, **kw):
        calls.append((url, kw))
        return _Resp({"id": "111_222"})

    monkeypatch.setattr(adapters.requests, "post", _post)

    assert adapters.publish(pub) == "111_222"
    url, kw = calls[0]
    assert url.endswith("/111/feed")
    assert "Brötchen" in kw["data"]["message"]
    assert "Nur heute" in kw["data"]["message"]
    assert kw["data"]["access_token"] == "tok"


def test_fb_publish_with_image_posts_photo(monkeypatch):
    pub = _publication(
        "facebook",
        config={"page_id": "111", "access_token": "tok"},
        images=[{"url": "https://cdn.example/x.jpg", "is_primary": True}],
    )
    calls = []

    def _post(url, **kw):
        calls.append((url, kw))
        return _Resp({"id": "media1", "post_id": "111_333"})

    monkeypatch.setattr(adapters.requests, "post", _post)

    # post_id (не id контейнера фото) — это идентификатор поста для удаления
    assert adapters.publish(pub) == "111_333"
    url, kw = calls[0]
    assert url.endswith("/111/photos")
    assert kw["data"]["url"] == "https://cdn.example/x.jpg"
    assert "Brötchen" in kw["data"]["caption"]


def test_fb_publish_without_config_raises():
    pub = _publication("facebook", config={})
    with pytest.raises(RuntimeError, match="nicht konfiguriert"):
        adapters.publish(pub)


def test_fb_remove_deletes_post(monkeypatch):
    pub = _publication(
        "facebook", config={"page_id": "111", "access_token": "tok"}, external_ref="111_222"
    )
    deleted = []

    def _delete(url, **kw):
        deleted.append((url, kw))
        return _Resp()

    monkeypatch.setattr(adapters.requests, "delete", _delete)
    adapters.remove(pub)
    assert deleted and deleted[0][0].endswith("/111_222")
    assert deleted[0][1]["params"]["access_token"] == "tok"


def test_fb_remove_without_post_is_noop(monkeypatch):
    pub = _publication("facebook", config={"access_token": "tok"})  # external_ref пуст

    def _boom(*args, **kw):
        raise AssertionError("API must not be called without external_ref")

    monkeypatch.setattr(adapters.requests, "delete", _boom)
    adapters.remove(pub)


# --- Instagram ---------------------------------------------------------------


def test_ig_publish_creates_container_then_publishes(monkeypatch):
    pub = _publication(
        "instagram",
        config={"ig_user_id": "999", "access_token": "tok"},
        images=[{"url": "https://cdn.example/x.jpg", "is_primary": True}],
    )
    calls = []

    def _post(url, **kw):
        calls.append((url, kw))
        if url.endswith("/999/media"):
            return _Resp({"id": "creation42"})
        return _Resp({"id": "ig_media_77"})

    monkeypatch.setattr(adapters.requests, "post", _post)

    assert adapters.publish(pub) == "ig_media_77"
    assert calls[0][0].endswith("/999/media")
    assert calls[0][1]["data"]["image_url"] == "https://cdn.example/x.jpg"
    assert calls[1][0].endswith("/999/media_publish")
    assert calls[1][1]["data"]["creation_id"] == "creation42"


def test_ig_publish_without_image_raises():
    pub = _publication("instagram", config={"ig_user_id": "999", "access_token": "tok"})
    with pytest.raises(RuntimeError, match="Bild"):
        adapters.publish(pub)


def test_ig_publish_without_config_raises():
    pub = _publication("instagram", config={})
    with pytest.raises(RuntimeError, match="nicht konfiguriert"):
        adapters.publish(pub)


def test_ig_remove_is_noop(monkeypatch):
    pub = _publication("instagram", config={"ig_user_id": "999", "access_token": "tok"})

    def _boom(*args, **kw):
        raise AssertionError("Graph API can't delete organic IG posts")

    monkeypatch.setattr(adapters.requests, "delete", _boom)
    monkeypatch.setattr(adapters.requests, "post", _boom)
    adapters.remove(pub)  # без вызовов API
