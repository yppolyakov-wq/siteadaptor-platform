"""Тесты моделей каталога (TENANT-схема — гоняются в public при тестах)."""

import pytest

from apps.catalog.models import Category, Product
from apps.catalog.tests.factories import CategoryFactory, ProductFactory


@pytest.mark.django_db
def test_product_str_uses_i18n_name():
    p = ProductFactory(name={"de": "Apfelstrudel", "en": "Apple strudel"})
    assert "Apfelstrudel" in str(p) or "Apple" in str(p)


@pytest.mark.django_db
def test_category_str_falls_back_to_slug():
    c = CategoryFactory(name={}, slug="baeckerei")
    assert str(c) == "baeckerei"


@pytest.mark.django_db
def test_product_soft_delete_hides_from_default_manager():
    p = ProductFactory()
    pk = p.pk
    p.delete()  # soft
    assert not Product.objects.filter(pk=pk).exists()
    assert Product.all_objects.filter(pk=pk).exists()
    p.restore()
    assert Product.objects.filter(pk=pk).exists()


@pytest.mark.django_db
def test_primary_image_selection():
    p = ProductFactory(
        images=[
            {"url": "a.jpg", "is_primary": False},
            {"url": "b.jpg", "is_primary": True},
        ]
    )
    assert p.primary_image["url"] == "b.jpg"


@pytest.mark.django_db
def test_primary_image_defaults_to_first():
    p = ProductFactory(images=[{"url": "a.jpg"}, {"url": "b.jpg"}])
    assert p.primary_image["url"] == "a.jpg"
    assert ProductFactory(images=[]).primary_image is None


@pytest.mark.django_db
def test_category_slug_unique_among_alive_only():
    CategoryFactory(slug="dup")
    dead = CategoryFactory(slug="dup2")
    dead.delete()  # soft-deleted, slug освобождён
    # переиспользуем slug удалённой записи — конфликта быть не должно
    CategoryFactory(slug="dup2")
    assert Category.objects.filter(slug="dup2").count() == 1


@pytest.mark.django_db
def test_product_category_relation():
    cat = CategoryFactory()
    p = ProductFactory(category=cat)
    assert p in cat.products.all()
