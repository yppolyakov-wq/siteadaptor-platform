"""OAuth-B: Meta (FB/IG) one-click — authorize + page-token exchange (застаблено)."""

import pytest

from apps.publishing import oauth
from apps.publishing.models import Channel
from apps.publishing.secrets import decrypted_config

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _settings(settings):
    settings.OAUTH_CALLBACK_BASE = "https://siteadaptor.de"
    settings.META_APP_ID = "app-id"
    settings.META_APP_SECRET = "app-secret"
    settings.META_GRAPH_API_VERSION = "v21.0"


def _schema():
    from django.db import connection

    return connection.schema_name


class _Resp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def test_facebook_authorize_url_has_version_and_scope():
    url = oauth.authorize_url("facebook", "tenant_x")
    assert url.startswith("https://www.facebook.com/v21.0/dialog/oauth?")
    assert "client_id=app-id" in url
    assert "instagram_content_publish" in url
    assert "redirect_uri=https%3A%2F%2Fsiteadaptor.de%2Foauth%2Ffacebook%2Fcallback%2F" in url


def test_meta_complete_stores_fb_and_ig(monkeypatch):
    calls = []

    def _get(url, **kw):
        calls.append(url)
        if url.endswith("/oauth/access_token") and kw["params"].get("code"):
            return _Resp({"access_token": "short-user-token"})
        if url.endswith("/oauth/access_token"):  # fb_exchange_token
            return _Resp({"access_token": "long-user-token"})
        if url.endswith("/me/accounts"):
            return _Resp(
                {
                    "data": [
                        {
                            "id": "PAGE1",
                            "name": "Bäckerei",
                            "access_token": "page-token",
                            "instagram_business_account": {"id": "IG1"},
                        }
                    ]
                }
            )
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(oauth.requests, "get", _get)
    oauth.complete("facebook", _schema(), "the-code")

    fb = Channel.objects.get(type="facebook")
    assert fb.config["page_id"] == "PAGE1"
    assert decrypted_config(fb)["access_token"] == "page-token"  # зашифрован at-rest
    ig = Channel.objects.get(type="instagram")
    assert ig.config["ig_user_id"] == "IG1"
    assert decrypted_config(ig)["access_token"] == "page-token"


def test_meta_complete_no_pages_raises(monkeypatch):
    def _get(url, **kw):
        if url.endswith("/me/accounts"):
            return _Resp({"data": []})
        return _Resp({"access_token": "t"})

    monkeypatch.setattr(oauth.requests, "get", _get)
    with pytest.raises(RuntimeError, match="no Facebook pages"):
        oauth.complete("facebook", _schema(), "code")
