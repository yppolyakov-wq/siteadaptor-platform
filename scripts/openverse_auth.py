"""Ключ Openverse для скриптов подбора демо-фото (`demo_photo_sheet.py`, `demo_photo_fetch.py`).

Без ключа Openverse даёт анониму 200 запросов в день — на сотни демо-картинок это
недели. С ключом (зарегистрированное приложение с подтверждённой почтой) лимит выше.

Ключ лежит в окружении сессии, не в репозитории:
    OPENVERSE_CLIENT_ID, OPENVERSE_CLIENT_SECRET
Нет переменных — скрипты работают анонимно, как раньше.
"""

from __future__ import annotations

import os
import time

import requests

TOKEN_URL = "https://api.openverse.org/v1/auth_tokens/token/"
_cache: dict = {}


def auth_headers(ua: str) -> dict:
    """Заголовки запроса к API: Bearer-токен, если ключ задан (кэш до истечения)."""
    headers = {"Accept": "application/json", "User-Agent": ua}
    cid = os.environ.get("OPENVERSE_CLIENT_ID", "").strip()
    secret = os.environ.get("OPENVERSE_CLIENT_SECRET", "").strip()
    if not cid or not secret:
        return headers
    if _cache.get("expires", 0) <= time.time() + 60:
        r = requests.post(
            TOKEN_URL,
            data={"grant_type": "client_credentials", "client_id": cid, "client_secret": secret},
            headers={"User-Agent": ua},
            timeout=40,
        )
        r.raise_for_status()  # неверный ключ — громко, а не тихий откат на анонима
        body = r.json()
        _cache["token"] = body["access_token"]
        _cache["expires"] = time.time() + int(body.get("expires_in", 3600))
    headers["Authorization"] = f"Bearer {_cache['token']}"
    return headers
