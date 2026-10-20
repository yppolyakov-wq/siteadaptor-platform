"""T-8.14: охват портала — ОДНА точка истины для всех путей чтения.

Портал ограничивает общий пул каталога города городом, типом бизнеса и (T-8.14) темой:
набором признаков (`theme_tags`, «любой из») и разделов/категорий (`theme_categories`,
«любой из»); между осями — И, пустая ось ничего не ограничивает. Карточка бизнеса
(`KIND_BUSINESS`) обычно без признаков, поэтому входит в тему, если подходит сама ИЛИ у
этого бизнеса есть предложение в теме — иначе страницы бизнесов на тематическом портале
исчезли бы.

Раньше пара `city` + `business_type` передавалась в `listings_for(...)` руками примерно в
тридцати местах; замок `test_portal_scope_single_entry` не даёт этому вернуться.
"""

from __future__ import annotations

from django.db.models import Q

_UNSET = object()


def theme_tags(portal) -> tuple[str, ...]:
    from apps.core import city_categories

    raw = getattr(portal, "theme_tags", None) or []
    return tuple(city_categories.normalize_tags(raw))


def theme_category_keys(portal) -> tuple[str, ...]:
    """Разделы темы раскрыты в категории (как `?kat=` раздела)."""
    from apps.core import city_categories

    keys: list[str] = []
    for value in getattr(portal, "theme_categories", None) or []:
        for key in city_categories.keys_for_filter(str(value)):
            if key not in keys:
                keys.append(key)
    return tuple(keys)


def has_theme(portal) -> bool:
    return bool(portal is not None and (theme_tags(portal) or theme_category_keys(portal)))


def _theme_q(portal) -> Q | None:
    tags, cats = theme_tags(portal), theme_category_keys(portal)
    if not tags and not cats:
        return None
    q = Q()
    if cats:
        q &= Q(city_category__in=cats)
    if tags:
        any_tag = Q()
        for tag in tags:
            any_tag |= Q(city_tags__contains=[tag])
        q &= any_tag
    return q


def apply(qs, portal):
    """Наложить тему портала на queryset листингов (без темы — тот же queryset)."""
    q = _theme_q(portal)
    if q is None:
        return qs
    from .models import AggregatorListing

    in_theme = qs.filter(q).exclude(listing_kind=AggregatorListing.KIND_BUSINESS)
    schemas = in_theme.order_by().values("tenant_schema")
    return qs.filter(q | Q(listing_kind=AggregatorListing.KIND_BUSINESS, tenant_schema__in=schemas))


def pool(portal, *, city=_UNSET, business_type=_UNSET, include_demo=_UNSET, **filters):
    """Пул портала: город, тип, демо и тема. Явные `city`/`business_type` перекрывают
    значения портала (чип свободной оси, подписка без города в портале); тема — всегда."""
    from .views import listings_for

    if portal is None:
        return listings_for(
            city=None if city is _UNSET else city,
            business_type=None if business_type is _UNSET else business_type,
            include_demo=True if include_demo is _UNSET else include_demo,
            **filters,
        )
    qs = listings_for(
        city=(portal.city or None) if city is _UNSET else city,
        business_type=(portal.business_type or None) if business_type is _UNSET else business_type,
        include_demo=bool(portal.show_demo) if include_demo is _UNSET else include_demo,
        **filters,
    )
    return apply(qs, portal)


def contains(listing, portal) -> bool:
    """Листинг в границах портала (страница предложения, переход к продавцу)."""
    if portal is None:
        return True
    if listing.is_demo and not portal.show_demo:
        return False
    if portal.city and (listing.city or "").lower() != portal.city.lower():
        return False
    if portal.business_type and listing.business_type != portal.business_type:
        return False
    if not has_theme(portal):
        return True
    from .models import AggregatorListing

    return apply(AggregatorListing.objects.filter(pk=listing.pk), portal).exists()


def contains_tenant(tenant, portal) -> bool:
    """Бизнес в границах портала (страница компании, отзывы о бизнесе)."""
    if portal is None:
        return True
    if tenant.is_demo and not portal.show_demo:
        return False
    if portal.city and (tenant.city or "").lower() != portal.city.lower():
        return False
    if portal.business_type and tenant.business_type != portal.business_type:
        return False
    if not has_theme(portal):
        return True
    return pool(portal).filter(tenant_schema=tenant.schema_name).exists()


def fingerprint(portal) -> str:
    """Ключ кэша охвата: портал с другой темой не делит кэш с прежней."""
    if portal is None:
        return "-"
    parts = [
        str(getattr(portal, "pk", "") or ""),
        "1" if getattr(portal, "show_demo", False) else "0",
        getattr(portal, "business_type", "") or "",
        ",".join(theme_tags(portal)),
        ",".join(theme_category_keys(portal)),
    ]
    return ":".join(parts)
