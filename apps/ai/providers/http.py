"""Один HTTP-вызов JSON-API с нормализацией ошибок.

Ключи живут только в заголовках запроса: исключения пересоздаются БЕЗ текста ответа,
URL с query и заголовков (`from None`), поэтому в логи и в `str(exc)` они не попадают."""

from __future__ import annotations

import requests

from ..errors import AIConfigError, AIRateLimited, AIUnavailable

CONNECT_TIMEOUT = 5


def post_json(url: str, *, headers: dict, payload: dict, timeout_s: int) -> dict:
    try:
        resp = requests.post(
            url, headers=headers, json=payload, timeout=(CONNECT_TIMEOUT, timeout_s)
        )
    except requests.Timeout:
        raise AIUnavailable("timeout") from None
    except requests.RequestException as exc:
        raise AIUnavailable(f"network {type(exc).__name__}") from None
    status = resp.status_code
    if status == 429:
        raise AIRateLimited("http 429")
    if status >= 500:
        raise AIUnavailable(f"http {status}")
    if status in (401, 403):
        raise AIConfigError(f"auth http {status}")
    if status >= 400:
        raise AIConfigError(f"http {status}")
    try:
        return resp.json()
    except ValueError:
        raise AIUnavailable("invalid response") from None
