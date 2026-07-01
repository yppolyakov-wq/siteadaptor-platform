"""UA4-4a: агрегаты и верификация для generic-модели `Review`.

Читатели витрины/списка идут сюда (не в per-модельные хелперы). Верификация
покупателя — per-kind адаптер, **fail-closed**: неизвестный/выключенный kind → False.
"""

from django.db.models import Avg, Count

from apps.reviews.models import Review


def published_for(entity_kind, entity_id):
    """Опубликованные отзывы сущности (новые сверху) — для детальной страницы."""
    return Review.objects.filter(entity_kind=entity_kind, entity_id=entity_id, is_published=True)


def summary(entity_kind, entity_id) -> dict:
    """Агрегат рейтинга сущности: {avg: float|None, count: int} по опубликованным."""
    agg = Review.objects.filter(
        entity_kind=entity_kind, entity_id=entity_id, is_published=True
    ).aggregate(avg=Avg("rating"), count=Count("id"))
    return {
        "avg": round(agg["avg"], 1) if agg["avg"] is not None else None,
        "count": agg["count"],
    }


def bulk_summary(entity_kind, entity_ids) -> dict:
    """{entity_id: {avg, count}} одним запросом — для списков/каталога без N+1."""
    rows = (
        Review.objects.filter(
            entity_kind=entity_kind, entity_id__in=list(entity_ids), is_published=True
        )
        .values("entity_id")
        .annotate(avg=Avg("rating"), count=Count("id"))
    )
    return {r["entity_id"]: {"avg": r["avg"], "count": r["count"]} for r in rows}


def is_verified_buyer(entity_kind, obj, email) -> bool:
    """Per-kind проверка «покупал ли этот email». Fail-closed: нет верификатора → False."""
    verifier = _verifier_for(entity_kind)
    return bool(verifier and verifier(obj, email))


def _verifier_for(entity_kind):
    """Ленивая привязка верификатора (избегаем циклов импорта между апп)."""
    if entity_kind == Review.KIND_PRODUCT:
        from apps.catalog.reviews import has_purchased

        return has_purchased
    return None
