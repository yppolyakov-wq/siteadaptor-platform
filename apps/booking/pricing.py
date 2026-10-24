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
    # UUID-pk назначается в __init__ → несохранённость определяет `_state.adding`;
    # у заглушек без модели (`SimpleNamespace` в тестах секций) вариантов нет.
    state = getattr(service, "_state", None)
    if state is None or state.adding or not getattr(service, "pk", None):
        return []
    return list(service.variants.filter(is_active=True).order_by("sort_order", "id"))


def resolve_variant(service, raw) -> tuple:
    """(вариант | None, ok). Пусто → базовая услуга (None): вариант — ЯВНЫЙ выбор,
    иначе любая ссылка без параметра (Finder, MCP, письма, акции) молча меняла бы цену
    и длину. Не активный вариант этой услуги / мусор → ok=False."""
    raw = (raw or "").strip()
    if not raw:
        return None, True
    for v in active_variants(service):
        if str(v.pk) == raw:
            return v, True
    return None, False


def is_stale_variant(service, raw) -> bool:
    """Вариант ЭТОЙ услуги, который выключили, или удалённый (UUID без строки):
    гостя со старой ссылкой возвращаем на выбор, а не в 404. Чужой вариант — подделка."""
    from uuid import UUID

    from .models import ServiceVariant

    try:
        uid = UUID(str(raw or "").strip())
    except ValueError:
        return False
    row = ServiceVariant.objects.filter(pk=uid).values_list("service_id", flat=True).first()
    return row is None or row == service.pk


def effective_minutes(service, variant) -> int:
    base = int(getattr(service, "duration_minutes", 0) or 0)
    delta = int(getattr(variant, "duration_delta_minutes", 0) or 0) if variant else 0
    return max(MIN_VARIANT_MINUTES, base + delta)


def variant_price_cents(service, day, variant, seasons=None) -> int:
    base = price_cents_for(service, day, seasons) if day is not None else service.price_cents
    delta = int(getattr(variant, "price_delta_cents", 0) or 0) if variant else 0
    return max(0, base + delta)


def promo_with_variant(hit, variant):
    """Цена акции «счастливых часов» с доплатой варианта (Р-1: акция на услугу,
    доплата за вариант остаётся). None — акции нет."""
    if hit is None:
        return None
    delta = int(getattr(variant, "price_delta_cents", 0) or 0) if variant else 0
    return max(0, int(hit[1]) + delta)


def with_active_variants(qs):
    """Prefetch активных вариантов (`to_attr="active_variants"`) — «ab»-цена карточки
    услуги без запроса на каждую услугу (листинги, блоки «Liste», выборки по id)."""
    from django.db.models import Prefetch

    from .models import ServiceVariant

    return qs.prefetch_related(
        Prefetch(
            "variants",
            queryset=ServiceVariant.objects.filter(is_active=True).order_by("sort_order", "id"),
            to_attr="active_variants",
        )
    )
