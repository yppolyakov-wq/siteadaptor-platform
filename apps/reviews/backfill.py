"""UA4-4a: перенос существующих `catalog.ProductReview` в generic `Review`.

Функция параметризована классами моделей, чтобы её можно было вызвать И из
data-миграции (с историческими моделями `apps.get_model`), И из теста (с боевыми
моделями) — без дублирования логики. Идемпотентна: повторный прогон пропускает уже
перенесённые строки (по (entity_id, email)).
"""


def copy_product_reviews(ProductReview, Review):
    """Копирует все `ProductReview` в `Review` (`entity_kind='product'`), сохраняя
    опубликованность/таймстемпы и помечая перенесённые как `verified=True` (в старой
    модели хранились только прошедшие проверку покупателя). Возвращает число созданных.
    """
    already = set(Review.objects.filter(entity_kind="product").values_list("entity_id", "email"))
    src = list(ProductReview.objects.all())
    pending = [pr for pr in src if (pr.product_id, pr.email) not in already]
    if not pending:
        return 0
    rows = [
        Review(
            entity_kind="product",
            entity_id=pr.product_id,
            rating=pr.rating,
            author_name=pr.author_name,
            email=pr.email,
            comment=pr.comment,
            verified=True,
            is_published=pr.is_published,
        )
        for pr in pending
    ]
    created = Review.objects.bulk_create(rows)
    # Сохранить оригинальные created_at/updated_at (auto_now_add/auto_now иначе
    # перезапишут их на «сейчас» при bulk_create).
    src_map = {(pr.product_id, pr.email): pr for pr in pending}
    for obj in created:
        pr = src_map[(obj.entity_id, obj.email)]
        obj.created_at, obj.updated_at = pr.created_at, pr.updated_at
    Review.objects.bulk_update(created, ["created_at", "updated_at"])
    return len(created)
