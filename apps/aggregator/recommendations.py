"""Рекомендации для выдачи агрегатора (P2.7+).

Без аналитики просмотров: «рекомендуем» = срочность предложения. ``ending_soon``
собирает то, что скоро закроется (акции с близким ends_at + события с близким
starts_at) — городская выдача и индекс показывают это рейлом «Endet bald», чтобы
повысить конверсию уходящих предложений. Размещения (stay) бессрочны → не сюда.
"""

from datetime import timedelta

from django.utils import timezone

from .models import AggregatorListing


def ending_soon(base_qs=None, *, days: int = 3, limit: int = 12) -> list:
    """Листинги, чьё окно скоро закрывается, в порядке срочности.

    base_qs — пул (по умолчанию все активные; порталы/город передают свой
    отфильтрованный). Акция входит по ends_at, событие — по starts_at; обе даты
    в окне [now, now+days]. Возвращает список (не QuerySet — два вида сливаем).
    """
    if base_qs is None:
        base_qs = AggregatorListing.objects.filter(is_active=True)
    now = timezone.now()
    soon = now + timedelta(days=days)

    promos = base_qs.filter(
        listing_kind=AggregatorListing.KIND_PROMOTION, ends_at__gte=now, ends_at__lte=soon
    )
    events = base_qs.filter(
        listing_kind=AggregatorListing.KIND_EVENT, starts_at__gte=now, starts_at__lte=soon
    )

    def _urgency(listing):
        # ближайшая релевантная дата (событие — старт, акция — конец)
        return (
            listing.starts_at
            if listing.listing_kind == AggregatorListing.KIND_EVENT
            else listing.ends_at
        )

    items = sorted([*promos, *events], key=_urgency)
    return items[:limit]
