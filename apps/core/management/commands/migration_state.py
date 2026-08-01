"""Сверка применённых миграций по ВСЕМ схемам (2026-08-01).

Зачем: `manage.py showmigrations` без tenant-контекста читает `django_migrations`
схемы **public**, а TENANT-приложения держат свою таблицу в КАЖДОЙ схеме тенанта.
Поэтому «на проде всё [X]» по обычному showmigrations — утверждение только про
public-часть, и очередь миграций в памяти проекта из-за этого разъезжалась с
реальностью (аудит 2026-08-01: числилось ~30 «ожидающих», применено было всё).

Печатает ТОЛЬКО неприменённое — вывод короткий и его можно целиком вставить в
переписку. Ничего не меняет в БД: read-only.
"""

from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.loader import MigrationLoader


class Command(BaseCommand):
    help = "Показать НЕприменённые миграции по всем схемам (public + тенанты)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            help="Печатать и схемы, где всё применено (по умолчанию — только проблемные).",
        )
        parser.add_argument(
            "--schema",
            default="",
            help="Проверить одну схему вместо всех.",
        )

    def handle(self, *args, **options):
        from django.conf import settings
        from django_tenants.utils import (
            app_labels,
            get_public_schema_name,
            get_tenant_model,
            schema_exists,
        )

        public = get_public_schema_name()
        shared = set(app_labels(settings.SHARED_APPS))
        tenant = set(app_labels(settings.TENANT_APPS))

        only = options["schema"]
        if only:
            schemas = [only]
        else:
            schemas = [public] + list(
                get_tenant_model()
                .objects.exclude(schema_name=public)
                .order_by("schema_name")
                .values_list("schema_name", flat=True)
            )

        # Группируем ПО МИГРАЦИИ, а не по схеме: у тенантов отстаёт обычно один и
        # тот же хвост, и построчный вывод на полсотни схем был бы простынёй.
        by_migration: dict[tuple[str, str], list[str]] = {}
        ok_schemas, missing = [], []
        for schema in schemas:
            # Строка Tenant может существовать без схемы (провалившийся
            # провижининг). Такую честно называем отсутствующей: сказать про неё
            # «миграции не применены» значило бы отправить владельца чинить не то.
            if not schema_exists(schema):
                missing.append(schema)
                continue
            # Приложения схемы: в public живут SHARED, в схеме тенанта — TENANT.
            # Приложение из обоих списков (напр. core) мигрируется в обеих.
            wanted = shared if schema == public else tenant
            pending = self._pending(schema, wanted)
            if not pending:
                ok_schemas.append(schema)
                continue
            for key in pending:
                by_migration.setdefault(key, []).append(schema)

        checked = len(schemas) - len(missing)
        if missing:
            self.stdout.write(
                self.style.ERROR(f"СХЕМЫ ОТСУТСТВУЮТ ({len(missing)}): {', '.join(missing)}")
            )
        if options["all"]:
            for schema in ok_schemas:
                self.stdout.write(f"{schema}: ок")
        for (app, name), where in sorted(by_migration.items()):
            head = self.style.WARNING(f"{app}.{name}")
            if len(where) == checked:
                self.stdout.write(f"{head} — не применена НИГДЕ ({checked} схем)")
            else:
                shown = ", ".join(where[:5]) + (
                    f" и ещё {len(where) - 5}" if len(where) > 5 else ""
                )
                self.stdout.write(f"{head} — не применена в {len(where)}: {shown}")

        tail = f"схем проверено: {checked}"
        if by_migration:
            self.stdout.write(
                self.style.ERROR(f"ИТОГО отстающих миграций: {len(by_migration)} ({tail})")
            )
        else:
            self.stdout.write(self.style.SUCCESS(f"Всё применено ({tail})"))

    def _pending(self, schema: str, wanted: set[str]) -> list[tuple[str, str]]:
        """Миграции на диске, которых нет в `django_migrations` этой схемы.

        Загрузчик читает таблицу ТЕКУЩЕГО search_path, поэтому переключение схемы
        и есть весь фокус: одна и та же миграция может быть применена в одной
        схеме и отсутствовать в другой.
        """
        from django_tenants.utils import schema_context

        with schema_context(schema):
            loader = MigrationLoader(connection, ignore_no_migrations=True)
            applied = set(loader.applied_migrations or ())
            return sorted(
                (app, name)
                for app, name in loader.disk_migrations
                if app in wanted and (app, name) not in applied
            )
