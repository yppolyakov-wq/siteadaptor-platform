"""AIS-0: метки времени мастера и отчёт «время до живого сайта»."""

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.tenants import onboarding
from apps.tenants.onboarding_metrics import summarize, tenant_row
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _tenant(**kw):
    return TenantFactory(**kw)


def test_times_are_first_only_and_survive_get_state():
    tenant = _tenant()
    onboarding.touch_start(tenant)
    first = onboarding.get_state(tenant)["times"]["start"]
    onboarding.touch_start(tenant)  # повторный заход не перезаписывает
    assert onboarding.get_state(tenant)["times"]["start"] == first


def test_advance_stamps_step_and_completion_with_wizard_source():
    tenant = _tenant()
    onboarding.goto(tenant, onboarding.STEP_KEYS[-2])
    onboarding.advance(tenant)
    state = onboarding.get_state(tenant)
    assert state["completed"] is True
    assert state["source"] == "wizard"
    assert {onboarding.STEP_KEYS[-2], "completed"} <= set(state["times"])


def test_mark_complete_records_foreign_source_and_is_excluded():
    tenant = _tenant()
    onboarding.touch_start(tenant)
    onboarding.mark_complete(tenant, source="demo")
    assert onboarding.get_state(tenant)["source"] == "demo"
    assert tenant_row(tenant) is None


def test_garbage_times_are_dropped():
    tenant = TenantFactory.build(
        site_config={
            "onboarding": {
                "v": 2,
                "step": "company",
                "times": {"start": "nope", "evil": "2026-01-01T00:00:00", "company": 5},
                "source": "hacker",
            }
        }
    )
    state = onboarding.get_state(tenant)
    assert "times" not in state and "source" not in state


def test_row_and_summary_measure_minutes_from_creation():
    tenant = _tenant()
    created = tenant.created_at
    stamp = lambda minutes: (created + timedelta(minutes=minutes)).isoformat()  # noqa: E731
    onboarding.save_state(
        tenant,
        {
            "v": 2,
            "step": "done",
            "done": ["company"],
            "skipped": ["stil"],
            "completed": True,
            "source": "wizard",
            "times": {
                "start": stamp(2),
                "company": stamp(6),
                "stil": stamp(7),
                "completed": stamp(20),
            },
        },
    )
    row = tenant_row(tenant)
    assert round(row["minutes_to_complete"]) == 20
    assert round(row["dwell"]["company"]) == 4 and round(row["dwell"]["stil"]) == 1
    summary = summarize([row])
    assert round(summary["median_minutes"]) == 20 and summary["share_within_day"] == 1.0
    assert summary["steps"]["stil"]["skipped"] == 1


def test_tenants_without_marks_are_not_counted():
    assert tenant_row(_tenant()) is None
    assert tenant_row(_tenant(is_demo=True)) is None


def test_report_command_runs():
    tenant = _tenant(business_type="bakery")
    onboarding.touch_start(tenant)
    onboarding.goto(tenant, onboarding.STEP_KEYS[-2])
    onboarding.advance(tenant)
    out = StringIO()
    call_command("onboarding_report", "--days", "1", stdout=out)
    assert "all:" in out.getvalue() and "bakery:" in out.getvalue()
    tenant.created_at = timezone.now() - timedelta(days=40)
    tenant.save(update_fields=["created_at"])
