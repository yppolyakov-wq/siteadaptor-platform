"""AI-0b: мягкие дневные лимиты и оценка стоимости."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.ai import api, pricing, usage
from apps.ai.errors import AIQuotaExceeded
from apps.ai.models import AIUsage
from apps.ai.providers import fake

pytestmark = pytest.mark.django_db


def _row(**kw):
    base = dict(day=timezone.localdate(), tenant_schema="baeckerei", task="smoke", route="fake")
    base.update(kw)
    return AIUsage.objects.create(**base)


def test_tenant_daily_calls_limit(ai_on):
    ai_on.AI_TENANT_DAILY_CALLS = 2
    for _ in range(2):
        api.generate("smoke", "x", tenant="baeckerei")
    with pytest.raises(AIQuotaExceeded):
        api.generate("smoke", "x", tenant="baeckerei")
    assert len(fake.CALLS) == 2
    api.generate("smoke", "x", tenant="metzgerei")  # другой бизнес не затронут


def test_failed_calls_do_not_count_as_calls(ai_on):
    ai_on.AI_TENANT_DAILY_CALLS = 1
    _row(ok=False, error_code="unavailable")
    api.generate("smoke", "x", tenant="baeckerei")


def test_tenant_daily_eur_limit(ai_on):
    ai_on.AI_TENANT_DAILY_EUR = 0.5
    _row(cost_cents=Decimal("50"))
    with pytest.raises(AIQuotaExceeded):
        api.generate("smoke", "x", tenant="baeckerei")


def test_platform_budget_blocks_all_tenants_and_platform(ai_on):
    ai_on.AI_DAILY_BUDGET_EUR = 1
    _row(tenant_schema="andere", cost_cents=Decimal("100"))
    for tenant in ("baeckerei", ""):
        with pytest.raises(AIQuotaExceeded):
            api.generate("smoke", "x", tenant=tenant)
    assert fake.CALLS == []


def test_limits_reset_next_day(ai_on):
    ai_on.AI_TENANT_DAILY_CALLS = 1
    _row(day=timezone.localdate() - timedelta(days=1))
    api.generate("smoke", "x", tenant="baeckerei")


def test_cost_from_prices(ai_on):
    ai_on.AI_PRICES = {"fake": [100_000, 400_000]}  # 1 000 € / 4 000 € за 1M (для арифметики)
    r = api.generate("smoke", "x" * 400, tenant="baeckerei")
    expected = (Decimal(100_000) * r.tokens_in + Decimal(400_000) * r.tokens_out) / 1_000_000
    assert r.cost_cents == expected.quantize(Decimal("0.0001"))
    assert AIUsage.objects.get().cost_cents == r.cost_cents


def test_unknown_price_counts_zero(settings):
    settings.AI_PRICES = {}
    assert pricing.cost_cents("whatever", 1000, 1000) == 0


def test_usage_record_is_fail_safe(monkeypatch, caplog):
    def boom(**kw):
        raise RuntimeError("db down")

    monkeypatch.setattr(AIUsage.objects, "create", boom)
    usage.record(tenant_schema="x", is_demo=False, task="smoke", route="fake", model="m")
    assert "RuntimeError" in caplog.text


def test_purge_removes_old_rows(settings):
    settings.AI_USAGE_RETENTION_DAYS = 10
    _row(day=timezone.localdate() - timedelta(days=11))
    keep = _row()
    assert usage.purge() == 1
    assert list(AIUsage.objects.values_list("pk", flat=True)) == [keep.pk]


def test_demo_tenant_flagged(ai_on):
    class T:
        schema_name = "demo_x"
        is_demo = True

    api.generate("smoke", "x", tenant=T())
    assert AIUsage.objects.get().is_demo is True


def test_public_schema_counts_as_platform(ai_on):
    api.generate("smoke", "x", tenant="public")
    assert AIUsage.objects.get().tenant_schema == ""
