"""KA-12 E10.4 lock: tenant-app migrations stay transactional.

A new business's schema is migrated INSIDE a transaction (tenant creation), where
`CREATE INDEX CONCURRENTLY` and non-atomic migrations are impossible — a concurrent
index there aborted the whole registration (found on the stand while E10.4 was being
built). Per-tenant tables are small: a plain CREATE INDEX is the right tool.
"""

import ast
from pathlib import Path

from django.apps import apps as django_apps
from django.conf import settings

FORBIDDEN_NAMES = {"AddIndexConcurrently", "RemoveIndexConcurrently"}


def _tenant_migration_files():
    shared = set(settings.SHARED_APPS)
    for label in settings.TENANT_APPS:
        if label in shared:
            continue
        cfg = next((c for c in django_apps.get_app_configs() if c.name == label), None)
        if cfg is None:
            continue
        mig = Path(cfg.path) / "migrations"
        if mig.is_dir():
            yield from sorted(mig.glob("[0-9]*.py"))


def test_tenant_migrations_are_transactional():
    offenders = []
    for path in _tenant_migration_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name | ast.Attribute):
                name = node.id if isinstance(node, ast.Name) else node.attr
                if name in FORBIDDEN_NAMES:
                    offenders.append(f"{path}: {name}")
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if "CONCURRENTLY" in node.value.upper():
                    offenders.append(f"{path}: SQL with CONCURRENTLY")
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == "atomic":
                        if isinstance(node.value, ast.Constant) and node.value.value is False:
                            offenders.append(f"{path}: atomic = False")
    assert not offenders, offenders
