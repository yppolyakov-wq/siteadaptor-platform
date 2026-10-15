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
    # T-8.7: округление до ~100 м — точнее не нужно, а произвольная точность раздувала бы
    # ключи кэша/журналы уникальными координатами.
    return round(lat, 3), round(lng, 3)


NEAREST_CAP = 3000


def nearest(qs, lat, lng, limit=50) -> list:
    """Листинги с координатами, отсортированные по дистанции (ближайшие сверху)."""
    out = []
    # Кап кандидатов: «рядом» по всей стране на /entdecken/ не должен тащить весь пул в Python.
    candidates = (
        qs.exclude(latitude__isnull=True)
        .exclude(longitude__isnull=True)
        .order_by("-pk")[:NEAREST_CAP]
    )
    for listing in candidates:
        listing.distance_km = round(
            haversine_km(lat, lng, float(listing.latitude), float(listing.longitude)), 1
        )
        out.append(listing)
    out.sort(key=lambda item: item.distance_km)
    return out[:limit]


RADIUS_CHOICES = (1, 2, 5, 10, 25)  # км, T-8.7 «im Umkreis» (Р-5: радиус — только фильтр)
RADIUS_CANDIDATE_CAP = 2000


def parse_radius(raw) -> int | None:
    """`?umkreis=` из RADIUS_CHOICES или None (мусор/отсутствие)."""
    try:
        value = int(str(raw or "").strip())
    except (TypeError, ValueError):
        return None
    return value if value in RADIUS_CHOICES else None


def bbox(lat: float, lng: float, km: float) -> tuple[float, float, float, float]:
    """(lat_min, lat_max, lng_min, lng_max) — грубый прямоугольник вокруг точки."""
    dlat = km / 111.0
    dlng = km / max(111.0 * math.cos(math.radians(lat)), 1e-6)
    return lat - dlat, lat + dlat, lng - dlng, lng + dlng


def within_radius(qs, lat: float, lng: float, km: int):
    """Листинги в радиусе: bounding-box в SQL, точная проверка haversine в Python,
    результат — тот же QuerySet через `pk__in` (пагинация и сортировки целы).
    Бизнес без координат в радиус не попадает (честно)."""
    lat_min, lat_max, lng_min, lng_max = bbox(lat, lng, km)
    candidates = (
        qs.order_by("pk")  # детерминированный срез при превышении капа
        .filter(
            latitude__gte=lat_min,
            latitude__lte=lat_max,
            longitude__gte=lng_min,
            longitude__lte=lng_max,
        )
        .values_list("pk", "latitude", "longitude")[:RADIUS_CANDIDATE_CAP]
    )
    keep = [
        pk
        for pk, plat, plng in candidates
        if haversine_km(lat, lng, float(plat), float(plng)) <= km
    ]
    return qs.filter(pk__in=keep)


def carry(lat, lng, radius_km=None) -> list[tuple[str, str]]:
    """Параметры точки для ссылок (НЕ в search.carry: координаты не должны попадать в
    журнал поиска T-8.21). Округление до 3 знаков (~100 м) — точнее не нужно."""
    if lat is None or lng is None:
        return []
    out = [("lat", f"{lat:.3f}"), ("lng", f"{lng:.3f}")]
    if radius_km:
        out.append(("umkreis", str(radius_km)))
    return out


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
        return card.portal_url

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
