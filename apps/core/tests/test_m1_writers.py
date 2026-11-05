"""AIS-M M-1b: единственные писатели модулей и направлений (под блокировкой, точечно)."""

from types import SimpleNamespace

import pytest

from apps.core import directions, modules, packages
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def _fresh(t):
    return Tenant.objects.get(pk=t.pk)


def test_set_modules_touches_only_its_key():
    t = TenantFactory(business_type="bakery", disabled_modules=["blog", "finance"])
    assert modules.set_modules(t, {"loyalty": False}) == {}
    assert sorted(_fresh(t).disabled_modules) == ["blog", "finance", "loyalty"]
    assert modules.set_modules(t, {"loyalty": True, "blog": True}) == {}
    assert _fresh(t).disabled_modules == ["finance"]


def test_core_and_unknown_are_refused():
    t = TenantFactory(disabled_modules=[])
    got = modules.set_modules(t, {"catalog": False, "nope": True})
    assert got == {"catalog": modules.SET_CORE, "nope": modules.SET_UNKNOWN}
    assert _fresh(t).disabled_modules == []


def test_package_ceiling_refused_inside_lock(monkeypatch):
    t = TenantFactory(disabled_modules=["finance"])
    monkeypatch.setattr(packages, "module_allowed", lambda tenant, key: key != "finance")
    assert modules.set_modules(t, {"finance": True}) == {"finance": modules.SET_PACKAGE}
    assert _fresh(t).disabled_modules == ["finance"]


def test_lite_package_keeps_jobs(monkeypatch):
    t = TenantFactory(disabled_modules=[])
    monkeypatch.setattr(packages, "package_of", lambda tenant: SimpleNamespace(lite=True))
    assert modules.set_modules(t, {"jobs": False}) == {"jobs": modules.SET_LITE}
    assert "jobs" not in _fresh(t).disabled_modules


def test_stale_request_object_does_not_roll_back_parallel_choice():
    t = TenantFactory(disabled_modules=["blog"])
    stale = _fresh(t)
    Tenant.objects.filter(pk=t.pk).update(disabled_modules=["blog", "finance"])
    modules.set_modules(stale, {"loyalty": False})
    assert sorted(_fresh(t).disabled_modules) == ["blog", "finance", "loyalty"]


def test_no_schema_creation_on_write(monkeypatch):
    calls = []
    real = Tenant.create_schema
    monkeypatch.setattr(
        Tenant, "create_schema", lambda self, *a, **k: calls.append(1) or real(self, *a, **k)
    )
    t = TenantFactory(disabled_modules=[])
    modules.set_modules(t, {"loyalty": False})
    directions.set_state(t, "termine", True, mode="zeigen")
    assert not calls


def test_direction_off_keeps_shared_module():
    """Кафе: Termine и Tisch на одном booking — выключение одного его не трогает."""
    t = TenantFactory(business_type="cafe", disabled_modules=[])
    if not directions.is_active(t, "tisch"):
        pytest.skip("у кафе нет направления Tisch")
    got = directions.set_state(t, "termine", False)
    assert got.get("booking") == directions.STATE_SHARED
    assert "booking" not in _fresh(t).disabled_modules


def test_direction_on_off_writes_its_modules():
    t = TenantFactory(business_type="bakery", disabled_modules=["events"])
    assert directions.set_state(t, "tickets", True) == {}
    assert "events" not in _fresh(t).disabled_modules
    assert directions.set_state(t, "tickets", False) == {}
    assert "events" in _fresh(t).disabled_modules


def test_fixed_directions_and_mode():
    t = TenantFactory(business_type="bakery", disabled_modules=[], site_config={"x": 1})
    assert directions.set_state(t, "waren", False) == {"waren": directions.STATE_FIXED}
    assert directions.set_state(t, "zimmer", True, mode="zeigen") == {}
    cfg = _fresh(t).site_config
    assert cfg["directions"] == {"zimmer": {"mode": "zeigen"}} and cfg["x"] == 1
    assert directions.set_state(t, "zimmer", True, mode="bad") == {"zimmer": modules.SET_UNKNOWN}
