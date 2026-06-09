"""Тесты адаптера Google Business Profile (Track B1). Stripe-паттерн: внешние
вызовы застаблены, реальные ключи не нужны (настройка — docs/gbp-setup.md)."""

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


def _publication(config=None, external_ref=""):
    channel = Channel.objects.create(type="google_business", is_enabled=True, config=config or {})
    promo = Promotion.objects.create(
        status="active", title={"de": "Brötchen -20%"}, description={"de": "Nur heute"}
    )
    return Publication.objects.create(
        promotion=promo,
        channel=channel,
        external_ref=external_ref,
        dedupe_key=f"publish:{promo.id}:{channel.id}",
    )


def test_publish_creates_local_post(monkeypatch, settings):
    settings.GOOGLE_OAUTH_CLIENT_ID = "cid"
    settings.GOOGLE_OAUTH_CLIENT_SECRET = "sec"
    pub = _publication(config={"location": "accounts/1/locations/2", "refresh_token": "rt"})
    calls = []

    def _post(url, **kw):
        calls.append((url, kw))
        if "oauth2" in url:
            return _Resp({"access_token": "at"})
        return _Resp({"name": "accounts/1/locations/2/localPosts/99"})

    monkeypatch.setattr(adapters.requests, "post", _post)

    assert adapters.publish(pub) == "accounts/1/locations/2/localPosts/99"
    post_url, post_kw = calls[1]
    assert post_url.endswith("accounts/1/locations/2/localPosts")
    assert "Brötchen" in post_kw["json"]["summary"]
    assert "Nur heute" in post_kw["json"]["summary"]
    assert post_kw["headers"]["Authorization"] == "Bearer at"


def test_publish_without_config_raises():
    pub = _publication(config={})
    with pytest.raises(RuntimeError, match="nicht konfiguriert"):
        adapters.publish(pub)


def test_remove_deletes_post(monkeypatch, settings):
    settings.GOOGLE_OAUTH_CLIENT_ID = "cid"
    settings.GOOGLE_OAUTH_CLIENT_SECRET = "sec"
    pub = _publication(
        config={"location": "accounts/1/locations/2", "refresh_token": "rt"},
        external_ref="accounts/1/locations/2/localPosts/99",
    )
    monkeypatch.setattr(adapters.requests, "post", lambda url, **kw: _Resp({"access_token": "at"}))
    deleted = []

    def _delete(url, **kw):
        deleted.append(url)
        return _Resp()

    monkeypatch.setattr(adapters.requests, "delete", _delete)

    adapters.remove(pub)
    assert deleted and deleted[0].endswith("/localPosts/99")


def test_remove_without_post_is_noop(monkeypatch):
    pub = _publication(config={"refresh_token": "rt"})  # external_ref пуст

    def _boom(*args, **kw):
        raise AssertionError("API must not be called without external_ref")

    monkeypatch.setattr(adapters.requests, "delete", _boom)
    adapters.remove(pub)  # без исключения — снятие идемпотентно
