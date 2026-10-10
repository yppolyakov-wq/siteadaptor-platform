import pytest

from apps.aggregator import tasks
from apps.aggregator.models import AggregatorListing
from apps.promotions.models import Promotion
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def test_reconcile_syncs_active_and_prunes_stale():
    TenantFactory(schema_name="public", slug="x", name="X", city="Hilden", business_type="bakery")
    Promotion.objects.create(status="active", title={"de": "A1"})
    Promotion.objects.create(status="active", title={"de": "A2"})
    ended = Promotion.objects.create(status="ended", title={"de": "E"})
    # устаревший листинг завершённой акции (как будто остался от прошлого)
    AggregatorListing.objects.create(
        tenant_schema="public",
        tenant_slug="x",
        business_name="X",
        promo_uuid=ended.id,
        title={"de": "E"},
        detail_url="https://x.siteadaptor.de/p/e/",
    )

    n = tasks.reconcile_schema("public")

    # T-8.11: + карточка самого предприятия (одна на бизнес).
    assert n == 3
    assert (
        AggregatorListing.objects.filter(tenant_schema="public", listing_kind="promotion").count()
        == 2
    )
    assert AggregatorListing.objects.filter(listing_kind="business").count() == 1
    assert not AggregatorListing.objects.filter(promo_uuid=ended.id).exists()
