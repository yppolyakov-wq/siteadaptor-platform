"""T-10 D-1: создание схемы бизнеса копией шаблонной схемы (2026-10-20).

План — docs/deploy-speed-plan-2026-10-20.md §5.

Новая схема получается за секунды копией `settings.TENANT_TEMPLATE_SCHEMA` (структура +
служебные таблицы `django_migrations`/`django_content_type`/`auth_permission`), а не
прогоном ~350 миграций (~минута). Правила безопасности:

- копируем ТОЛЬКО свежий (нет неприменённых миграций) и чистый (в таблицах бизнеса ни
  одной строки) шаблон; иначе — прежний путь миграциями;
- после копии — повторная сверка; если миграции появились, они применяются ПО-НАСТОЯЩЕМУ
  (`migrate_schemas --schema`), никогда `--fake`;
- копии берут общую (shared) advisory-блокировку, пересборка шаблона — исключительную:
  копии идут параллельно, но не читают полумигрированный шаблон; при пересборке схема
  создаётся миграциями — без ожидания;
- любая ошибка копии откатывает транзакцию (DDL в Postgres транзакционный — полусхемы не
  остаётся) и уводит на путь миграциями.
"""

from __future__ import annotations

import logging
import re

from django.conf import settings
from django.db import connection, transaction

log = logging.getLogger(__name__)

# Ключ advisory-блокировки (одно 64-битное число на всю платформу).
LOCK_KEY = 7_310_202_610_200_001
INSTALL_LOCK_KEY = 7_310_202_610_200_003
# Таблицы, в которых у чистого шаблона законно есть строки.
SERVICE_TABLES = frozenset({"django_migrations", "django_content_type", "auth_permission"})


class CloneMismatch(Exception):
    pass


# Имя схемы — только такое (кавычки/пробелы исключены: имена идут в DDL f-строками).
_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def valid_name(schema: str) -> bool:
    return bool(_NAME_RE.match(schema or "")) and not schema.startswith("pg_")


def name() -> str:
    value = str(getattr(settings, "TENANT_TEMPLATE_SCHEMA", "") or "")
    if value and not valid_name(value):
        log.error("TENANT_TEMPLATE_SCHEMA %r is not a valid schema name — template off", value)
        return ""
    return value


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
        tables = [row[0] for row in cursor.fetchall() if row[0] not in SERVICE_TABLES]
        if not tables:
            return []
        # Один запрос на все таблицы (а не по запросу на таблицу).
        probe = " UNION ALL ".join(
            f"SELECT %s WHERE EXISTS (SELECT 1 FROM {_q(schema)}.{_q(t)})"  # noqa: S608
            for t in tables
        )
        cursor.execute(probe, tables)
        return sorted(row[0] for row in cursor.fetchall())


def _q(identifier: str) -> str:
    return connection.ops.quote_name(identifier)


# Структура схемы из каталога Postgres (без данных). Сравнивается с шаблоном после копии.
_STRUCTURE_SQL = {
    "relations": """
        SELECT relname, relkind, relpersistence, coalesce(reloptions::text, '')
        FROM pg_class WHERE relnamespace = %s::regnamespace""",
    "columns": """
        SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull,
               coalesce(pg_get_expr(d.adbin, d.adrelid), ''), a.attidentity, a.attgenerated,
               coalesce(co.collname, '')
        FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
        LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
        LEFT JOIN pg_collation co ON co.oid = a.attcollation AND a.attcollation <> 0
        WHERE c.relnamespace = %s::regnamespace AND a.attnum > 0 AND NOT a.attisdropped""",
    "constraints": """
        SELECT cl.relname, c.conname, c.contype, pg_get_constraintdef(c.oid)
        FROM pg_constraint c JOIN pg_class cl ON cl.oid = c.conrelid
        WHERE cl.relnamespace = %s::regnamespace""",
    "indexes": "SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname = %s",
    "sequences": """
        SELECT sequencename, data_type, start_value, increment_by, min_value, max_value,
               cycle, cache_size
        FROM pg_sequences WHERE schemaname = %s""",
    "owned": """
        SELECT s.relname, t.relname, a.attname FROM pg_class s
        JOIN pg_depend d ON d.objid = s.oid AND d.deptype IN ('a', 'i')
        JOIN pg_class t ON t.oid = d.refobjid
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = d.refobjsubid
        WHERE s.relkind = 'S' AND s.relnamespace = %s::regnamespace""",
    "triggers": """
        SELECT c.relname, t.tgname, pg_get_triggerdef(t.oid)
        FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
        WHERE c.relnamespace = %s::regnamespace AND NOT t.tgisinternal""",
    "views": "SELECT viewname, definition FROM pg_views WHERE schemaname = %s",
    "functions": """
        SELECT proname, pg_get_function_identity_arguments(oid), md5(prosrc)
        FROM pg_proc WHERE pronamespace = %s::regnamespace""",
    "types": """
        SELECT typname, typtype FROM pg_type
        WHERE typnamespace = %s::regnamespace AND typtype NOT IN ('c', 'b')""",
}


def _normalizer(schema: str):
    """Убрать квалификатор СВОЕЙ схемы (`schema.` / `"schema".`) — только как отдельный
    токен, не внутри других слов."""
    pattern = re.compile(rf'(?<![\w"]){re.escape(schema)}\.|"{re.escape(schema)}"\.')

    def norm(value):
        return pattern.sub("", value) if isinstance(value, str) else value

    return norm


def structure(schema: str) -> dict[str, list[tuple]]:
    """Структура схемы без её имени — две разные схемы сравнимы напрямую."""
    norm = _normalizer(schema)
    out = {}
    with connection.cursor() as cursor:
        for key, sql in _STRUCTURE_SQL.items():
            cursor.execute(sql, [_q(schema) if "regnamespace" in sql else schema])
            out[key] = sorted((tuple(norm(v) for v in row) for row in cursor.fetchall()), key=repr)
        # Служебные таблицы копируются С ДАННЫМИ — их содержимое тоже часть сверки.
        for table in sorted(SERVICE_TABLES):
            cursor.execute(f"SELECT count(*) FROM {_q(schema)}.{_q(table)}")  # noqa: S608
            out[f"rows:{table}"] = [cursor.fetchone()]
    return out


def structure_diff(a: str, b: str) -> dict[str, tuple[list, list]]:
    sa, sb = structure(a), structure(b)
    return {
        key: (
            sorted(set(sa[key]) - set(sb[key]), key=repr),
            sorted(set(sb[key]) - set(sa[key]), key=repr),
        )
        for key in sb
        if sa[key] != sb[key]
    }


def _sequences_ahead(schema: str) -> list[str]:
    """Служебные таблицы: счётчик id не позади max(id) — иначе следующая вставка
    (новая миграция, тип содержимого) упала бы на дубле ключа."""
    behind = []
    with connection.cursor() as cursor:
        for table in sorted(SERVICE_TABLES):
            cursor.execute("SELECT pg_get_serial_sequence(%s, 'id')", [f"{_q(schema)}.{_q(table)}"])
            seq = cursor.fetchone()[0]
            if not seq:
                continue
            cursor.execute(
                f"SELECT (SELECT coalesce(max(id), 0) FROM {_q(schema)}.{_q(table)}), "  # noqa: S608
                f"last_value, is_called FROM {seq}"
            )
            top, last, called = cursor.fetchone()
            if top and (last < top or (last == top and not called)):
                behind.append(f"{table}: max(id)={top} last_value={last} is_called={called}")
    return behind


def _restore_constraint_names(source: str, target: str) -> None:
    """Функция копирования django-tenants пересоздаёт часть UNIQUE-ограничений с именами
    Postgres (`…_key`) вместо имён Django (`…_<hash>_uniq`). Будущая миграция, которая
    ищет ограничение по имени, на копии бы упала — возвращаем имена шаблона.

    Ключ — (таблица, тип, определение без имени схемы); одинаковые определения на одной
    таблице сопоставляются по порядку. Переименование в два шага (через временные имена),
    чтобы обмен именами не упирался в «already exists»."""
    sql = """
        SELECT cl.relname, c.conname, c.contype, pg_get_constraintdef(c.oid), c.oid
        FROM pg_constraint c JOIN pg_class cl ON cl.oid = c.conrelid
        WHERE cl.relnamespace = %s::regnamespace ORDER BY c.conname"""

    def grouped(schema):
        norm = _normalizer(schema)
        out: dict[tuple, list[tuple[str, int]]] = {}
        cursor.execute(sql, [_q(schema)])
        for table, cname, kind, definition, oid in cursor.fetchall():
            out.setdefault((table, kind, norm(definition)), []).append((cname, oid))
        return out

    with connection.cursor() as cursor:
        want, have = grouped(source), grouped(target)
        renames = []
        for key, items in have.items():
            names = [n for n, _oid in want.get(key, [])]
            for (now, oid), tpl in zip(items, names, strict=False):
                if now != tpl:
                    renames.append((key[0], now, tpl, oid))
        for table, now, _tpl, oid in renames:
            cursor.execute(
                f"ALTER TABLE {_q(target)}.{_q(table)} "
                f"RENAME CONSTRAINT {_q(now)} TO {_q(f'zz_tmp_{oid}')}"
            )
        for table, _now, tpl, oid in renames:
            cursor.execute(
                f"ALTER TABLE {_q(target)}.{_q(table)} "
                f"RENAME CONSTRAINT {_q(f'zz_tmp_{oid}')} TO {_q(tpl)}"
            )


_CLONE_FN = "public.clone_schema(text,text,public.cloneparms[])"


def install_clone_function() -> None:
    """Функция копирования django-tenants. Ставится ОДИН раз (шаг деплоя, под
    блокировкой), а не на каждую регистрацию: её установка — DROP TYPE … CASCADE и
    пересоздание функций в public."""
    from django_tenants.clone import CloneSchema

    CloneSchema()._create_clone_schema_function()


def _clone(source: str, target: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regprocedure(%s) IS NOT NULL", [_CLONE_FN])
        if not cursor.fetchone()[0]:
            # Установка трогает public (DROP TYPE … CASCADE) — по одной за раз.
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [INSTALL_LOCK_KEY])
            cursor.execute("SELECT to_regprocedure(%s) IS NOT NULL", [_CLONE_FN])
            if not cursor.fetchone()[0]:
                install_clone_function()
        cursor.execute("SELECT public.clone_schema(%s, %s, 'DATA')", [source, target])


def is_ready() -> bool:
    """Шаблон есть, свежий и чистый — копировать можно."""
    return exists() and not pending() and not dirty_tables()


def clone_into(schema: str) -> bool:
    """Создать `schema` копией шаблона. False — копия не сделана (вызывающий идёт путём
    миграций); схемы `schema` при этом нет."""
    from django_tenants.utils import schema_exists

    if not enabled() or schema == name() or not valid_name(schema):
        return False
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                # Общая (shared) блокировка: копии идут параллельно друг другу (`--jobs`,
                # одновременные регистрации); исключает их только пересборка шаблона.
                cursor.execute("SELECT pg_try_advisory_xact_lock_shared(%s)", [LOCK_KEY])
                if not cursor.fetchone()[0]:
                    log.info("schema template busy, %s via migrations", schema)
                    return False
            if not is_ready():
                log.warning("schema template not ready, %s via migrations", schema)
                return False
            if schema_exists(schema):
                return False
            connection.set_schema_to_public()
            _clone(name(), schema)
            _restore_constraint_names(name(), schema)
            diff = structure_diff(schema, name())
            if diff or _sequences_ahead(schema):
                # Копия не совпала с шаблоном — откат всей транзакции (схемы не будет).
                raise CloneMismatch(sorted(diff) or _sequences_ahead(schema))
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
