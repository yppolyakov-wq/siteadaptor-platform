"""Какие миграции не применены в схеме (T-10, 2026-10-20).

Общий помощник для `migration_state` и шаблонной схемы (`apps.tenants.schema_template`):
миграции на диске читаются один раз, по схеме — только её таблица `django_migrations`.
"""

from __future__ import annotations

from django.db import connection


def disk_migrations() -> set[tuple[str, str]]:
    from django.db.migrations.loader import MigrationLoader

    return set(MigrationLoader(None, ignore_no_migrations=True).disk_migrations)


def tenant_app_labels() -> set[str]:
    from django.conf import settings
    from django_tenants.utils import app_labels

    return set(app_labels(settings.TENANT_APPS))


def pending(schema: str, wanted: set[str], disk=None) -> list[tuple[str, str]]:
    """Миграции приложений `wanted`, которых нет в `django_migrations` этой схемы.

    Загрузчик читает таблицу ТЕКУЩЕГО search_path, поэтому переключение схемы и есть
    весь фокус: одна и та же миграция может быть применена в одной схеме и отсутствовать
    в другой.
    """
    from django.db.migrations.recorder import MigrationRecorder
    from django_tenants.utils import schema_context

    if disk is None:
        disk = disk_migrations()
    with schema_context(schema):
        applied = set(MigrationRecorder(connection).applied_migrations())
    return sorted((app, name) for app, name in disk if app in wanted and (app, name) not in applied)
