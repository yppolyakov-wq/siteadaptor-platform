"""T-10 D-1: создание схемы бизнеса копией шаблонной схемы (2026-10-20).

План — docs/deploy-speed-plan-2026-10-20.md §5.

Новая схема получается за секунды копией `settings.TENANT_TEMPLATE_SCHEMA` (структура +
служебные таблицы `django_migrations`/`django_content_type`/`auth_permission`), а не
прогоном ~350 миграций (~минута). Правила безопасности:

- копируем ТОЛЬКО свежий (нет неприменённых миграций) и чистый (в таблицах бизнеса ни
  одной строки) шаблон; иначе — прежний путь миграциями;
- после копии — повторная сверка; если миграции появились, они применяются ПО-НАСТОЯЩЕМУ
  (`migrate_schemas --schema`), никогда `--fake`;
- копия идёт под advisory-блокировкой, которую держит и пересборка шаблона: копия не
  читает полумигрированный шаблон, а при занятой блокировке (деплой мигрирует шаблон)
  схема создаётся миграциями — без ожидания;
- любая ошибка копии откатывает транзакцию (DDL в Postgres транзакционный — полусхемы не
  остаётся) и уводит на путь миграциями.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.db import connection, transaction

log = logging.getLogger(__name__)

# Ключ advisory-блокировки (одно 64-битное число на всю платформу).
LOCK_KEY = 7_310_202_610_200_001
# Таблицы, в которых у чистого шаблона законно есть строки.
SERVICE_TABLES = frozenset({"django_migrations", "django_content_type", "auth_permission"})


class CloneMismatch(Exception):
    pass


def name() -> str:
    return str(getattr(settings, "TENANT_TEMPLATE_SCHEMA", "") or "")


def enabled() -> bool:
    return bool(name())


def is_reserved(schema: str) -> bool:
    return enabled() and schema == name()


def exists() -> bool:
    from django_tenants.utils import schema_exists

    return enabled() and schema_exists(name())


def pending(schema: str | None = None) -> list[tuple[str, str]]:
    from apps.core.schema_migrations import pending as _pending
    from apps.core.schema_migrations import tenant_app_labels

    return _pending(schema or name(), tenant_app_labels())


def dirty_tables(schema: str | None = None) -> list[str]:
    """Таблицы шаблона со строками (кроме служебных). Пусто = шаблон чистый."""
    schema = schema or name()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = %s ORDER BY tablename",
            [schema],
        )
        tables = [row[0] for row in cursor.fetchall()]
        dirty = []
        for table in tables:
            if table in SERVICE_TABLES:
                continue
            cursor.execute(
                f'SELECT EXISTS (SELECT 1 FROM "{schema}"."{table}" LIMIT 1)'  # noqa: S608
            )
            if cursor.fetchone()[0]:
                dirty.append(table)
    return dirty


# Структура схемы из каталога Postgres (без данных). Сравнивается с шаблоном после копии.
_STRUCTURE_SQL = {
    "columns": """
        SELECT table_name, column_name, data_type, udt_name, is_nullable, column_default,
               character_maximum_length, numeric_precision, numeric_scale, is_identity
        FROM information_schema.columns WHERE table_schema = %s""",
    "constraints": """
        SELECT cl.relname, c.conname, c.contype, pg_get_constraintdef(c.oid)
        FROM pg_constraint c JOIN pg_class cl ON cl.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = cl.relnamespace WHERE n.nspname = %s""",
    "indexes": "SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname = %s",
    "sequences": """
        SELECT sequencename, data_type, start_value, increment_by, min_value, max_value
        FROM pg_sequences WHERE schemaname = %s""",
    "owned": """
        SELECT s.relname, t.relname, a.attname FROM pg_class s
        JOIN pg_namespace n ON n.oid = s.relnamespace
        JOIN pg_depend d ON d.objid = s.oid AND d.deptype IN ('a', 'i')
        JOIN pg_class t ON t.oid = d.refobjid
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = d.refobjsubid
        WHERE s.relkind = 'S' AND n.nspname = %s""",
    "triggers": """
        SELECT event_object_table, trigger_name, action_timing, event_manipulation,
               action_statement
        FROM information_schema.triggers WHERE trigger_schema = %s""",
    "views": "SELECT viewname, definition FROM pg_views WHERE schemaname = %s",
}


def structure(schema: str) -> dict[str, list[tuple]]:
    """Структура схемы без её имени — две разные схемы сравнимы напрямую."""

    def norm(value):
        return str(value).replace(f'"{schema}".', "").replace(f"{schema}.", "")

    out = {}
    with connection.cursor() as cursor:
        for key, sql in _STRUCTURE_SQL.items():
            cursor.execute(sql, [schema])
            out[key] = sorted(tuple(norm(v) for v in row) for row in cursor.fetchall())
    return out


def structure_diff(a: str, b: str) -> dict[str, tuple[list, list]]:
    sa, sb = structure(a), structure(b)
    return {
        key: (sorted(set(sa[key]) - set(sb[key])), sorted(set(sb[key]) - set(sa[key])))
        for key in sb
        if sa[key] != sb[key]
    }


def _restore_constraint_names(source: str, target: str) -> None:
    """Функция копирования django-tenants пересоздаёт часть UNIQUE-ограничений с именами
    Postgres (`…_key`) вместо имён Django (`…_<hash>_uniq`). Будущая миграция, которая
    ищет ограничение по имени, на копии бы упала — возвращаем имена шаблона."""
    sql = """
        SELECT cl.relname, c.conname, c.contype, pg_get_constraintdef(c.oid)
        FROM pg_constraint c JOIN pg_class cl ON cl.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = cl.relnamespace WHERE n.nspname = %s"""
    with connection.cursor() as cursor:
        cursor.execute(sql, [source])
        want = {(t, kind, d): name for t, name, kind, d in cursor.fetchall()}
        cursor.execute(sql, [target])
        have = {(t, kind, d): name for t, name, kind, d in cursor.fetchall()}
        for key, name_now in have.items():
            name_tpl = want.get(key)
            if name_tpl and name_tpl != name_now:
                cursor.execute(
                    f'ALTER TABLE "{target}"."{key[0]}" '
                    f'RENAME CONSTRAINT "{name_now}" TO "{name_tpl}"'
                )


def is_ready() -> bool:
    """Шаблон есть, свежий и чистый — копировать можно."""
    return exists() and not pending() and not dirty_tables()


def clone_into(schema: str) -> bool:
    """Создать `schema` копией шаблона. False — копия не сделана (вызывающий идёт путём
    миграций); схемы `schema` при этом нет."""
    from django_tenants.clone import CloneSchema

    if not enabled() or schema == name():
        return False
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", [LOCK_KEY])
                if not cursor.fetchone()[0]:
                    log.info("schema template busy, %s via migrations", schema)
                    return False
            if not is_ready():
                log.warning("schema template not ready, %s via migrations", schema)
                return False
            CloneSchema().clone_schema(name(), schema, "DATA")
            _restore_constraint_names(name(), schema)
            diff = structure_diff(schema, name())
            if diff:
                # Копия не совпала с шаблоном — откат всей транзакции (схемы не будет).
                raise CloneMismatch(sorted(diff))
    except Exception:
        log.warning("schema template clone failed for %s, via migrations", schema, exc_info=True)
        connection.set_schema_to_public()
        return False
    connection.set_schema_to_public()
    # Миграция могла появиться между проверкой и копией (код новее шаблона) — догоняем
    # ПО-НАСТОЯЩЕМУ, без --fake.
    if pending(schema):
        from django.core.management import call_command

        call_command(
            "migrate_schemas",
            tenant=True,
            schema_name=schema,
            interactive=False,
            verbosity=0,
        )
        connection.set_schema_to_public()
    return True
