"""T-8.10f F-1: каркас MCP-эндпоинта портала (протокол, выключатель, защита).

План — docs/t8-10-rest-plan-2026-10-19.md §1.7 F-1. Вьюха зовётся напрямую через
RequestFactory с request.portal (паттерн test_machine_readable.py)."""

import json
import logging

import pytest
from django.test import RequestFactory, override_settings
from django.urls import resolve

from apps.aggregator.mcp import protocol, tools
from apps.aggregator.mcp.views import mcp_endpoint
from apps.aggregator.models import AggregatorPortal

pytestmark = pytest.mark.django_db

_HOST = "solingen.siteadaptor.de"
ON = {"MCP_ENABLED": True, "MCP_PORTAL_HOSTS": [], "MCP_ALLOWED_ORIGINS": []}


@pytest.fixture
def portal():
    return AggregatorPortal.objects.create(
        host=_HOST, kind="city", city="Solingen", title={"de": "Entdecke Solingen"}, is_active=True
    )


@pytest.fixture(autouse=True)
def _rl(isolated_ratelimit):
    return isolated_ratelimit


@pytest.fixture
def echo_tool(monkeypatch):
    """Служебный инструмент только для теста протокола (реестр F-1 пуст)."""
    reg = dict(tools.REGISTRY)
    monkeypatch.setattr(tools, "REGISTRY", reg)

    def handler(args, ctx):
        if args.get("fail"):
            raise tools.ToolError("nicht gefunden")
        if args.get("bad_output"):
            return {"echo": 1}
        return {"echo": args.get("text", ""), "city": ctx.portal.city}

    tools.register(
        tools.Tool(
            name="echo",
            title="Echo",
            description="test",
            input_schema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "maxLength": 10},
                    "fail": {"type": "boolean"},
                    "bad_output": {"type": "boolean"},
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "properties": {"echo": {"type": "string"}, "city": {"type": "string"}},
                "required": ["echo"],
            },
            handler=handler,
            annotations={"readOnlyHint": True},
        )
    )


def _post(portal, payload, *, raw=None, **extra):
    body = raw if raw is not None else json.dumps(payload)
    req = RequestFactory().post(
        "/mcp/", data=body, content_type="application/json", HTTP_HOST=_HOST, **extra
    )
    req.portal = portal
    return mcp_endpoint(req)


def _rpc(method, params=None, msg_id=1):
    msg = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        msg["params"] = params
    return msg


def _body(resp):
    return json.loads(resp.content)


# --- выключатель и маршрут --------------------------------------------------


def test_disabled_by_default_is_404(portal):
    from django.http import Http404

    with override_settings(MCP_ENABLED=False), pytest.raises(Http404):
        _post(portal, _rpc("ping"))


@override_settings(**ON)
def test_no_portal_is_404():
    from django.http import Http404

    with pytest.raises(Http404):
        _post(None, _rpc("ping"))


@override_settings(MCP_ENABLED=True, MCP_PORTAL_HOSTS=["andere.siteadaptor.de"])
def test_host_not_in_pilot_list_is_404(portal):
    from django.http import Http404

    with pytest.raises(Http404):
        _post(portal, _rpc("ping"))


@override_settings(MCP_ENABLED=True, MCP_PORTAL_HOSTS=[_HOST.upper()])
def test_host_in_pilot_list_is_served(portal):
    assert _post(portal, _rpc("ping")).status_code == 200


def test_route_is_before_facet_catch_all():
    match = resolve("/mcp/", urlconf="config.urls_portal")
    assert match.url_name == "portal-mcp"


def test_robots_disallows_mcp():
    from apps.aggregator.portal_views import PORTAL_DISALLOW

    assert "/mcp/" in PORTAL_DISALLOW


# --- HTTP-уровень ---------------------------------------------------------------


@override_settings(**ON)
@pytest.mark.parametrize("method", ["get", "delete", "put"])
def test_only_post(portal, method):
    req = getattr(RequestFactory(), method)("/mcp/", HTTP_HOST=_HOST)
    req.portal = portal
    resp = mcp_endpoint(req)
    assert resp.status_code == 405 and resp["Allow"] == "POST"


@override_settings(**ON)
def test_foreign_origin_is_forbidden(portal):
    assert _post(portal, _rpc("ping"), HTTP_ORIGIN="https://evil.example").status_code == 403


@override_settings(MCP_ENABLED=True, MCP_ALLOWED_ORIGINS=["https://claude.ai"])
def test_allowed_origin_passes(portal):
    assert _post(portal, _rpc("ping"), HTTP_ORIGIN="https://claude.ai").status_code == 200


@override_settings(MCP_MAX_BODY=200, **ON)
def test_large_body_is_413(portal):
    resp = _post(portal, None, raw=json.dumps(_rpc("ping", {"x": "a" * 500})))
    assert resp.status_code == 413


@override_settings(MCP_RATE_PER_IP=2, **ON)
def test_rate_limit_per_ip(portal):
    ip = {"REMOTE_ADDR": "10.1.1.1"}
    assert _post(portal, _rpc("ping"), **ip).status_code == 200
    assert _post(portal, _rpc("ping"), **ip).status_code == 200
    resp = _post(portal, _rpc("ping"), **ip)
    assert resp.status_code == 429 and resp["Retry-After"]
    # другой адрес — свой счётчик
    assert _post(portal, _rpc("ping"), REMOTE_ADDR="10.1.1.2").status_code == 200


@override_settings(MCP_RATE_GLOBAL=2, **ON)
def test_rate_limit_global(portal):
    assert _post(portal, _rpc("ping"), REMOTE_ADDR="10.2.0.1").status_code == 200
    assert _post(portal, _rpc("ping"), REMOTE_ADDR="10.2.0.2").status_code == 200
    assert _post(portal, _rpc("ping"), REMOTE_ADDR="10.2.0.3").status_code == 429


@override_settings(**ON)
def test_unsupported_protocol_header_is_400(portal):
    resp = _post(portal, _rpc("ping"), HTTP_MCP_PROTOCOL_VERSION="1999-01-01")
    assert resp.status_code == 400


@override_settings(**ON)
def test_supported_protocol_header_passes(portal):
    resp = _post(portal, _rpc("ping"), HTTP_MCP_PROTOCOL_VERSION=protocol.PROTOCOL_VERSIONS[1])
    assert resp.status_code == 200


@override_settings(**ON)
def test_no_cookies_no_session(portal):
    resp = _post(portal, _rpc("initialize", {"protocolVersion": "2025-06-18"}))
    assert resp.status_code == 200
    assert not resp.cookies
    assert "no-cache" in resp["Cache-Control"] or "max-age=0" in resp["Cache-Control"]


# --- JSON-RPC -----------------------------------------------------------------


@override_settings(**ON)
def test_parse_error(portal):
    resp = _post(portal, None, raw="{nicht json")
    assert resp.status_code == 400 and _body(resp)["error"]["code"] == protocol.PARSE_ERROR


@override_settings(**ON)
def test_batch_rejected(portal):
    resp = _post(portal, [_rpc("ping"), _rpc("ping", msg_id=2)])
    assert _body(resp)["error"]["code"] == protocol.INVALID_REQUEST


@override_settings(**ON)
@pytest.mark.parametrize(
    "msg",
    [
        {"id": 1, "method": "ping"},  # без jsonrpc
        {"jsonrpc": "2.0", "id": 1},  # без method и без result
        {"jsonrpc": "2.0", "id": 1, "method": 5},
        {"jsonrpc": "2.0", "id": True, "method": "ping"},
        {"jsonrpc": "2.0", "id": {"x": 1}, "method": "ping"},
        "ping",
    ],
)
def test_invalid_request(portal, msg):
    resp = _post(portal, msg)
    assert resp.status_code == 400 and _body(resp)["error"]["code"] == protocol.INVALID_REQUEST


@override_settings(**ON)
def test_unknown_method(portal):
    body = _body(_post(portal, _rpc("resources/list", msg_id="a")))
    assert body["id"] == "a" and body["error"]["code"] == protocol.METHOD_NOT_FOUND


@override_settings(**ON)
def test_notification_is_202_without_body(portal):
    resp = _post(portal, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert resp.status_code == 202 and resp.content == b""


@override_settings(**ON)
def test_client_response_is_accepted(portal):
    resp = _post(portal, {"jsonrpc": "2.0", "id": 9, "result": {}})
    assert resp.status_code == 202


@override_settings(**ON)
def test_initialize_echoes_supported_version(portal):
    version = protocol.PROTOCOL_VERSIONS[-1]
    res = _body(_post(portal, _rpc("initialize", {"protocolVersion": version})))["result"]
    assert res["protocolVersion"] == version
    assert res["capabilities"] == {"tools": {"listChanged": False}}
    assert res["serverInfo"]["name"] == "siteadaptor-city-catalog"
    assert res["serverInfo"]["title"] == "Entdecke Solingen"
    assert "sponsored" in res["instructions"] and "demo" in res["instructions"]


@override_settings(**ON)
def test_initialize_unknown_version_gets_ours(portal):
    res = _body(_post(portal, _rpc("initialize", {"protocolVersion": "2020-01-01"})))["result"]
    assert res["protocolVersion"] == protocol.PROTOCOL_VERSIONS[0]


@override_settings(**ON)
def test_ping(portal):
    assert _body(_post(portal, _rpc("ping", msg_id=7))) == {"jsonrpc": "2.0", "id": 7, "result": {}}


@override_settings(**ON)
def test_params_must_be_object(portal):
    body = _body(_post(portal, {"jsonrpc": "2.0", "id": 1, "method": "ping", "params": [1]}))
    assert body["error"]["code"] == protocol.INVALID_PARAMS


# --- инструменты --------------------------------------------------------------


@override_settings(**ON)
def test_tools_list_describes_registry(portal, echo_tool):
    listed = _body(_post(portal, _rpc("tools/list")))["result"]["tools"]
    echo = next(t for t in listed if t["name"] == "echo")
    assert set(echo) >= {"name", "title", "description", "inputSchema", "outputSchema"}
    assert echo["annotations"] == {"readOnlyHint": True}


@override_settings(**ON)
def test_tools_call_returns_structured_content(portal, echo_tool):
    res = _body(_post(portal, _rpc("tools/call", {"name": "echo", "arguments": {"text": "hi"}})))
    res = res["result"]
    assert res["isError"] is False
    assert res["structuredContent"] == {"echo": "hi", "city": "Solingen"}
    assert json.loads(res["content"][0]["text"]) == res["structuredContent"]


@override_settings(**ON)
def test_tools_call_unknown_tool_is_protocol_error(portal, echo_tool):
    body = _body(_post(portal, _rpc("tools/call", {"name": "nope"})))
    assert body["error"]["code"] == protocol.INVALID_PARAMS


@override_settings(**ON)
def test_tools_call_invalid_input_is_tool_error_not_500(portal, echo_tool):
    for args in ({"text": "x" * 50}, {"unexpected": 1}, {"text": 5}):
        res = _body(_post(portal, _rpc("tools/call", {"name": "echo", "arguments": args})))
        assert res["result"]["isError"] is True


@override_settings(**ON)
def test_tools_call_arguments_must_be_object(portal, echo_tool):
    body = _body(_post(portal, _rpc("tools/call", {"name": "echo", "arguments": [1]})))
    assert body["error"]["code"] == protocol.INVALID_PARAMS


@override_settings(**ON)
def test_domain_error_is_is_error(portal, echo_tool):
    res = _body(_post(portal, _rpc("tools/call", {"name": "echo", "arguments": {"fail": True}})))
    assert res["result"] == {
        "content": [{"type": "text", "text": "nicht gefunden"}],
        "isError": True,
    }


@override_settings(**ON)
def test_output_schema_violation_is_internal_error(portal, echo_tool):
    args = {"name": "echo", "arguments": {"bad_output": True}}
    resp = _post(portal, _rpc("tools/call", args, msg_id=4))
    body = _body(resp)
    assert resp.status_code == 200
    assert body["id"] == 4 and body["error"]["code"] == protocol.INTERNAL_ERROR


@override_settings(**ON)
def test_logs_never_contain_arguments(portal, echo_tool, caplog):
    secret = "geheim@x.de"[:10]
    with caplog.at_level(logging.INFO, logger="apps.aggregator.mcp.views"):
        _post(portal, _rpc("tools/call", {"name": "echo", "arguments": {"text": secret}}))
    assert caplog.records, "вызов должен оставить строку в журнале"
    assert all(secret not in r.getMessage() for r in caplog.records)


# --- security-ревью F-1 -------------------------------------------------------


@override_settings(**ON)
@pytest.mark.parametrize("raw", ["[" * 30000, '{"a":' * 12000])
def test_deep_nesting_is_parse_error_not_500(portal, raw):
    resp = _post(portal, None, raw=raw)
    assert resp.status_code == 400 and _body(resp)["error"]["code"] == protocol.PARSE_ERROR


@override_settings(**ON)
def test_log_never_contains_client_method_text(portal, caplog):
    forged = "x\nINFO forged line"
    with caplog.at_level(logging.INFO, logger="apps.aggregator.mcp.views"):
        _post(portal, _rpc(forged))
    assert caplog.records
    assert all("forged" not in r.getMessage() for r in caplog.records)


@override_settings(**ON)
def test_reflected_input_is_clipped(portal, echo_tool):
    long_name = "n" * 5000
    body = _body(_post(portal, _rpc("tools/call", {"name": long_name})))
    assert len(body["error"]["message"]) < protocol.ECHO_MAX + 40
    res = _body(
        _post(portal, _rpc("tools/call", {"name": "echo", "arguments": {"text": "y" * 5000}}))
    )
    assert len(res["result"]["content"][0]["text"]) < 2 * protocol.ECHO_MAX + 60


# --- django-ревью F-1 ---------------------------------------------------------


def test_route_without_slash_is_same_endpoint():
    assert resolve("/mcp", urlconf="config.urls_portal").func is mcp_endpoint


@override_settings(**ON)
def test_missing_content_length_is_411(portal):
    req = RequestFactory().post(
        "/mcp/", data="{}", content_type="application/json", HTTP_HOST=_HOST
    )
    del req.META["CONTENT_LENGTH"]
    req.portal = portal
    assert mcp_endpoint(req).status_code == 411


@override_settings(**ON)
def test_invalid_method_keeps_request_id(portal):
    body = _body(_post(portal, {"jsonrpc": "2.0", "id": 42, "method": 5}))
    assert body["id"] == 42 and body["error"]["code"] == protocol.INVALID_REQUEST


@override_settings(MCP_RATE_PER_IP=1, **ON)
def test_rate_limit_runs_before_body_checks(portal):
    ip = {"REMOTE_ADDR": "10.3.3.3"}
    assert _post(portal, _rpc("ping"), **ip).status_code == 200
    # второй запрос — сверхлимит: 429 даже с телом, которое иначе дало бы 400
    assert _post(portal, None, raw="{nicht json", **ip).status_code == 429


@override_settings(**ON)
def test_old_protocol_version_is_still_accepted(portal):
    res = _body(_post(portal, _rpc("initialize", {"protocolVersion": "2024-11-05"})))["result"]
    assert res["protocolVersion"] == "2024-11-05"
