"""KA-12 E11.5: отчёт пилота — числа без персональных данных, только чтение."""

import csv
import io
import re
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _report(**opts):
    out = io.StringIO()
    call_command("pilot_report", stdout=out, **opts)
    return list(csv.DictReader(io.StringIO(out.getvalue()))), out.getvalue()


def _tenant(**kw):
    kw.setdefault("city", "Solingen")
    kw.setdefault("name", "Bäckerei Meyer")
    kw.setdefault("owner_email", "inhaber@meyer.example")
    kw.setdefault("owner_phone", "+49 212 123456")
    return TenantFactory(**kw)


def test_minutes_to_first_active_promo_from_audit():
    tenant = _tenant()
    AuditEvent.objects.create(
        tenant_schema=tenant.schema_name, action="promotion.activated", resource_type="promotion"
    )
    AuditEvent.objects.filter(tenant_schema=tenant.schema_name).update(
        created_at=tenant.created_at + timedelta(minutes=7)
    )
    rows, _ = _report(city="solingen")
    row = next(r for r in rows if r["schema"] == tenant.schema_name)
    assert row["min_to_first_active_promo"] == "7"
    assert rows[-1]["schema"].startswith("MEDIAN")


def test_demo_and_internal_excluded_by_default():
    real = _tenant()
    demo = _tenant(is_demo=True)
    internal = _tenant(is_internal=True)
    schemas = {r["schema"] for r in _report()[0]}
    assert real.schema_name in schemas
    assert demo.schema_name not in schemas and internal.schema_name not in schemas
    schemas = {r["schema"] for r in _report(include_demo=True)[0]}
    assert demo.schema_name in schemas


def test_city_filter():
    here = _tenant()
    there = _tenant(city="Hilden")
    schemas = {r["schema"] for r in _report(city="Solingen")[0]}
    assert here.schema_name in schemas and there.schema_name not in schemas


def test_no_personal_data_in_output():
    _tenant()
    _, raw = _report()
    assert "@" not in raw
    assert "Meyer" not in raw
    assert "123456" not in raw and "+49" not in raw


def test_report_writes_nothing():
    _tenant()
    with CaptureQueriesContext(connection) as ctx:
        _report()
    writes = [
        q["sql"] for q in ctx.captured_queries if re.match(r"\s*(INSERT|UPDATE|DELETE)", q["sql"])
    ]
    assert writes == []


def test_empty_is_not_zero():
    tenant = _tenant()
    row = next(r for r in _report()[0] if r["schema"] == tenant.schema_name)
    assert row["min_to_first_active_promo"] == ""
    assert row["promotions_total"] == "0"


def test_broken_schema_gives_error_row(monkeypatch):
    from apps.core.management.commands import pilot_report

    tenant = _tenant()

    def boom(*a, **k):
        raise RuntimeError("schema gone")

    monkeypatch.setattr(pilot_report, "tenant_row", boom)
    row = next(r for r in _report()[0] if r["schema"] == tenant.schema_name)
    assert row["error"] == "RuntimeError"


def test_support_log_counts(tmp_path):
    tenant = _tenant()
    log = tmp_path / "support.csv"
    log.write_text(
        f"date,schema,topic,minutes\n2026-10-24,{tenant.schema_name},Login,5\n"
        f"2026-10-25,{tenant.schema_name},Foto,3\n",
        encoding="utf-8",
    )
    row = next(r for r in _report(support_log=str(log))[0] if r["schema"] == tenant.schema_name)
    assert row["support_requests"] == "2"


def test_since_filter():
    old = _tenant()
    type(old).objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=40))
    new = _tenant()
    since = (timezone.now() - timedelta(days=5)).date().isoformat()
    schemas = {r["schema"] for r in _report(since=since)[0]}
    assert new.schema_name in schemas and old.schema_name not in schemas
