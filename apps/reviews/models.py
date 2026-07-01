"""UA4-4a (U-A): единая generic-модель отзыва о продаваемой сущности.

Заменяет per-модельный `catalog.ProductReview` единым `Review`, адресуемым по
(`entity_kind`, `entity_id`) — товар/услуга/номер/событие. Читатели витрины и
агрегаты — `apps.reviews.services`; верификация покупателя — per-kind, fail-closed.
"""

from django.db import models

from apps.core.models import TimestampedModel


class Review(TimestampedModel):
    """Отзыв о продаваемой сущности (TENANT-схема).

    Generic по (`entity_kind`, `entity_id`) вместо FK на конкретную модель, чтобы
    один движок отзывов/агрегатов/JSON-LD работал для всех архетипов (протокол
    `SellableEntity`). Оставлять может лишь верифицированный покупатель (проверка
    per-kind во вьюхе); `verified` фиксирует этот факт на момент подачи. Один отзыв
    на (kind, id, email); повтор обновляет. Владелец может скрыть
    (`is_published=False`) — лёгкая модерация. Агрегаты avg/count —
    `apps.reviews.services`.
    """

    KIND_PRODUCT = "product"
    KIND_SERVICE = "service"
    KIND_STAY = "stay"
    KIND_EVENT = "event"
    ENTITY_KINDS = [
        (KIND_PRODUCT, "Product"),
        (KIND_SERVICE, "Service"),
        (KIND_STAY, "Stay"),
        (KIND_EVENT, "Event"),
    ]

    entity_kind = models.CharField(max_length=16, choices=ENTITY_KINDS)
    entity_id = models.UUIDField()  # все продаваемые сущности — UUID-PK (TimestampedModel)
    rating = models.PositiveSmallIntegerField()  # 1..5 (валидируется во вьюхе)
    author_name = models.CharField(max_length=120)
    email = models.EmailField()
    comment = models.TextField(blank=True)
    verified = models.BooleanField(default=True)  # был верифицированным покупателем при подаче
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["entity_kind", "entity_id", "email"],
                name="review_entity_email_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["entity_kind", "entity_id", "is_published"],
                name="review_entity_pub_idx",
            ),
        ]

    def __str__(self):
        return f"{self.entity_kind}:{self.entity_id}: {self.rating}★ ({self.author_name})"

    @property
    def stars(self) -> str:
        return "★" * self.rating + "☆" * (5 - self.rating)
