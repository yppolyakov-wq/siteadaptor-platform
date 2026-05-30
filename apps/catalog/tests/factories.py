import factory
from factory.django import DjangoModelFactory

from apps.catalog.models import Category, Product


class CategoryFactory(DjangoModelFactory):
    class Meta:
        model = Category

    name = factory.Sequence(lambda n: {"de": f"Kategorie {n}", "en": f"Category {n}"})
    slug = factory.Sequence(lambda n: f"category-{n}")
    sort_order = 0
    is_active = True


class ProductFactory(DjangoModelFactory):
    class Meta:
        model = Product

    name = factory.Sequence(lambda n: {"de": f"Produkt {n}", "en": f"Product {n}"})
    description = factory.LazyFunction(dict)
    base_price = "9.90"
    currency = "EUR"
    is_active = True
