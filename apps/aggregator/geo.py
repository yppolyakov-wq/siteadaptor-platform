"""Гео для агрегатора (G8c): дистанция, разбор координат, ближайшие, точки карты.

Координаты денормализованы на AggregatorListing (sync_listing из Tenant). Карта —
Leaflet/OSM (без API-ключа); «In meiner Nähe» — геолокация браузера → ?lat=&lng=
→ сортировка по haversine (в памяти, по выборке города/портала — объём скромный).
"""

import math


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    """Дистанция по большому кругу, км."""
    radius = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def parse_latlng(request):
    """(lat, lng) из ?lat=&lng= или (None, None). Валидируем диапазон."""
    try:
        lat = float(request.GET["lat"])
        lng = float(request.GET["lng"])
    except (KeyError, ValueError, TypeError):
        return None, None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None, None
    return lat, lng


def nearest(qs, lat, lng, limit=50) -> list:
    """Листинги с координатами, отсортированные по дистанции (ближайшие сверху)."""
    out = []
    for listing in qs.exclude(latitude__isnull=True).exclude(longitude__isnull=True):
        listing.distance_km = round(
            haversine_km(lat, lng, float(listing.latitude), float(listing.longitude)), 1
        )
        out.append(listing)
    out.sort(key=lambda item: item.distance_km)
    return out[:limit]


def map_points(cards) -> list:
    """[{lat, lng, title, url, featured}] для маркеров карты (только карточки с
    координатами). featured — оплаченная позиция: попап обязан нести пометку
    «Anzeige» (UWG §5a, D2.1 — паритет с карточками `_cards.html`), а клик идёт
    через счётчик (D2.3; fail-safe на detail_url, если имя вне urlconf)."""
    from django.urls import NoReverseMatch, reverse

    def _url(card):
        if card.is_featured_now:
            try:
                return reverse("aggregator-featured-click", args=[card.pk])
            except NoReverseMatch:
                pass
        return card.detail_url

    return [
        {
            "lat": float(card.latitude),
            "lng": float(card.longitude),
            "title": card.title_text,
            "url": _url(card),
            "featured": bool(card.is_featured_now),
        }
        for card in cards
        if card.latitude is not None and card.longitude is not None
    ]
