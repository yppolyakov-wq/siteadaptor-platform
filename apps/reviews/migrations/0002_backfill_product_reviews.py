"""UA4-4a: data-migration — перенос `catalog.ProductReview` → generic `Review`.

Копирует все существующие отзывы о товаре в единую модель (`entity_kind='product'`),
сохраняя опубликованность/таймстемпы. Логика — в `apps.reviews.backfill` (тот же код
покрыт тестом на боевых моделях). `ProductReview` не удаляем (не деструктивно; чтение
переключается на generic-модель во вьюхах).
"""

from django.db import migrations

from apps.reviews.backfill import copy_product_reviews


def forwards(apps, schema_editor):
    ProductReview = apps.get_model("catalog", "ProductReview")
    Review = apps.get_model("reviews", "Review")
    copy_product_reviews(ProductReview, Review)


def backwards(apps, schema_editor):
    Review = apps.get_model("reviews", "Review")
    Review.objects.filter(entity_kind="product").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("reviews", "0001_initial"),
        ("catalog", "0010_productreview"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
