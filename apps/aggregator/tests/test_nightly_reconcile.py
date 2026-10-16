"""T-8.26 п.3 (3c): ночная сверка снимка каталога города по всем схемам."""

from decimal import Decimal

import pytest
from django.conf import settings

from apps.aggregator import tasks
from apps.aggregator.models import AggregatorListing
from apps.catalog.models import Product
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def test_beat_entry_exists():
    entry = settings.CELERY_BEAT_SCHEDULE["reconcile-aggregator-nightly"]
    assert entry["task"] == "apps.aggregator.tasks.reconcile_aggregator_nightly"
    assert entry["schedule"] == 86400.0


def test_fans_out_one_task_per_tenant_with_spread(monkeypatch):
    TenantFactory(schema_name="public", slug="plat")
    a = TenantFactory(slug="a-biz")
    b = TenantFactory(slug="b-biz")
    calls = []
    monkeypatch.setattr(
        tasks.reconcile_aggregator_schema_job,
        "apply_async",
        lambda kwargs=None, countdown=None, **kw: calls.append((kwargs, countdown)),
    )
    monkeypatch.setattr(settings, "AGG_RECONCILE_SPREAD_S", 20)
    tasks.reconcile_aggregator_nightly()
    schemas = [k["tenant_schema"] for k, _ in calls]
    assert "public" not in schemas and {a.schema_name, b.schema_name} <= set(schemas)
    assert [c for _, c in calls] == [i * 20 for i in range(len(calls))]
    assert all(k["dedupe_key"].startswith(f"agg-nightly:{k['tenant_schema']}:") for k, _ in calls)


def test_reconcile_fixes_drift_after_bare_update():
    TenantFactory(schema_name="public", slug="walder", name="Walder", city="Solingen")
    product = Product.objects.create(
        name={"de": "Jacke"},
        base_price=Decimal("10.00"),
        images=[{"url": "/media/x.webp", "is_primary": True}],
        stock_quantity=0,
    )
    assert tasks.sync_product_listing("public", product.pk) == "upserted"
    row = AggregatorListing.objects.get(listing_kind="product", source_ref=str(product.pk))
    assert row.availability == "sold_out"
    Product.objects.filter(pk=product.pk).update(stock_quantity=5)  # мимо леджера и сигналов
    tasks.reconcile_schema("public")
    row.refresh_from_db()
    assert row.availability == ""
