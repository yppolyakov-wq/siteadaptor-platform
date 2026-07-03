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
    """Ленивая привязка per-kind верификатора (избегаем циклов импорта между апп).

    Каждый верификатор — `(obj, email) -> bool`, сам fail-closed (модуль/таблицы
    недоступны → False). Неизвестный/непривязанный kind → None → отзыв запрещён."""
    if entity_kind == Review.KIND_PRODUCT:
        from apps.catalog.reviews import has_purchased

        return has_purchased
    if entity_kind == Review.KIND_SERVICE:
        from apps.booking.reviews import has_booked

        return has_booked
    if entity_kind == Review.KIND_STAY:
        from apps.stays.reviews import has_stayed

        return has_stayed
    if entity_kind == Review.KIND_EVENT:
        from apps.events.reviews import has_ticket

        return has_ticket
    return None


def owner_overview() -> dict:
    """CM-6.3: сводка для кабинета «Bewertungen» текущей схемы: общий avg/count
    (по опубликованным), разбивка по kind, счётчики скрытых и без ответа."""
    from django.db.models import Q

    published = Review.objects.filter(is_published=True)
    agg = published.aggregate(avg=Avg("rating"), count=Count("id"))
    by_kind = {
        r["entity_kind"]: {"avg": round(r["avg"], 1), "count": r["count"]}
        for r in published.values("entity_kind").annotate(avg=Avg("rating"), count=Count("id"))
    }
    return {
        "avg": round(agg["avg"], 1) if agg["avg"] is not None else None,
        "count": agg["count"],
        "by_kind": by_kind,
        "hidden": Review.objects.filter(is_published=False).count(),
        "unanswered": Review.objects.filter(is_published=True)
        .filter(Q(reply_text="") | Q(reply_text__isnull=True))
        .count()
        if hasattr(Review, "reply_text")
        else None,
    }


def entity_labels(reviews) -> dict:
    """CM-6.1: {(kind, id): подпись сущности} балком, fail-soft (удалённая → «—»).

    Review хранит только UUID — кабинету нужно человекочитаемое имя."""
    wanted = {}
    for r in reviews:
        wanted.setdefault(r.entity_kind, set()).add(r.entity_id)
    labels = {}
    loaders = {
        "product": ("apps.catalog.models", "Product"),
        "service": ("apps.booking.models", "Service"),
        "stay": ("apps.stays.models", "StayUnit"),
        "event": ("apps.events.models", "Event"),
    }
    for kind, ids in wanted.items():
        spec = loaders.get(kind)
        if spec is None:
            continue
        try:
            import importlib

            model = getattr(importlib.import_module(spec[0]), spec[1])
            for obj in model.objects.filter(pk__in=ids):
                labels[(kind, obj.pk)] = str(obj)
        except Exception:  # noqa: BLE001 — домен не валит кабинет отзывов
            continue
    return labels
