"""Клиент Google Business Profile для Д3 «GBP-Sync» (план docs/d3-gbp-sync-plan-2026-10-18.md).

Только фиксированные хосты Google; токены живут в памяти на время одного вызова и не
попадают ни в логи, ни в сообщения, ни в `last_error_code` (там — только код ниже).
Тело ответа Google не сохраняем: оно может эхом нести данные запроса.

Пока Google не одобрил доступ проекта к API (квота 0), запросы дают 403 → код
`not_approved`; экран честно показывает «noch nicht freigeschaltet»."""

from __future__ import annotations

import logging
import re

import requests
from django.conf import settings

logger = logging.getLogger("publishing")

TOKEN_URL = "https://oauth2.googleapis.com/token"
ACCOUNTS_URL = "https://mybusinessaccountmanagement.googleapis.com/v1/accounts"
INFO_API = "https://mybusinessbusinessinformation.googleapis.com/v1"
V4_API = "https://mybusiness.googleapis.com/v4"

# v4-имя локации (так оно хранится в Channel.config["location"]).
LOCATION_RE = re.compile(r"^accounts/\d+/locations/\d+$")
ACCOUNT_RE = re.compile(r"^accounts/\d+$")
MAX_ACCOUNTS = 20
MAX_LOCATIONS = 200

CODES = ("not_configured", "not_approved", "auth", "quota", "not_found", "network", "bad_response")


class GbpError(Exception):
    """Ошибка обмена с Google. `code` — один из CODES; `status` — HTTP-статус или 0."""

    def __init__(self, code: str, status: int = 0):
        super().__init__(code)
        self.code = code if code in CODES else "bad_response"
        self.status = status


def _timeout() -> int:
    return int(getattr(settings, "GBP_API_TIMEOUT", 20))


def _error_for(response) -> GbpError:
    status = getattr(response, "status_code", 0) or 0
    if status == 401:
        return GbpError("auth", status)
    if status == 403:
        return GbpError("not_approved", status)
    if status == 404:
        return GbpError("not_found", status)
    if status == 429:
        return GbpError("quota", status)
    return GbpError("bad_response", status)


def _json(response):
    try:
        data = response.json()
    except ValueError as exc:
        raise GbpError("bad_response", getattr(response, "status_code", 0) or 0) from exc
    if not isinstance(data, dict):
        raise GbpError("bad_response", getattr(response, "status_code", 0) or 0)
    return data


def access_token(config) -> str:
    """refresh_token → access_token (платформенные ключи — из секрет-стора/env)."""
    from apps.secrets import store as secret_store

    refresh = (config or {}).get("refresh_token")
    if not refresh:
        raise GbpError("not_configured")
    try:
        response = requests.post(
            TOKEN_URL,
            data={
                "client_id": secret_store.get_or_setting(
                    "google_oauth_client_id", "GOOGLE_OAUTH_CLIENT_ID"
                ),
                "client_secret": secret_store.get_or_setting(
                    "google_oauth_client_secret", "GOOGLE_OAUTH_CLIENT_SECRET"
                ),
                "refresh_token": refresh,
                "grant_type": "refresh_token",
            },
            timeout=_timeout(),
        )
    except requests.RequestException as exc:
        raise GbpError("network") from exc
    if response.status_code in (400, 401):  # invalid_grant: доступ отозван/истёк
        raise GbpError("auth", response.status_code)
    if response.status_code >= 400:
        raise _error_for(response)
    token = _json(response).get("access_token")
    if not isinstance(token, str) or not token:
        raise GbpError("bad_response", response.status_code)
    return token


def location_ids(config) -> tuple[str, str]:
    """(v4-имя `accounts/A/locations/L`, v1-имя `locations/L`) из конфига канала."""
    location = str((config or {}).get("location") or "").strip()
    if not LOCATION_RE.match(location):
        raise GbpError("not_configured")
    return location, "locations/" + location.rsplit("/", 1)[1]


def _get(url: str, token: str, params: dict | None = None) -> dict:
    try:
        response = requests.get(
            url,
            params=params or {},
            headers={"Authorization": f"Bearer {token}"},
            timeout=_timeout(),
        )
    except requests.RequestException as exc:
        raise GbpError("network") from exc
    if response.status_code >= 400:
        raise _error_for(response)
    return _json(response)


def list_accounts(token: str) -> list[dict]:
    """[{name, title}] аккаунтов, к которым у токена есть доступ."""
    data = _get(ACCOUNTS_URL, token, {"pageSize": MAX_ACCOUNTS})
    out = []
    for row in data.get("accounts") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "")
        if ACCOUNT_RE.match(name):
            out.append({"name": name, "title": str(row.get("accountName") or name)[:200]})
    return out[:MAX_ACCOUNTS]


def list_locations(token: str, account: str) -> list[dict]:
    """[{name (v4), title, address}] локаций аккаунта; v1 отдаёт `locations/L`."""
    if not ACCOUNT_RE.match(account or ""):
        raise GbpError("not_configured")
    data = _get(
        f"{INFO_API}/{account}/locations",
        token,
        {"readMask": "name,title,storefrontAddress", "pageSize": 100},
    )
    out = []
    for row in data.get("locations") or []:
        if not isinstance(row, dict):
            continue
        tail = str(row.get("name") or "").rsplit("/", 1)[-1]
        if not tail.isdigit():
            continue
        address = row.get("storefrontAddress") if isinstance(row, dict) else None
        lines = []
        if isinstance(address, dict):
            lines = [str(x) for x in (address.get("addressLines") or []) if isinstance(x, str)]
            if isinstance(address.get("locality"), str):
                lines.append(address["locality"])
        out.append(
            {
                "name": f"{account}/locations/{tail}",
                "title": str(row.get("title") or tail)[:200],
                "address": ", ".join(lines)[:300],
            }
        )
    return out[:MAX_LOCATIONS]


def all_locations(config) -> list[dict]:
    """Все локации всех доступных аккаунтов (для выбора на экране)."""
    token = access_token(config)
    out = []
    for account in list_accounts(token):
        for loc in list_locations(token, account["name"]):
            out.append({**loc, "account": account["title"]})
            if len(out) >= MAX_LOCATIONS:
                return out
    return out
