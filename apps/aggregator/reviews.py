"""Агрегат рейтинга бизнеса по отзывам (G8 / G8a).

recompute_rating пересчитывает avg+count из опубликованных отзывов в
BusinessRating (денорм для звёзд в выдаче). ratings_for — пакетная выборка по
списку схем (карточки листингов, G8b).
"""

from decimal import Decimal

from django.db.models import Avg, Count

from .models import BusinessRating, BusinessReview


def recompute_rating(tenant_schema: str) -> None:
    agg = BusinessReview.objects.filter(
        tenant_schema=tenant_schema, status=BusinessReview.STATUS_PUBLISHED
    ).aggregate(avg=Avg("rating"), count=Count("id"))
    avg = round(agg["avg"], 2) if agg["avg"] is not None else Decimal("0")
    BusinessRating.objects.update_or_create(
        tenant_schema=tenant_schema,
        defaults={"avg_rating": avg, "review_count": agg["count"] or 0},
    )


def ratings_for(schemas) -> dict:
    """{tenant_schema: BusinessRating} для списка схем (звёзды на карточках)."""
    return {
        r.tenant_schema: r
        for r in BusinessRating.objects.filter(tenant_schema__in=set(schemas), review_count__gt=0)
    }


def attach_ratings(cards):
    """Прикрепить .business_rating к каждой карточке (G8b) — звёзды в выдаче."""
    ratings = ratings_for({c.tenant_schema for c in cards})
    for card in cards:
        card.business_rating = ratings.get(card.tenant_schema)
    return cards


def verified_emails(tenant_schema: str, emails) -> set:
    """Подмножество email'ов, у которых есть Customer в схеме бизнеса (G8).

    Customer создаётся при реальной сделке (бронь/заказ/запись/смета) → наличие =
    «Verifizierter Gast». Кросс-схемно (schema_context). Сравнение без регистра.
    Ошибки/пустой ввод → пустое множество (бейдж просто не показываем).
    """
    wanted = {e.strip().lower() for e in emails if e}
    if not wanted:
        return set()
    try:
        from django.db.models.functions import Lower
        from django_tenants.utils import schema_context

        from apps.promotions.models import Customer

        with schema_context(tenant_schema):
            found = (
                Customer.objects.annotate(le=Lower("email"))
                .filter(le__in=wanted)
                .values_list("le", flat=True)
            )
            return set(found)
    except Exception:  # noqa: BLE001 — бейдж необязателен, не роняем страницу
        return set()
