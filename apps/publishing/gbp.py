"""Клиент Google Business Profile для Д3 «GBP-Sync» (план docs/d3-gbp-sync-plan-2026-10-18.md).

Только фиксированные хосты Google; токены живут в памяти на время одного вызова и не
попадают ни в логи, ни в сообщения, ни в `last_error_code` (там — только код ниже).
Тело ответа Google не сохраняем: оно может эхом нести данные запроса.

Пока Google не одобрил доступ проекта к API (квота 0), запросы дают 403 → код
`not_approved`; экран честно показывает «noch nicht freigeschaltet»."""

from __future__ import annotations

import logging
import re
import time

import requests
from django.conf import settings

logger = logging.getLogger("publishing")

TOKEN_URL = "https://oauth2.googleapis.com/token"
ACCOUNTS_URL = "https://mybusinessaccountmanagement.googleapis.com/v1/accounts"
INFO_API = "https://mybusinessbusinessinformation.googleapis.com/v1"
V4_API = "https://mybusiness.googleapis.com/v4"

# v4-имя локации (так оно хранится в Channel.config["location"]).
# ASCII + fullmatch: `\d` без re.ASCII пропускает цифры других письменностей, `$` — \n.
LOCATION_RE = re.compile(r"accounts/[0-9]+/locations/[0-9]+", re.ASCII)
ACCOUNT_RE = re.compile(r"accounts/[0-9]+", re.ASCII)
MAX_ACCOUNTS = 20
MAX_LOCATIONS = 200
MAX_PAGES = 5  # на один список; страница локаций — 100
LIST_DEADLINE_S = 45  # общий бюджет загрузки локаций в веб-запросе

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


def _list(value) -> list:
    """Список из ответа Google или [] — чужой тип не роняет экран в 500."""
    return value if isinstance(value, list) else []


def _looks_encrypted(value: str) -> bool:
    # Шифротекст Fernet, который не удалось расшифровать (сменили ключ): слать его
    # в Google бессмысленно и вредно — это «не подключено», а не «ошибка Google».
    return value.startswith("gAAAAA")


def access_token(config) -> str:
    """refresh_token → access_token (платформенные ключи — из секрет-стора/env)."""
    from apps.secrets import store as secret_store

    refresh = (config or {}).get("refresh_token")
    if not isinstance(refresh, str) or not refresh or _looks_encrypted(refresh):
        raise GbpError("not_configured")
    client_id = secret_store.get_or_setting("google_oauth_client_id", "GOOGLE_OAUTH_CLIENT_ID")
    client_secret = secret_store.get_or_setting(
        "google_oauth_client_secret", "GOOGLE_OAUTH_CLIENT_SECRET"
    )
    if not client_id or not client_secret:
        raise GbpError("not_configured")
    try:
        response = requests.post(
            TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
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
    if not LOCATION_RE.fullmatch(location):
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


def _pages(url: str, token: str, params: dict, key: str, cap: int, deadline: float | None):
    """Строки списка по всем страницам (до `cap` строк / MAX_PAGES страниц / дедлайна)."""
    rows: list = []
    params = dict(params)
    for _page in range(MAX_PAGES):
        data = _get(url, token, params)
        rows += [row for row in _list(data.get(key)) if isinstance(row, dict)]
        page_token = data.get("nextPageToken")
        if len(rows) >= cap or not isinstance(page_token, str) or not page_token:
            break
        if deadline is not None and time.monotonic() > deadline:
            break
        params["pageToken"] = page_token
    return rows[:cap]


def list_accounts(token: str, deadline: float | None = None) -> list[dict]:
    """[{name, title}] аккаунтов, к которым у токена есть доступ."""
    out = []
    for row in _pages(
        ACCOUNTS_URL, token, {"pageSize": MAX_ACCOUNTS}, "accounts", MAX_ACCOUNTS, deadline
    ):
        name = str(row.get("name") or "")
        if ACCOUNT_RE.fullmatch(name):
            out.append({"name": name, "title": str(row.get("accountName") or name)[:200]})
    return out


def list_locations(token: str, account: str, deadline: float | None = None) -> list[dict]:
    """[{name (v4), title, address}] локаций аккаунта; v1 отдаёт `locations/L`."""
    if not ACCOUNT_RE.fullmatch(account or ""):
        raise GbpError("not_configured")
    rows = _pages(
        f"{INFO_API}/{account}/locations",
        token,
        {"readMask": "name,title,storefrontAddress", "pageSize": 100},
        "locations",
        MAX_LOCATIONS,
        deadline,
    )
    out = []
    for row in rows:
        tail = str(row.get("name") or "").rsplit("/", 1)[-1]
        if not (tail.isascii() and tail.isdigit()):
            continue
        address = row.get("storefrontAddress")
        lines = []
        if isinstance(address, dict):
            lines = [x for x in _list(address.get("addressLines")) if isinstance(x, str)]
            if isinstance(address.get("locality"), str):
                lines.append(address["locality"])
        out.append(
            {
                "name": f"{account}/locations/{tail}",
                "title": str(row.get("title") or tail)[:200],
                "address": ", ".join(lines)[:300],
            }
        )
    return out


def all_locations(config) -> list[dict]:
    """Все локации всех доступных аккаунтов (для выбора на экране).

    Сбой одного аккаунта (нет прав, таймаут) не прячет остальные; ошибка поднимается,
    только если не удалось получить ни одного аккаунта. Общий дедлайн держит веб-воркер."""
    deadline = time.monotonic() + LIST_DEADLINE_S
    token = access_token(config)
    out: list[dict] = []
    first_error: GbpError | None = None
    accounts = list_accounts(token, deadline)
    for account in accounts:
        if time.monotonic() > deadline:
            break
        try:
            locations = list_locations(token, account["name"], deadline)
        except GbpError as exc:
            if exc.code in ("auth", "quota"):  # общие для всего токена — дальше бессмысленно
                raise
            first_error = first_error or exc
            continue
        for loc in locations:
            out.append({**loc, "account": account["title"]})
            if len(out) >= MAX_LOCATIONS:
                return out
    if not out and first_error is not None:
        raise first_error
    return out


def get_hours(token: str, v1_name: str) -> dict:
    """{"periods": [...], "special_count": N} — обычные часы и число особых дат локации."""
    data = _get(f"{INFO_API}/{v1_name}", token, {"readMask": "regularHours,specialHours"})
    regular = data.get("regularHours")
    special = data.get("specialHours")
    periods = _list(regular.get("periods")) if isinstance(regular, dict) else []
    days = _list(special.get("specialHourPeriods")) if isinstance(special, dict) else []
    return {"periods": periods, "special_count": len(days)}


def patch_regular_hours(token: str, v1_name: str, periods: list) -> None:
    """Записать ТОЛЬКО обычные часы (`updateMask=regularHours`) — особые часы не трогаем."""
    try:
        response = requests.patch(
            f"{INFO_API}/{v1_name}",
            params={"updateMask": "regularHours"},
            json={"regularHours": {"periods": periods}},
            headers={"Authorization": f"Bearer {token}"},
            timeout=_timeout(),
        )
    except requests.RequestException as exc:
        raise GbpError("network") from exc
    if response.status_code >= 400:
        raise _error_for(response)
