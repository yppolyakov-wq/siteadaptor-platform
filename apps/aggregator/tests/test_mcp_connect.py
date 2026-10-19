"""T-8.10f F-5: подключение MCP — строка в llms.txt портала и команда mcp_smoke."""

import json
from io import StringIO
from types import SimpleNamespace

import pytest
from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.test import RequestFactory, override_settings

from apps.aggregator import portal_views
from apps.aggregator.mcp.views import mcp_endpoint
from apps.aggregator.tests.test_machine_readable import _HOST, _get, _listing, _portal

pytestmark = pytest.mark.django_db

PORTAL = {"ROOT_URLCONF": "config.urls_portal"}


@pytest.fixture(autouse=True)
def _rl(isolated_ratelimit):
    cache.clear()
    yield isolated_ratelimit
    cache.clear()


def _llms(portal) -> str:
    return portal_views.portal_llms_txt(_get("/llms.txt", portal)).content.decode()


def test_llms_txt_names_mcp_only_when_enabled():
    with override_settings(MCP_ENABLED=False, **PORTAL):
        assert "/mcp/" not in _llms(_portal())
    cache.clear()
    with override_settings(MCP_ENABLED=True, MCP_PORTAL_HOSTS=[], **PORTAL):
        body = _llms(_portal(host="zwei.siteadaptor.de"))
    assert "## MCP" in body and "/mcp/" in body and "search_offers" in body


def _fake_post(portal):
    """requests.Session.post → настоящий эндпоинт (без сети)."""

    def post(self, url, data=None, headers=None, timeout=None):
        extra = {}
        if headers and headers.get("MCP-Protocol-Version"):
            extra["HTTP_MCP_PROTOCOL_VERSION"] = headers["MCP-Protocol-Version"]
        req = RequestFactory().post(
            "/mcp/", data=data, content_type="application/json", HTTP_HOST=_HOST, **extra
        )
        req.portal = portal
        resp = mcp_endpoint(req)
        body = resp.content.decode()
        return SimpleNamespace(
            status_code=resp.status_code, text=body, json=lambda: json.loads(body)
        )

    return post


def test_smoke_command_walks_the_handshake(monkeypatch):
    import requests

    with override_settings(MCP_ENABLED=True, MCP_PORTAL_HOSTS=[], **PORTAL):
        portal = _portal()
        _listing(title={"de": "Brotkorb"})
        monkeypatch.setattr(requests.Session, "post", _fake_post(portal))
        out = StringIO()
        call_command("mcp_smoke", "--url", f"https://{_HOST}/mcp/", "--query", "Brot", stdout=out)
    text = out.getvalue()
    assert "✓ initialize" in text and "✓ tools/list" in text and "Brotkorb" in text


def test_smoke_command_fails_loudly_when_disabled(monkeypatch):
    import requests

    def post(self, url, **kw):
        return SimpleNamespace(status_code=404, text="Not Found", json=dict)

    monkeypatch.setattr(requests.Session, "post", post)
    with pytest.raises(CommandError, match="MCP_ENABLED"):
        call_command("mcp_smoke", "--url", f"https://{_HOST}/mcp/", stdout=StringIO())


def test_smoke_command_rejects_non_http_url():
    with pytest.raises(CommandError):
        call_command("mcp_smoke", "--url", "file:///etc/passwd", stdout=StringIO())


@pytest.mark.parametrize(
    "post",
    [
        "conn",
        "html",
        "list",
        "noresult",
    ],
)
def test_smoke_command_turns_bad_answers_into_clean_errors(monkeypatch, post):
    import requests

    def fake(self, url, **kw):
        if post == "conn":
            raise requests.ConnectionError("refused")
        body = {"html": "<html>Shop</html>", "list": "[1, 2]", "noresult": '{"jsonrpc": "2.0"}'}[
            post
        ]
        return SimpleNamespace(status_code=200, text=body, json=lambda: json.loads(body))

    monkeypatch.setattr(requests.Session, "post", fake)
    with pytest.raises(CommandError):
        call_command("mcp_smoke", "--url", f"https://{_HOST}/mcp/", stdout=StringIO())
