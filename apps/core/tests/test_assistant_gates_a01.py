"""AIS-A A-0 срез A0.1: единые гейты — помощник зовёт их, а не повторяет (замки паритета)."""

import itertools
from types import SimpleNamespace

import pytest

from apps.aggregator import visibility
from apps.core import readiness
from apps.core.storefront_state import hidden_reasons
from apps.orders.public_views import orders_active
from apps.tenants.tests.factories import TenantFactory

FLAGS = {
    "is_active": (True, False),
    "subscription_status": ("active", visibility.SUSPENDED),
    "email_pending": (False, True),
    "in_city_catalog": (True, False),
    "is_internal": (False, True),
    "published_at": ("2026-01-01", None),
}


def _matrix():
    keys = list(FLAGS)
    for values in itertools.product(*(FLAGS[k] for k in keys)):
        yield dict(zip(keys, values, strict=True))


def test_listable_is_exactly_no_withheld_reasons():
    for flags in _matrix():
        tenant = SimpleNamespace(**flags)
        reasons = visibility.withheld_reasons(tenant)
        assert visibility.listable(tenant) is (not reasons), flags
        expected = {
            "inactive": not flags["is_active"],
            "suspended": flags["subscription_status"] == visibility.SUSPENDED,
            "email_pending": flags["email_pending"],
            "unpublished": flags["published_at"] is None,
            "operator_off": not flags["in_city_catalog"],
            "internal": flags["is_internal"],
        }
        assert set(reasons) == {k for k, v in expected.items() if v}, flags
    assert visibility.withheld_reasons(None) == ["inactive"]


@pytest.mark.django_db
def test_withheld_schemas_agrees_with_withheld_reasons():
    from django.utils import timezone

    tenants = []
    for i, flags in enumerate(
        [
            {},
            {"is_active": False},
            {"subscription_status": visibility.SUSPENDED},
            {"email_pending": True},
            {"in_city_catalog": False},
            {"is_internal": True},
            {"published_at": None},
        ]
    ):
        flags.setdefault("published_at", timezone.now())
        tenants.append(TenantFactory(schema_name=f"wh{i}", slug=f"wh{i}", **flags))
    withheld = set(visibility.withheld_schemas().values_list("schema_name", flat=True))
    for tenant in tenants:
        assert (tenant.schema_name in withheld) is bool(visibility.withheld_reasons(tenant))


def test_hidden_reasons_codes():
    t = SimpleNamespace(schema_name="shop", email_pending=True, published_at=None)
    assert hidden_reasons(t) == ["email_pending", "unpublished"]
    assert hidden_reasons(SimpleNamespace(schema_name="shop", email_pending=False)) == []
    assert hidden_reasons(SimpleNamespace(schema_name="public", email_pending=True)) == []
    assert hidden_reasons(None) == []


def test_orders_active_is_the_module_gate():
    assert orders_active(None) is False
    on = SimpleNamespace(is_module_active=lambda key: key == "orders")
    off = SimpleNamespace(is_module_active=lambda key: False)
    assert orders_active(on) is True and orders_active(off) is False


def test_where_names_an_unpublished_site():
    from apps.promotions.where import _catalog_reason

    tenant = SimpleNamespace(**{**{k: v[0] for k, v in FLAGS.items()}, "published_at": None})
    assert "veröffentlichen" in str(_catalog_reason(tenant))
    tenant.published_at, tenant.email_pending = "x", True
    assert "E-Mail" in str(_catalog_reason(tenant))  # приоритет прежний: почта первой


def _items(monkeypatch, checks):
    items = tuple(
        readiness.Item(f"t{i}", "", readiness.MUST, f"T{i}", "settings", check)
        for i, check in enumerate(checks)
    )
    monkeypatch.setattr(readiness, "REGISTRY", items)
    monkeypatch.setattr(readiness, "_active_direction_keys", lambda t: set())


def test_unknown_on_error_also_marks_items_that_read_a_failed_memoized_fact(monkeypatch):
    tenant = SimpleNamespace(schema_name="public")

    def boom():
        raise RuntimeError("db down")

    def first(t, f):
        return bool(f.get("shared", boom))

    _items(monkeypatch, [first, first, lambda t, f: False])
    monkeypatch.setattr(readiness.Facts, "in_schema", lambda self: True)
    rows = readiness.items_for(tenant, unknown_on_error=True)
    assert [r["done"] for r in rows] == [None, None, False]
    # Гейт продажи остаётся fail-open: по умолчанию сбой = True.
    del tenant._readiness_facts
    assert [r["done"] for r in readiness.items_for(tenant)] == [True, True, False]


def test_palette_tag_uses_the_shared_function(monkeypatch):
    from apps.core import nav_registry
    from apps.core.templatetags import cabinet

    marker = [{"url_name": "x", "query": "", "label": "X", "area": "", "haystack": "x"}]
    monkeypatch.setattr(nav_registry, "palette_entries_for", lambda request: marker)
    assert cabinet.nav_palette({"request": None}) == {"entries": marker}


def test_unknown_when_applies_fails_and_is_done_flag(monkeypatch):
    tenant = SimpleNamespace(schema_name="public")

    def bad_applies(t):
        raise RuntimeError("x")

    item = readiness.Item(
        "tx", "", readiness.MUST, "TX", "settings", lambda t, f: True, bad_applies
    )
    monkeypatch.setattr(readiness, "REGISTRY", (item,))
    monkeypatch.setattr(readiness, "_BY_KEY", {"tx": item})
    monkeypatch.setattr(readiness, "_active_direction_keys", lambda t: set())
    assert [r["done"] for r in readiness.items_for(tenant, unknown_on_error=True)] == [None]

    def boom(t, f):
        raise RuntimeError("y")

    item2 = readiness.Item("ty", "", readiness.MUST, "TY", "settings", boom)
    monkeypatch.setattr(readiness, "_BY_KEY", {"ty": item2})
    assert readiness.is_done(tenant, "ty") is True  # гейт: fail-open
    assert readiness.is_done(tenant, "ty", unknown_on_error=True) is None


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ({"in_city_catalog": False, "email_pending": True}, "not_in_catalog"),
        ({"email_pending": True}, "email_pending"),
        ({"published_at": None}, "hidden"),
        ({}, "ok"),
    ],
)
def test_owner_stats_status_reads_withheld_reasons(flags, expected):
    from apps.aggregator.owner_stats import _status

    base = {k: v[0] for k, v in FLAGS.items()}
    assert _status(SimpleNamespace(**{**base, **flags})) == expected


def test_tls_withheld_after_grace():
    from datetime import timedelta

    from django.utils import timezone

    from apps.core.health import UNCONFIRMED_TLS_GRACE, tls_withheld

    old = timezone.now() - UNCONFIRMED_TLS_GRACE - timedelta(minutes=1)
    assert tls_withheld(SimpleNamespace(email_pending=True, created_at=old))
    assert not tls_withheld(SimpleNamespace(email_pending=True, created_at=timezone.now()))
    assert not tls_withheld(SimpleNamespace(email_pending=False, created_at=old))
    assert not tls_withheld(None)


def test_storefront_gates_have_one_source():
    """Витринные проверки модулей заказа/брони/номеров — только через storefront_state."""
    import re
    from pathlib import Path

    files = [
        "apps/orders/public_views.py",
        "apps/promotions/public_views.py",
        "apps/promotions/response.py",
        "apps/stays/public_views.py",
        "apps/booking/public_views.py",
    ]
    pattern = re.compile(r'is_module_active\("(orders|stays|booking)"\)')
    hits = {f: pattern.findall(Path(f).read_text(encoding="utf-8")) for f in files}
    assert not any(hits.values()), hits


@pytest.mark.parametrize("key", ["orders", "booking", "stays", "events", "jobs", "finance", "crm"])
@pytest.mark.parametrize(
    "disabled",
    [[], ["orders"], ["booking", "stays"], ["events"], ["jobs", "finance"]],
)
def test_inactive_reason_agrees_with_is_module_active(key, disabled):
    from apps.core import modules

    for btype in ("bakery", "hotel", "friseur", "other"):
        tenant = TenantFactory.build(business_type=btype, disabled_modules=list(disabled))
        reason = modules.inactive_reason(tenant, key)
        assert (reason == "") is modules.is_module_active(tenant, key), (btype, key, reason)


def test_strict_closures_raise_instead_of_saying_open(monkeypatch):
    from datetime import date

    from apps.core import closures

    monkeypatch.setattr(closures, "_own_schema", lambda t: True)

    class Boom:
        @staticmethod
        def filter(**kw):
            raise RuntimeError("db down")

    import apps.booking.models as bm

    monkeypatch.setattr(bm.ClosedDate, "objects", Boom)
    assert closures.closed_days(date(2026, 1, 1), date(2026, 1, 2)) == {}
    with pytest.raises(RuntimeError):
        closures.closed_days(date(2026, 1, 1), date(2026, 1, 2), strict=True)
