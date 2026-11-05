"""AIS-A A-0 срез A0.2: реестр диагнозов помощника — зовёт гейты, fail-safe, только чтение."""

import ast
import importlib
from pathlib import Path

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import NoReverseMatch, reverse

from apps.core import diagnoses
from apps.tenants.tests.factories import TenantFactory

SOURCE = Path(diagnoses.__file__).read_text(encoding="utf-8")


@pytest.fixture
def urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _resolve(path: str):
    module, attr = path.split(":")
    obj = importlib.import_module(module)
    for part in attr.split("."):
        obj = getattr(obj, part)
    return obj


def test_every_declared_gate_exists():
    for d in diagnoses.REGISTRY:
        assert d.gates, d.key
        for gate in d.gates:
            assert callable(_resolve(gate)), (d.key, gate)


def test_registry_keys_are_unique_and_costs_known():
    keys = [d.key for d in diagnoses.REGISTRY]
    assert len(keys) == len(set(keys)) == 8
    assert {d.cost for d in diagnoses.REGISTRY} <= {diagnoses.CHEAP, diagnoses.HEAVY}


def test_no_direct_flag_reads():
    """Диагнозы не повторяют гейты: флаги видимости читают только гейты."""
    forbidden = {
        "email_pending",
        "published_at",
        "in_city_catalog",
        "subscription_status",
        "is_internal",
    }
    hits = []
    for node in ast.walk(ast.parse(SOURCE)):
        if isinstance(node, ast.Attribute) and node.attr in forbidden:
            hits.append(node.attr)
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "channel"
            and isinstance(node.value, ast.Name)
            and node.value.id == "merchant"
        ):
            hits.append("merchant.channel")  # get_or_create — GET помощника не пишет
    assert not hits, hits


def test_all_finding_urls_reverse(urlconf):
    names = {
        n.value
        for n in ast.walk(ast.parse(SOURCE))
        if isinstance(n, ast.Constant)
        and isinstance(n.value, str)
        and (":" in n.value or n.value.replace("-", "").isalpha())
        and n.value.islower()
        and " " not in n.value
    }
    url_like = {
        "owner-confirm-resend",
        "setup",
        "billing",
        "promotions:promotion-list",
        "promotions:promotion-create",
        "promotions:promotion-edit",
        "modules",
        "betriebsferien",
        "payment-settings",
        "catalog:product-create",
        "settings",
        "booking:services",
        "booking:resources",
        "stays:units",
        "gbp-merchant",
    }
    assert url_like <= names
    for name in url_like:
        try:
            reverse(name)
        except NoReverseMatch:
            reverse(name, args=["00000000-0000-0000-0000-000000000000"])


@pytest.mark.django_db
def test_website_hidden_follows_the_gate(monkeypatch, urlconf):
    from apps.core import storefront_state

    tenant = TenantFactory(schema_name="public")
    monkeypatch.setattr(storefront_state, "hidden_reasons", lambda t: [])
    assert [f.level for f in diagnoses.run(tenant, "website_hidden")] == [diagnoses.OK]
    monkeypatch.setattr(storefront_state, "hidden_reasons", lambda t: ["email_pending"])
    found = diagnoses.run(tenant, "website_hidden")
    assert found[0].level == diagnoses.PROBLEM
    assert found[0].url_name == "owner-confirm-resend" and found[0].method == "POST"


@pytest.mark.django_db
def test_not_in_city_follows_the_gate(monkeypatch, urlconf):
    from apps.aggregator import visibility

    tenant = TenantFactory(schema_name="public")
    monkeypatch.setattr(visibility, "withheld_reasons", lambda t: ["operator_off", "suspended"])
    found = diagnoses.run(tenant, "not_in_city")
    assert [f.level for f in found] == [diagnoses.PROBLEM, diagnoses.PROBLEM]
    assert found[1].owner_only is True and found[1].url_name == "billing"
    monkeypatch.setattr(visibility, "withheld_reasons", lambda t: [])
    # Без листингов — честная подсказка, не «всё хорошо».
    assert diagnoses.run(tenant, "not_in_city")[0].level == diagnoses.PROBLEM


@pytest.mark.django_db
def test_cart_closed_reads_module_gate(monkeypatch, urlconf):
    from apps.core import modules

    tenant = TenantFactory(schema_name="public")
    monkeypatch.setattr(modules, "inactive_reason", lambda t, key: "package")
    found = diagnoses.run(tenant, "cart_closed")
    assert len(found) == 1 and "Paket" in found[0].text


@pytest.mark.django_db
def test_failure_is_unknown_not_ok(monkeypatch, urlconf):
    from apps.core import storefront_state

    tenant = TenantFactory(schema_name="public")

    def boom(t):
        raise RuntimeError("db down")

    monkeypatch.setattr(storefront_state, "hidden_reasons", boom)
    found = diagnoses.run(tenant, "website_hidden")
    assert [f.level for f in found] == [diagnoses.UNKNOWN]


@pytest.mark.django_db
def test_applicable_survives_failing_applies(monkeypatch):
    tenant = TenantFactory(schema_name="public")
    monkeypatch.setattr(diagnoses, "_promotions_on", lambda t: 1 / 0)
    keys = [d.key for d in diagnoses.applicable(tenant)]
    assert "website_hidden" in keys


@pytest.mark.django_db
def test_all_diagnoses_are_read_only(urlconf):
    tenant = TenantFactory(schema_name="public")
    with CaptureQueriesContext(connection) as ctx:
        for d in diagnoses.REGISTRY:
            diagnoses.run(tenant, d.key)
    writes = [
        q["sql"]
        for q in ctx.captured_queries
        if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
    ]
    assert not writes, writes[:3]
