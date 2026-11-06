"""AIS-M M-1e: modules_report — только отчёт по умолчанию, --apply включает пресетное."""

import json
from io import StringIO

import pytest
from django.core.management import call_command

from apps.core import module_report, modules
from apps.core.module_presets import LEGACY_DISABLED
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _hotel(disabled):
    return TenantFactory(business_type="hotel", disabled_modules=list(disabled))


def _run(*args):
    out = StringIO()
    call_command("modules_report", "--json", *args, stdout=out)
    return json.loads(out.getvalue())


def _row(data, schema):
    return next(r for r in data["tenants"] if r["schema"] == schema)


def test_legacy_hotel_is_preset_and_apply_enables_promotions_only():
    t = _hotel(LEGACY_DISABLED["hotel"])
    row = _row(_run("--tenant", t.schema_name), t.schema_name)
    assert row["class"] == "preset"
    assert "promotions" in row["enable"]
    t.refresh_from_db()
    assert sorted(t.disabled_modules) == sorted(LEGACY_DISABLED["hotel"])  # отчёт не пишет
    _run("--tenant", t.schema_name, "--apply")
    t.refresh_from_db()
    assert "promotions" not in t.disabled_modules
    # ничего не выключает: customer_account у живого отеля остаётся включённым
    assert "customer_account" not in t.disabled_modules


def test_variants_without_blog_and_with_migration_additions():
    for extra in ({"stays"}, {"customer_account"}):
        legacy = (set(LEGACY_DISABLED["hotel"]) - {"blog", "booking"}) | extra
        assert frozenset(legacy) in module_report.legacy_variants("hotel")


def test_owner_choice_is_untouched():
    t = _hotel([*LEGACY_DISABLED["hotel"], "crm"])
    row = _row(_run("--tenant", t.schema_name, "--apply"), t.schema_name)
    assert row["class"] == "owner"
    assert "crm" in row["base_off"]
    t.refresh_from_db()
    assert "promotions" in t.disabled_modules


def test_apply_is_idempotent():
    t = _hotel(LEGACY_DISABLED["hotel"])
    _run("--tenant", t.schema_name, "--apply")
    second = _row(_run("--tenant", t.schema_name, "--apply"), t.schema_name)
    assert second["class"] == "same"
    assert not second.get("applied")


def test_demo_and_lite_are_skipped_or_owner():
    demo = TenantFactory(business_type="hotel", disabled_modules=list(LEGACY_DISABLED["hotel"]))
    demo.is_demo = True
    demo.save(update_fields=["is_demo"])
    data = _run("--tenant", demo.schema_name)
    assert data["tenants"] == [] and data["skipped"] == {"demo": 1}
    lite = TenantFactory(
        business_type="bakery",
        disabled_modules=list(LEGACY_DISABLED["bakery"]),
        site_config={"profile": "aktionen"},
    )
    assert _row(_run("--tenant", lite.schema_name), lite.schema_name)["class"] == "owner"


def test_new_preset_is_same():
    t = TenantFactory(
        business_type="bakery", disabled_modules=modules.default_disabled_for("bakery")
    )
    assert module_report.classify(t)[0] == "same"


def test_race_owner_switched_inside_lock():
    t = _hotel(LEGACY_DISABLED["hotel"])
    type(t).objects.filter(pk=t.pk).update(disabled_modules=[*LEGACY_DISABLED["hotel"], "crm"])
    assert module_report.apply_for(t) == []
    t.refresh_from_db()
    assert "promotions" in t.disabled_modules
