"""T-8.10f: эндпоинт `POST /mcp/` на хосте портала (Streamable HTTP, ответ — JSON).

Порядок отказов: выключено/чужой хост → 404 · не POST → 405 · чужой Origin → 403 ·
велико тело → 413 · лимит частоты → 429 · неизвестная версия протокола → 400.
Аргументы вызовов в лог не пишем (DSGVO) — только метод и код результата.
"""

from __future__ import annotations

import json
import logging

from django.conf import settings
from django.http import Http404, HttpResponse, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt

from apps.core import ratelimit

from . import (
    action_tools,  # noqa: F401 — регистрирует инструменты действий (F-4)
    handlers,  # noqa: F401 — регистрирует инструменты в реестре
    protocol,
    tools,
)

logger = logging.getLogger(__name__)

_WINDOW = 60


def mcp_available(portal) -> bool:
    """Включён ли MCP на этом портале (env-выключатель + необязательный список хостов)."""
    if portal is None or not getattr(settings, "MCP_ENABLED", False):
        return False
    hosts = {h.strip().lower() for h in getattr(settings, "MCP_PORTAL_HOSTS", []) if h.strip()}
    return not hosts or (portal.host or "").lower() in hosts


def _json(payload, status: int = 200) -> JsonResponse:
    return JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})


def _rpc_error(code: int, message: str, status: int) -> JsonResponse:
    return _json(protocol.error(None, code, message), status=status)


def _origin_allowed(request) -> bool:
    origin = request.META.get("HTTP_ORIGIN")
    if not origin:
        return True
    allowed = {o.strip().rstrip("/") for o in getattr(settings, "MCP_ALLOWED_ORIGINS", []) if o}
    return origin.rstrip("/") in allowed


def _too_large(request) -> bool:
    limit = getattr(settings, "MCP_MAX_BODY", 64 * 1024)
    try:
        declared = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        declared = 0
    return declared > limit or len(request.body) > limit


def _rate_limited(request) -> bool:
    per_ip = getattr(settings, "MCP_RATE_PER_IP", 600)
    overall = getattr(settings, "MCP_RATE_GLOBAL", 3000)
    if ratelimit.hit("mcp", ratelimit.client_ip(request), limit=per_ip, window=_WINDOW):
        return True
    return ratelimit.hit("mcp-global", "all", limit=overall, window=_WINDOW)


def _log_method(message) -> str:
    """Метод для журнала: только известные значения — ввод клиента в лог не пишем
    (переводы строк подделали бы записи журнала)."""
    method = message.get("method") if isinstance(message, dict) else None
    return method if method in protocol.KNOWN_METHODS else "?"


@csrf_exempt
@never_cache
def mcp_endpoint(request):
    portal = getattr(request, "portal", None)
    if not mcp_available(portal):
        raise Http404
    if request.method != "POST":
        resp = HttpResponse(status=405)
        resp["Allow"] = "POST"
        return resp
    if not _origin_allowed(request):
        return HttpResponse(status=403)
    if _rate_limited(request):  # до чтения тела
        resp = _rpc_error(protocol.INTERNAL_ERROR, "Too many requests", 429)
        resp["Retry-After"] = str(_WINDOW)
        return resp
    if not request.META.get("CONTENT_LENGTH"):
        # WSGI без Content-Length (chunked) отдаёт Django пустое тело — честный отказ,
        # а не «Parse error» на корректное сообщение.
        return _rpc_error(protocol.INVALID_REQUEST, "Content-Length required", 411)
    if _too_large(request):
        return _rpc_error(protocol.INVALID_REQUEST, "Request too large", 413)
    header_version = request.META.get("HTTP_MCP_PROTOCOL_VERSION")
    if header_version and header_version not in protocol.PROTOCOL_VERSIONS:
        return _rpc_error(protocol.INVALID_REQUEST, "Unsupported MCP-Protocol-Version", 400)
    try:
        message = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        # RecursionError — глубокая вложенность («[[[[…» в пределах 64 КБ)
        return _rpc_error(protocol.PARSE_ERROR, "Parse error", 400)
    if isinstance(message, list):
        # JSON-RPC batch в текущих ревизиях MCP убран
        return _rpc_error(protocol.INVALID_REQUEST, "Batch requests are not supported", 400)

    ctx = tools.Context(portal=portal, request=request)
    method = _log_method(message)
    try:
        reply = protocol.dispatch(message, ctx)
    except protocol.ProtocolError as exc:
        logger.info("mcp method=%s rejected code=%s", method, exc.code)
        return _json(protocol.error(exc.msg_id, exc.code, exc.message), status=exc.status)
    except Exception:  # noqa: BLE001 — сбой обработчика не должен уронить эндпоинт в 500 без тела
        logger.exception("mcp method=%s failed", method)
        msg_id = message.get("id") if isinstance(message, dict) else None
        return _json(protocol.error(msg_id, protocol.INTERNAL_ERROR, "Internal error"))
    if reply is None:
        return HttpResponse(status=202)
    outcome = "error" if "error" in reply else "ok"
    logger.info("mcp method=%s %s", method, outcome)
    return _json(reply)
