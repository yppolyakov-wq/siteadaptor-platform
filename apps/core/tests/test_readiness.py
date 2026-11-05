"""AIS-W W4-0: единый реестр готовности — замки (план ais-w4-0-readiness-plan-2026-11-05)."""

import pathlib
from io import StringIO

import pytest
from django.core.management import call_command
from django.urls import reverse

from apps.core import directions, readiness
from apps.tenants import onboarding, siteconfig
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db

ROOT = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _tenant_urlconf(settings):
    settings.ROOT_URLCONF = "config.urls_tenant"


def _tenant(**kw):
    """Тенант «в своей схеме»: тестовая БД держит таблицы тенанта в public."""
    kw.setdefault("schema_name", "public")
    kw.setdefault("slug", "rd")
    kw.setdefault("business_type", "bakery")
    return TenantFactory(**kw)


def test_registry_is_consistent_and_every_fix_link_resolves():
    keys = [item.key for item in readiness.REGISTRY]
    assert len(keys) == len(set(keys))
    known = {d.key for d in directions.REGISTRY}
    for item in readiness.REGISTRY:
        assert item.level in (readiness.MUST, readiness.NICE), item.key
        assert not item.direction or item.direction in known, item.key
        assert reverse(item.url_name), item.key


def test_outside_tenant_schema_is_unknown_not_missing():
    tenant = TenantFactory.build(schema_name="elsewhere", business_type="bakery")
    assert readiness.is_done(tenant, "impressum") is None
    assert "impressum" not in [r["key"] for r in readiness.missing(tenant, direction="")]


def test_recht_step_is_done_only_with_complete_impressum():
    """Единственное изменение поведения W4-0: шаг «Recht» = Impressum по § 5 DDG."""
    from apps.core.models import LegalDoc

    tenant = _tenant()
    LegalDoc.objects.create(kind="datenschutz", locale="de", text="Datenschutz …")
    step = onboarding._STEP_BY_KEY["texts"]
    assert step.check(tenant) is False  # только Datenschutz — Impressum не закрыт
    LegalDoc.objects.create(kind="impressum", locale="de", text="Bäckerei, Weg 1, Hilden")
    tenant = type(tenant).objects.get(pk=tenant.pk)  # сбросить мемо
    assert step.check(tenant) is True


def test_sell_gate_is_off_by_default(settings):
    settings.READINESS_SELL_GATE = False
    assert readiness.sell_allowed(_tenant(), "waren") is True


def test_sell_gate_closes_unready_and_respects_exempt_and_demo(settings):
    settings.READINESS_SELL_GATE = True
    tenant = _tenant(disabled_modules=[])  # orders включён → Waren продаёт
    assert readiness.sell_allowed(tenant, "waren") is False
    tenant.site_config = {"readiness": {"exempt": True}}
    assert readiness.sell_allowed(tenant, "waren") is True
    demo = TenantFactory.build(schema_name="public", business_type="bakery", is_demo=True)
    assert readiness.sell_allowed(demo, "waren") is True


def test_delivery_without_prepayment_is_missing():
    tenant = _tenant(disabled_modules=[], delivery_enabled=True)
    keys = [r["key"] for r in readiness.missing(tenant, direction="waren")]
    assert "waren.prepay" in keys
    pickup_only = TenantFactory.build(
        schema_name="public", business_type="bakery", disabled_modules=[], delivery_enabled=False
    )
    keys = [r["key"] for r in readiness.items_for(pickup_only, direction="waren")]
    assert "waren.prepay" not in keys  # пункт не применим без доставки


def _selects(fn):
    """Число SELECT'ов (savepoint'ы защиты фактов — не чтение данных)."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as ctx:
        fn()
    return sum(1 for q in ctx.captured_queries if q["sql"].lstrip().upper().startswith("SELECT"))


def test_query_budget_per_direction_and_memo():
    tenant = _tenant(business_type="hotel")
    for key in ("waren", "termine", "zimmer", "tickets"):
        assert _selects(lambda k=key: readiness.missing(tenant, direction=k)) <= 3, key
    # Повтор — из мемо; живым остаётся только Impressum (правится в том же запросе).
    assert _selects(lambda: readiness.missing(tenant, direction="zimmer")) <= 1


def test_normalize_keeps_only_true_exempt():
    assert siteconfig.normalize({"readiness": {"exempt": True}})["readiness"] == {"exempt": True}
    assert "readiness" not in siteconfig.normalize({"readiness": {"exempt": "yes"}})
    assert "readiness" not in siteconfig.normalize({})


def test_registry_is_not_called_from_cabinet_chrome():
    """Реестр зовут по месту и в шторке помощника — не на каждом рендере кабинета."""
    chrome = [
        ROOT / "apps/core/context_processors.py",
        ROOT / "apps/core/nav_registry.py",
        ROOT / "templates/tenant/_base_dashboard.html",
    ]
    for path in chrome:
        assert "readiness" not in path.read_text(encoding="utf-8"), path


def test_report_rows_and_stamp_rules():
    """Отчёт по бизнесу в своей схеме + правила исключения (сбой продаж ≠ «не продаёт»)."""
    from apps.core.management.commands import readiness_report as cmd

    tenant = _tenant(disabled_modules=[])  # Waren продаёт, ничего не заполнено
    row = cmd.report_for(tenant)
    assert "waren" in row["would_close"] and "impressum" in row["base_missing"]
    assert cmd.needs_exempt({**row, "recent_sales": True})
    assert cmd.needs_exempt({**row, "recent_sales": None})  # неясно — исключение ставим
    assert not cmd.needs_exempt({**row, "recent_sales": False})
    assert not cmd.needs_exempt({**row, "demo": True, "recent_sales": True})


def test_internal_tenant_is_not_gated(settings):
    settings.READINESS_SELL_GATE = True
    internal = TenantFactory.build(schema_name="public", business_type="bakery", is_internal=True)
    assert readiness.sell_allowed(internal, "waren") is True


def test_stamp_writes_flag_and_dry_run_writes_nothing():
    from apps.core.management.commands import readiness_report as cmd

    tenant = _tenant(disabled_modules=[], site_config={"seo": {"x": 1}})
    out = StringIO()
    call_command("readiness_report", "--stamp-exempt", stdout=out)
    tenant.refresh_from_db()
    assert "readiness" not in tenant.site_config and "dry-run" in out.getvalue()
    cmd.stamp_exempt(tenant.schema_name)
    tenant.refresh_from_db()
    assert tenant.site_config["readiness"] == {"exempt": True}
    assert tenant.site_config["seo"] == {"x": 1}  # чужие ключи целы


def test_report_errors_mean_exempt_and_unknown_key_raises():
    from apps.core.management.commands import readiness_report as cmd

    row = {
        "demo": False,
        "exempt": False,
        "would_close": {},
        "errors": ["agb"],
        "recent_sales": True,
    }
    assert cmd.needs_exempt(row)  # сбой проверки не лишает продающий бизнес исключения
    with pytest.raises(KeyError):
        readiness.is_done(TenantFactory.build(schema_name="public"), "nope")


def test_outside_schema_is_not_memoized():
    tenant = TenantFactory.build(schema_name="elsewhere", business_type="bakery")
    assert readiness.facts_for(tenant).get("x", lambda: True) is None
    assert "x" not in readiness.facts_for(tenant)._cache
