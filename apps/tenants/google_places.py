"""GK-11: Google-рейтинг бизнеса — Places API (New), только rating/userRatingCount.

Ключ — платформенный (шифрованный стор → env-фолбэк GOOGLE_PLACES_API_KEY,
external-integrations-backlog: включённый Places API + billing на владельце).
FieldMask из двух полей = дешёвый Basic-SKU; URL платформенный (SSRF-гард не
нужен — owner-ввод только place_id, он уходит в path через quote)."""

import logging
import re
from dataclasses import dataclass, field
from urllib.parse import quote

import requests

_PLACES_API = "https://places.googleapis.com/v1/places"


def api_key() -> str:
    from apps.secrets.store import get_or_setting

    return get_or_setting("google_places_api_key", "GOOGLE_PLACES_API_KEY")


def fetch_rating(place_id: str) -> tuple:
    """(rating, count) по Place ID. RuntimeError без ключа; сетевые/HTTP-ошибки
    пробрасываются requests'ом — вызывающий (beat/кнопка) решает, что делать."""
    key = api_key()
    if not key:
        raise RuntimeError("Google Places nicht konfiguriert: GOOGLE_PLACES_API_KEY fehlt")
    response = requests.get(
        f"{_PLACES_API}/{quote(place_id, safe='')}",
        headers={
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": "rating,userRatingCount",
        },
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    return data.get("rating"), int(data.get("userRatingCount") or 0)


# --- AIS W4-3: найти свой профиль Google (мастер v4, шаг «Firma») -----------------------
# План — docs/ais-w4-3-google-profile-plan-2026-11-06.md. Ответ Google — недоверенные данные:
# всё клампится и проверяется здесь; фото не запрашиваются никогда (условия Places API).

logger = logging.getLogger(__name__)

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
SEARCH_MASK = "places.id,places.displayName,places.formattedAddress"
DETAILS_MASK = (
    "nationalPhoneNumber,websiteUri,regularOpeningHours,addressComponents,formattedAddress"
)
TIMEOUT = (3, 6)
MAX_HITS = 5
PLACE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,255}$")
_PHONE_RE = re.compile(r"^[\d +()/-]{3,40}$")


class PlacesError(Exception):
    """Сбой Google (сеть, HTTP, формат). Текст — без ключа и без тела ответа."""


@dataclass(frozen=True)
class PlaceHit:
    place_id: str
    name: str
    address: str


@dataclass(frozen=True)
class PlaceData:
    place_id: str
    address: str = ""
    city: str = ""
    zip_code: str = ""
    phone: str = ""
    website: str = ""
    hours: dict = field(default_factory=dict)
    #: часы Google не уложились в нашу сетку (ночные, два интервала) — владелец проверит
    hours_partial: bool = False


def _clip(value, n: int) -> str:
    return " ".join(str(value or "").split())[:n]


def _request(method: str, url: str, mask: str, **kw):
    key = api_key()
    if not key:
        raise PlacesError("not configured")
    try:
        resp = requests.request(
            method,
            url,
            headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": mask},
            timeout=TIMEOUT,
            **kw,
        )
    except requests.RequestException as exc:
        raise PlacesError(type(exc).__name__) from None
    if resp.status_code >= 400:
        raise PlacesError(f"http {resp.status_code}")
    try:
        data = resp.json()
    except ValueError:
        raise PlacesError("bad json") from None
    if not isinstance(data, dict):
        raise PlacesError("bad json")
    return data


def search_places(query: str, city: str, *, lang: str = "de") -> list[PlaceHit]:
    text = _clip(f"{query} {city}", 120)
    data = _request(
        "POST",
        SEARCH_URL,
        SEARCH_MASK,
        json={
            "textQuery": text,
            "languageCode": lang,
            "regionCode": "DE",
            "maxResultCount": MAX_HITS,
        },
    )
    hits = []
    for raw in data.get("places") or []:
        if not isinstance(raw, dict):
            continue
        pid = str(raw.get("id") or "")
        if not PLACE_ID_RE.fullmatch(pid):
            continue
        name = raw.get("displayName")
        name = name.get("text") if isinstance(name, dict) else name
        hits.append(PlaceHit(pid, _clip(name, 120), _clip(raw.get("formattedAddress"), 255)))
        if len(hits) >= MAX_HITS:
            break
    return hits


def _address(components) -> tuple[str, str, str]:
    parts = {}
    for c in components if isinstance(components, list) else []:
        if not isinstance(c, dict):
            continue
        for t in c.get("types") or []:
            parts.setdefault(t, _clip(c.get("longText") or c.get("shortText"), 80))
    street = " ".join(x for x in (parts.get("route", ""), parts.get("street_number", "")) if x)
    city = parts.get("locality") or parts.get("postal_town", "")
    zip_code = parts.get("postal_code", "")
    line = ", ".join(x for x in (street, " ".join(y for y in (zip_code, city) if y)) if x)
    return _clip(line, 255), city, zip_code


def _hours(raw) -> tuple[dict, bool]:
    """Google `regularOpeningHours.periods` (day 0 = воскресенье) → наш {"0".."6": [o, c]}
    (0 = понедельник). Ночные смены и второй интервал дня не ложатся в сетку — отбрасываются."""
    from apps.tenants import openinghours

    periods = (raw or {}).get("periods") if isinstance(raw, dict) else None
    out, partial = {}, False
    for p in periods if isinstance(periods, list) else []:
        try:
            o, c = p["open"], p["close"]
            if o["day"] != c["day"]:
                partial = True
                continue
            wd = str((int(o["day"]) + 6) % 7)
            rng = [f"{int(o['hour']):02d}:{int(o.get('minute', 0)):02d}"]
            rng.append(f"{int(c['hour']):02d}:{int(c.get('minute', 0)):02d}")
        except (KeyError, TypeError, ValueError):
            partial = True
            continue
        if wd in out:
            partial = True
            continue
        out[wd] = rng
    clean = openinghours.normalize(out)
    return clean, partial or len(clean) != len(out)


def place_details(place_id: str, *, lang: str = "de") -> PlaceData:
    from urllib.parse import urlsplit

    if not PLACE_ID_RE.fullmatch(place_id or ""):
        raise PlacesError("bad id")
    data = _request(
        "GET",
        f"{_PLACES_API}/{quote(place_id, safe='')}",
        DETAILS_MASK,
        params={"languageCode": lang},
    )
    address, city, zip_code = _address(data.get("addressComponents"))
    phone = _clip(data.get("nationalPhoneNumber"), 40)
    raw_site = str(data.get("websiteUri") or "").strip()
    site = raw_site if len(raw_site) <= 200 else ""  # обрезанный URL — битая ссылка: не берём
    parts = urlsplit(site) if site else None
    if (
        not parts
        or parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
    ):
        site = ""
    hours, partial = _hours(data.get("regularOpeningHours"))
    return PlaceData(
        place_id=place_id,
        address=address or _clip(data.get("formattedAddress"), 255),
        city=city,
        zip_code=zip_code,
        phone=phone if _PHONE_RE.fullmatch(phone) else "",
        website=site,
        hours=hours,
        hours_partial=partial,
    )
