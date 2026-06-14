"""OAuth-A: in-app подключение каналов (state, authorize, exchange, callback)."""

import pytest
from django.test import RequestFactory

from apps.publishing import oauth, views
from apps.publishing.models import Channel
from apps.publishing.secrets import decrypted_config

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _settings(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"
    settings.OAUTH_CALLBACK_BASE = "https://siteadaptor.de"


# --- state ------------------------------------------------------------------------


def test_state_roundtrip_and_provider_guard():
    state = oauth.make_state("tenant_x", "pinterest")
    assert oauth.read_state(state, "pinterest") == "tenant_x"
    assert oauth.read_state(state, "google_business") is None  # чужой провайдер
    assert oauth.read_state("garbage", "pinterest") is None


def test_authorize_url_has_redirect_and_state(settings):
    settings.PINTEREST_CLIENT_ID = "pin-cid"
    url = oauth.authorize_url("pinterest", "tenant_x")
    assert url.startswith("https://www.pinterest.com/oauth/?")
    assert "client_id=pin-cid" in url
    assert "redirect_uri=https%3A%2F%2Fsiteadaptor.de%2Foauth%2Fpinterest%2Fcallback%2F" in url
    assert "state=" in url


def test_exchange_code_pinterest_uses_basic_auth(monkeypatch, settings):
    settings.PINTEREST_CLIENT_ID = "cid"
    settings.PINTEREST_CLIENT_SECRET = "sec"
    captured = {}

    class _R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"access_token": "pin-token"}

    def _post(url, **kw):
        captured.update(url=url, kw=kw)
        return _R()

    monkeypatch.setattr(oauth.requests, "post", _post)
    assert oauth.exchange_code("pinterest", "the-code") == "pin-token"
    assert captured["kw"]["auth"] == ("cid", "sec")  # Basic auth, не в body
    assert captured["kw"]["data"]["code"] == "the-code"


def test_store_token_encrypts_into_channel_config():
    oauth.store_token("pinterest", connection_schema(), "pin-token")
    channel = Channel.objects.get(type="pinterest")
    assert channel.config["access_token"] != "pin-token"  # зашифровано
    assert decrypted_config(channel)["access_token"] == "pin-token"


def connection_schema():
    from django.db import connection

    return connection.schema_name


# --- вьюхи ------------------------------------------------------------------------


def test_oauth_start_redirects_to_provider(monkeypatch):
    user = type("U", (), {"is_authenticated": True, "is_active": True})()
    req = RequestFactory().get("/dashboard/channels/connect/pinterest/")
    req.user = user
    resp = views.oauth_start(req, provider="pinterest")
    assert resp.status_code == 302
    assert resp["Location"].startswith("https://www.pinterest.com/oauth/")


def test_oauth_start_unknown_provider_404():
    from django.http import Http404

    user = type("U", (), {"is_authenticated": True, "is_active": True})()
    req = RequestFactory().get("/x/")
    req.user = user
    with pytest.raises(Http404):
        views.oauth_start(req, provider="tiktok")


def test_oauth_callback_stores_token(monkeypatch):
    schema = connection_schema()
    state = oauth.make_state(schema, "pinterest")
    monkeypatch.setattr(oauth, "exchange_code", lambda provider, code: "pin-token")
    monkeypatch.setattr(
        oauth, "tenant_channels_url", lambda s: "https://shop.test/dashboard/channels/"
    )
    req = RequestFactory().get(f"/oauth/pinterest/callback/?code=abc&state={state}")
    resp = views.oauth_callback(req, provider="pinterest")
    assert resp.status_code == 302
    assert decrypted_config(Channel.objects.get(type="pinterest"))["access_token"] == "pin-token"


def test_oauth_callback_bad_state_400():
    req = RequestFactory().get("/oauth/pinterest/callback/?code=abc&state=bad")
    resp = views.oauth_callback(req, provider="pinterest")
    assert resp.status_code == 400
