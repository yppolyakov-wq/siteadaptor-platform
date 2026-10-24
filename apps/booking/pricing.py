"""HF-5: цена услуги на конкретную дату (сезонные тарифы).

Приоритет: `ServiceSeasonRate` (диапазон дат) → базовая цена услуги. Зеркало
`stays.pricing.nightly_price_cents`; отдельный модуль, чтобы цена считалась в
ОДНОМ месте — им пользуются и витрина (показ), и приём брони (что списываем).
"""


def price_cents_for(service, day, seasons=None) -> int:
    """Цена услуги на день `day` в центах (базовая, если сезона нет)."""
    if day is None:
        return service.price_cents
    seasons = service.season_rates.all() if seasons is None else seasons
    for rate in seasons:
        if rate.start_date <= day <= rate.end_date:
            return rate.price_cents
    return service.price_cents


def season_label_for(service, day, seasons=None) -> str:
    """Подпись сезона для дня («Feiertage») или "" — для честного показа цены."""
    if day is None:
        return ""
    seasons = service.season_rates.all() if seasons is None else seasons
    for rate in seasons:
        if rate.start_date <= day <= rate.end_date:
            return rate.label
    return ""


# --- KA-12 E4.4b: варианты услуги -------------------------------------------------
MIN_VARIANT_MINUTES = 5


def active_variants(service) -> list:
    """Активные варианты услуги по порядку — из prefetch `active_variants`, если он есть."""
    cached = getattr(service, "active_variants", None)
    if cached is not None:
        return list(cached)
    if not getattr(service, "pk", None):
        return []
    return list(service.variants.filter(is_active=True).order_by("sort_order", "id"))


def resolve_variant(service, raw) -> tuple:
    """(вариант | None, ok). Пусто → первый активный (или None без вариантов);
    чужой/выключенный/мусор → ok=False (витрина отвечает 404 — ссылки строит сервер)."""
    variants = active_variants(service)
    raw = (raw or "").strip()
    if not raw:
        return (variants[0] if variants else None), True
    for v in variants:
        if str(v.pk) == raw:
            return v, True
    return None, False


def effective_minutes(service, variant) -> int:
    base = int(getattr(service, "duration_minutes", 0) or 0)
    delta = int(getattr(variant, "duration_delta_minutes", 0) or 0) if variant else 0
    return max(MIN_VARIANT_MINUTES, base + delta)


def variant_price_cents(service, day, variant, seasons=None) -> int:
    base = price_cents_for(service, day, seasons) if day is not None else service.price_cents
    delta = int(getattr(variant, "price_delta_cents", 0) or 0) if variant else 0
    return max(0, base + delta)
