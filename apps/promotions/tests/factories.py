import factory
from factory.django import DjangoModelFactory

from apps.promotions.models import Customer, Promotion


class CustomerFactory(DjangoModelFactory):
    class Meta:
        model = Customer

    name = factory.Sequence(lambda n: f"Kunde {n}")
    email = factory.Sequence(lambda n: f"kunde{n}@test.de")


class PromotionFactory(DjangoModelFactory):
    class Meta:
        model = Promotion

    title = factory.Sequence(lambda n: {"de": f"Aktion {n}", "en": f"Promo {n}"})
    description = factory.LazyFunction(dict)
    promo_type = "reservation"
    status = "active"
    available_quantity = 10
    max_per_customer = 5
    reservation_ttl_hours = 24
    auto_confirm = False
