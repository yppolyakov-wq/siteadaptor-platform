"""GK-11: Google-рейтинг бизнеса — Places API (New), только rating/userRatingCount.

Ключ — платформенный (шифрованный стор → env-фолбэк GOOGLE_PLACES_API_KEY,
external-integrations-backlog: включённый Places API + billing на владельце).
FieldMask из двух полей = дешёвый Basic-SKU; URL платформенный (SSRF-гард не
нужен — owner-ввод только place_id, он уходит в path через quote)."""

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
