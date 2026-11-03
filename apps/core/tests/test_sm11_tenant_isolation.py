"""SM11: фоновые обходы бизнесов — ошибка одного не обрывает остальных."""

import logging

import pytest
from django.db import connection

from apps.core import tenant_iter
from apps.tenants.models import Tenant
from apps.tenants.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


def test_failing_tenant_is_logged_and_the_loop_continues(caplog):
    seen = []
    with caplog.at_level(logging.ERROR, logger="apps.core.tenant_iter"):
        for schema in ("a", "b", "c"):
            with tenant_iter.isolated(connection.schema_name, f"probe-{schema}") as outcome:
                if schema == "b":
                    raise RuntimeError("boom")
                seen.append(schema)
            if schema == "b":
                assert outcome.failed
    assert seen == ["a", "c"]
    assert "probe-b" in caplog.text


def test_db_error_inside_one_tenant_does_not_poison_the_next():
    """В тестах (внутри транзакции) ошибка БД без точки сохранения дала бы
    «current transaction is aborted» всем следующим бизнесам."""
    with tenant_iter.isolated(connection.schema_name, "probe") as outcome:
        with connection.cursor() as cur:
            cur.execute("SELECT * FROM table_that_does_not_exist_sm11")
    assert outcome.failed
    with tenant_iter.isolated(connection.schema_name, "probe2") as outcome2:
        assert Tenant.objects.exists() is not None
    assert not outcome2.failed


def test_failed_provisioning_tenants_are_not_iterated():
    ok = TenantFactory(schema_name="sm11ok", provisioning_status=Tenant.PROVISIONING_READY)
    bad = TenantFactory(schema_name="sm11bad", provisioning_status=Tenant.PROVISIONING_FAILED)
    names = tenant_iter.schemas()
    assert ok.schema_name in names and bad.schema_name not in names
    assert names == sorted(names, key=lambda n: Tenant.objects.get(schema_name=n).pk)


def test_every_beat_loop_uses_isolation():
    """Голый `with schema_context(schema):` внутри обхода тенантов вернул бы класс SM11."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    bad = []
    for path in sorted(root.glob("apps/*/tasks.py")):
        text = path.read_text()
        # тело цикла до следующей строки с меньшим отступом
        for m in re.finditer(
            r"for \w+(?:, \w+)? in _iter_tenant\w*\(\):\n((?:\s+.*\n){1,6})", text
        ):
            body = m.group(1)
            # своя изоляция с логом (jobs, purge_old_night_rates) — тоже допустима
            own_guard = "try:" in body and ".exception(" in text[m.end() : m.end() + 900] + body
            if "tenant_iter.isolated(" not in body and not own_guard:
                bad.append(f"{path.relative_to(root)}: {body.strip().splitlines()[0]}")
    assert not bad, "\n".join(bad)
