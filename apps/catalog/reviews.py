"""A1/A2: отзывы о товаре — верификация покупателя и агрегаты рейтинга.

«Verified buyer only»: оставить отзыв может лишь тот, у кого есть заказ с этим
товаром (OrderItem) на его email. Заказы — отдельный модуль (orders); если он не
активен/таблиц нет, верификация безопасно возвращает False (никого не пускаем).
"""

from django.db.models import Avg, Count


def has_purchased(product, email: str) -> bool:
    """True, если по email есть незавершённо-отменённый заказ с этим товаром.

    Сравнение email без регистра. Любая ошибка (нет модуля orders/таблиц) → False —
    отзыв оставить нельзя, страница не падает.
    """
    email = (email or "").strip().lower()
    if not email:
        return False
    try:
        from apps.orders.models import OrderItem

        return (
            OrderItem.objects.filter(product=product, order__customer__email__iexact=email)
            .exclude(order__status="cancelled")
            .exists()
        )
    except Exception:  # noqa: BLE001 — orders может быть выключен; тогда верификации нет
        return False


def published_for(product):
    """Опубликованные отзывы товара (новые сверху) — для детальной страницы."""
    return product.reviews.filter(is_published=True)


def summary(product) -> dict:
    """Агрегат рейтинга товара: {avg: float|None, count: int} по опубликованным."""
    agg = product.reviews.filter(is_published=True).aggregate(avg=Avg("rating"), count=Count("id"))
    return {"avg": round(agg["avg"], 1) if agg["avg"] is not None else None, "count": agg["count"]}
