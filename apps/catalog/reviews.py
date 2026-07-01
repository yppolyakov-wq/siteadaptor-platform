"""A1/A2: отзывы о товаре — верификация покупателя и агрегаты рейтинга.

«Verified buyer only»: оставить отзыв может лишь тот, у кого есть заказ с этим
товаром (OrderItem) на его email. Заказы — отдельный модуль (orders); если он не
активен/таблиц нет, верификация безопасно возвращает False (никого не пускаем).

UA4-4a: хранение/агрегаты отзывов перенесены в generic-модель `apps.reviews.Review`
(`entity_kind='product'`). Здесь остаётся product-специфичная верификация
покупателя (`has_purchased`) + тонкие product-обёртки над `apps.reviews.services`.
"""

from apps.reviews import services as review_services


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
    return review_services.published_for(review_services.Review.KIND_PRODUCT, product.pk)


def summary(product) -> dict:
    """Агрегат рейтинга товара: {avg: float|None, count: int} по опубликованным."""
    return review_services.summary(review_services.Review.KIND_PRODUCT, product.pk)
