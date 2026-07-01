"""UA4-4a: generic `Review` — data-migration из `ProductReview`, агрегаты, fail-closed."""

import pytest

from apps.catalog.models import ProductReview
from apps.catalog.tests.factories import ProductFactory
from apps.reviews import services as review_services
from apps.reviews.backfill import copy_product_reviews
from apps.reviews.models import Review

pytestmark = pytest.mark.django_db


# --- data-migration: перенос без потерь ------------------------------------
def test_backfill_copies_all_fields_and_marks_verified():
    p1, p2 = ProductFactory(), ProductFactory()
    ProductReview.objects.create(
        product=p1, rating=5, author_name="Anna", email="a@t.de", comment="Top"
    )
    ProductReview.objects.create(
        product=p2, rating=2, author_name="Bea", email="b@t.de", is_published=False
    )
    Review.objects.all().delete()  # чистый старт (в тест-БД миграция уже прошла на пустой БД)

    n = copy_product_reviews(ProductReview, Review)

    assert n == 2
    assert Review.objects.filter(entity_kind="product").count() == 2
    r1 = Review.objects.get(entity_kind="product", entity_id=p1.pk, email="a@t.de")
    assert r1.rating == 5 and r1.author_name == "Anna" and r1.comment == "Top"
    assert r1.verified is True and r1.is_published is True
    r2 = Review.objects.get(entity_kind="product", entity_id=p2.pk, email="b@t.de")
    assert r2.is_published is False and r2.verified is True  # опубликованность сохранена


def test_backfill_preserves_timestamps():
    p = ProductFactory()
    pr = ProductReview.objects.create(product=p, rating=4, author_name="A", email="a@t.de")
    Review.objects.all().delete()

    copy_product_reviews(ProductReview, Review)

    r = Review.objects.get(entity_kind="product", entity_id=p.pk)
    assert r.created_at == pr.created_at  # не перезаписан на «сейчас»


def test_backfill_idempotent():
    p = ProductFactory()
    ProductReview.objects.create(product=p, rating=3, author_name="A", email="a@t.de")
    Review.objects.all().delete()

    assert copy_product_reviews(ProductReview, Review) == 1
    assert copy_product_reviews(ProductReview, Review) == 0  # второй прогон — ничего
    assert Review.objects.filter(entity_kind="product").count() == 1


# --- агрегаты ---------------------------------------------------------------
def test_summary_averages_published_only():
    p = ProductFactory()
    Review.objects.create(
        entity_kind="product", entity_id=p.pk, rating=5, author_name="A", email="a@t.de"
    )
    Review.objects.create(
        entity_kind="product", entity_id=p.pk, rating=3, author_name="B", email="b@t.de"
    )
    Review.objects.create(
        entity_kind="product",
        entity_id=p.pk,
        rating=1,
        author_name="C",
        email="c@t.de",
        is_published=False,
    )
    assert review_services.summary("product", p.pk) == {"avg": 4.0, "count": 2}


def test_summary_empty():
    p = ProductFactory()
    assert review_services.summary("product", p.pk) == {"avg": None, "count": 0}


def test_bulk_summary_keyed_by_entity_id():
    p1, p2 = ProductFactory(), ProductFactory()
    Review.objects.create(
        entity_kind="product", entity_id=p1.pk, rating=5, author_name="A", email="a@t.de"
    )
    Review.objects.create(
        entity_kind="product", entity_id=p1.pk, rating=3, author_name="B", email="b@t.de"
    )
    Review.objects.create(
        entity_kind="product", entity_id=p2.pk, rating=4, author_name="C", email="c@t.de"
    )
    out = review_services.bulk_summary("product", [p1.pk, p2.pk])
    assert out[p1.pk]["count"] == 2 and out[p1.pk]["avg"] == 4.0
    assert out[p2.pk]["count"] == 1


def test_published_for_excludes_hidden_and_other_entities():
    p1, p2 = ProductFactory(), ProductFactory()
    Review.objects.create(
        entity_kind="product", entity_id=p1.pk, rating=5, author_name="A", email="a@t.de"
    )
    Review.objects.create(
        entity_kind="product",
        entity_id=p1.pk,
        rating=1,
        author_name="H",
        email="h@t.de",
        is_published=False,
    )
    Review.objects.create(
        entity_kind="product", entity_id=p2.pk, rating=4, author_name="B", email="b@t.de"
    )
    got = list(review_services.published_for("product", p1.pk))
    assert len(got) == 1 and got[0].author_name == "A"


# --- верификация: fail-closed ----------------------------------------------
def test_is_verified_buyer_unknown_kind_is_false():
    p = ProductFactory()
    # неизвестный/непривязанный kind → нет верификатора → False (никого не пускаем)
    assert review_services.is_verified_buyer("service", p, "x@t.de") is False
    assert review_services.is_verified_buyer("stay", p, "x@t.de") is False


def test_is_verified_buyer_product_without_order_is_false():
    p = ProductFactory()
    assert review_services.is_verified_buyer("product", p, "nobody@t.de") is False
