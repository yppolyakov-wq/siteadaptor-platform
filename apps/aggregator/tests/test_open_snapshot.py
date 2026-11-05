"""PH-0: общий снимок «открыто сейчас» — один запрос, паритет фильтра и карточек."""

from types import SimpleNamespace

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.aggregator import views
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ALWAYS = {str(d): [["00:00", "23:59"]] for d in range(7)}


def test_snapshot_is_one_query_and_feeds_both_helpers():
    a = TenantFactory(schema_name="snap_a", slug="snap-a", opening_hours_structured=ALWAYS)
    b = TenantFactory(schema_name="snap_b", slug="snap-b", opening_hours_structured={})
    with CaptureQueriesContext(connection) as ctx:
        snap = views.open_snapshot({a.schema_name, b.schema_name})
    assert len(ctx.captured_queries) == 1
    assert views._open_now_schemas(set(), snapshot=snap) == views._open_now_schemas(
        {a.schema_name, b.schema_name}
    )
    cards = [
        SimpleNamespace(tenant_schema=a.schema_name),
        SimpleNamespace(tenant_schema=b.schema_name),
    ]
    with CaptureQueriesContext(connection) as ctx:
        views._attach_open_status(cards, snapshot=snap)
    assert len(ctx.captured_queries) == 0
    fresh = [
        SimpleNamespace(tenant_schema=a.schema_name),
        SimpleNamespace(tenant_schema=b.schema_name),
    ]
    views._attach_open_status(fresh)
    for x, y in zip(cards, fresh, strict=True):
        assert (x.has_hours, x.open_now, x.open_until, x.opens_next) == (
            y.has_hours,
            y.open_now,
            y.open_until,
            y.opens_next,
        )
