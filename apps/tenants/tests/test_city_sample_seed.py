"""DCC: образцы китов города проходят сидинг, а фактические категории листингов совпадают
с предсказателем `validate.predicted_categories` (держит его честным)."""

import pytest

from apps.aggregator.models import AggregatorListing
from apps.aggregator.tasks import reconcile_schema
from apps.tenants import demo_kits
from apps.tenants.demo_city import businesses
from apps.tenants.demo_city.validate import predicted_categories
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

CITY_SAMPLE = ("sg_trattoria_lumetto", "sg_wuschelkopf", "sg_fachwerkblick")


@pytest.mark.parametrize("key", CITY_SAMPLE)
def test_sample_seed_matches_predicted_categories(key):
    biz = {b.key: b for b in businesses()}[key]
    tenant = TenantFactory(slug=f"city-{key}", name="City", auto_create_schema=True)
    from django_tenants.utils import schema_context

    with schema_context(tenant.schema_name):
        assert demo_kits.apply_kit(tenant, key) is True
    reconcile_schema(tenant.schema_name)
    rows = AggregatorListing.objects.filter(tenant_schema=tenant.schema_name)
    assert rows.exists()
    actual = {r.city_category for r in rows if r.city_category}
    assert actual == predicted_categories(biz), (actual, predicted_categories(biz))
    tenant.refresh_from_db()
    assert tenant.is_demo and tenant.district == biz.district
    # признаки акции доехали до листинга
    tagged = [o for o in biz.offers if o.tags]
    if tagged:
        promo_rows = rows.filter(listing_kind=AggregatorListing.KIND_PROMOTION)
        assert any(set(tagged[0].tags) <= set(r.city_tags or []) for r in promo_rows)
