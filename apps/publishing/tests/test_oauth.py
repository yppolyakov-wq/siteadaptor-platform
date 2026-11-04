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


def _req(path, session=None):
    from django.contrib.messages.storage.fallback import FallbackStorage

    req = RequestFactory().get(path)
    req.user = type("U", (), {"is_authenticated": True, "is_active": True})()
    req.session = session if session is not None else {}
    req._messages = FallbackStorage(req)
    return req


def test_oauth_start_redirects_to_provider_and_binds_the_browser():
    req = _req("/dashboard/channels/connect/pinterest/")
    resp = views.oauth_start(req, provider="pinterest")
    assert resp.status_code == 302
    assert resp["Location"].startswith("https://www.pinterest.com/oauth/")
    # SEC-C-M1: одноразовый код в сессии И в state
    nonce = req.session[oauth.SESSION_NONCE_KEY.format(provider="pinterest")]
    from urllib.parse import parse_qs, urlsplit

    state = parse_qs(urlsplit(resp["Location"]).query)["state"][0]
    assert oauth.read_state_data(state, "pinterest")["n"] == nonce


def test_oauth_start_unknown_provider_404():
    from django.http import Http404

    with pytest.raises(Http404):
        views.oauth_start(_req("/x/"), provider="tiktok")


def test_oauth_callback_forwards_to_the_cabinet_without_storing(monkeypatch):
    """Основной домен токен не сохраняет — передаёт код в кабинет бизнеса."""
    schema = connection_schema()
    state = oauth.make_state(schema, "pinterest", "n1", "shop.test")
    monkeypatch.setattr(oauth, "tenant_origin", lambda s, h: "https://shop.test")
    monkeypatch.setattr(oauth, "complete", lambda *a: pytest.fail("callback must not store"))
    req = RequestFactory().get(f"/oauth/pinterest/callback/?code=abc&state={state}")
    resp = views.oauth_callback(req, provider="pinterest")
    assert resp.status_code == 302
    assert resp["Location"].startswith(
        "https://shop.test/dashboard/channels/connect/pinterest/finish/?"
    )
    assert "code=abc" in resp["Location"]


def test_oauth_callback_bad_state_400():
    req = RequestFactory().get("/oauth/pinterest/callback/?code=abc&state=bad")
    resp = views.oauth_callback(req, provider="pinterest")
    assert resp.status_code == 400


def _finish(state, session):
    return views.oauth_finish(
        _req(f"/dashboard/channels/connect/pinterest/finish/?code=abc&state={state}", session),
        provider="pinterest",
    )


def test_oauth_finish_stores_token_in_the_starting_browser(monkeypatch):
    schema = connection_schema()
    monkeypatch.setattr(oauth, "exchange_code", lambda provider, code: "pin-token")
    session = {oauth.SESSION_NONCE_KEY.format(provider="pinterest"): "n1"}
    resp = _finish(oauth.make_state(schema, "pinterest", "n1"), session)
    assert resp.status_code == 302
    assert decrypted_config(Channel.objects.get(type="pinterest"))["access_token"] == "pin-token"
    assert not session  # код одноразовый


def test_oauth_finish_refuses_a_link_started_in_another_browser(monkeypatch):
    """Атака: ссылку на согласие, начатую атакующим, открывает жертва. У жертвы в
    сессии кода нет (или он свой) — токен её страницы не сохраняется."""
    schema = connection_schema()
    monkeypatch.setattr(oauth, "complete", lambda *a: pytest.fail("must not store"))
    attacker_state = oauth.make_state(schema, "pinterest", "attacker-nonce")
    assert _finish(attacker_state, {}).status_code == 302
    victim = {oauth.SESSION_NONCE_KEY.format(provider="pinterest"): "victim-nonce"}
    assert _finish(attacker_state, victim).status_code == 302
    assert not Channel.objects.filter(type="pinterest", config__has_key="access_token").exists()


def test_oauth_finish_refuses_state_of_another_business(monkeypatch):
    monkeypatch.setattr(oauth, "complete", lambda *a: pytest.fail("must not store"))
    session = {oauth.SESSION_NONCE_KEY.format(provider="pinterest"): "n1"}
    _finish(oauth.make_state("other_schema", "pinterest", "n1"), session)


def test_tenant_origin_accepts_only_domains_of_that_business():
    from apps.tenants.models import Domain
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory(schema_name="oauth_t", slug="oauth-t")
    Domain.objects.create(tenant=tenant, domain="laden.example", is_primary=True)
    Domain.objects.create(tenant=tenant, domain="mein-laden.de", is_primary=False)
    assert oauth.tenant_origin("oauth_t", "mein-laden.de:443") == "https://mein-laden.de"
    assert oauth.tenant_origin("oauth_t", "evil.example") == "https://laden.example"
    assert oauth.tenant_origin("nope", "evil.example") == ""
