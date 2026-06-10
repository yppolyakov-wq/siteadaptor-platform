"""Track B2: денормализация флага Überraschungstüte в листинг агрегатора."""

import pytest

from apps.aggregator import tasks
from apps.aggregator.models import AggregatorListing
from apps.promotions.models import Promotion
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def test_surprise_flag_is_denormalized_to_listing():
    TenantFactory(schema_name="public", slug="x", name="X", city="Hilden", business_type="bakery")
    promo = Promotion.objects.create(
        status="active", title={"de": "Feierabend-Tüte"}, is_surprise=True
    )
    tasks.sync_listing("public", str(promo.id))
    listing = AggregatorListing.objects.get(promo_uuid=promo.id)
    assert listing.is_surprise is True
