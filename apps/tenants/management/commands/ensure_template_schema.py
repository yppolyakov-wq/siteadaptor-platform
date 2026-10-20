"""T-10 D-1: создать или освежить шаблонную схему (шаг деплоя, идемпотентно).

- шаблона нет → `CREATE SCHEMA` + миграции TENANT-приложений;
- шаблон есть → те же миграции (нечего применять — секунды);
- в шаблоне оказались данные бизнеса → отказ (код 1); `--force` пересоздаёт его.

Держит ту же advisory-блокировку, что копирование: пока шаблон мигрирует, новые схемы
создаются прежним путём миграциями, а не копией полумигрированного шаблона.
"""

import sys

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection

from apps.tenants import schema_template


class Command(BaseCommand):
    help = "Создать/освежить шаблонную схему для быстрого создания схем бизнесов."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Пересоздать шаблон, если в нём оказались данные.",
        )

    def handle(self, *args, **options):
        from django_tenants.postgresql_backend.base import _check_schema_name
        from django_tenants.utils import get_public_schema_name, get_tenant_model

        name = schema_template.name()
        if not name:
            self.stdout.write("Шаблонная схема выключена (TENANT_TEMPLATE_SCHEMA пуст).")
            return
        _check_schema_name(name)
        if name == get_public_schema_name() or (
            get_tenant_model().objects.filter(schema_name=name).exists()
        ):
            self.stderr.write(self.style.ERROR(f"Схема {name} принадлежит бизнесу — отказ."))
            sys.exit(1)
        connection.set_schema_to_public()
        from django.db import OperationalError

        try:
            with connection.cursor() as cursor:
                # Копии держат блокировку до конца СВОЕЙ внешней транзакции — не ждём вечно.
                cursor.execute("SET lock_timeout = '120s'")
                cursor.execute("SELECT pg_advisory_lock(%s)", [schema_template.LOCK_KEY])
                cursor.execute("SET lock_timeout = 0")
        except OperationalError:
            self.stderr.write(self.style.ERROR("Шаблон занят копированием — повторите позже."))
            sys.exit(1)
        try:
            schema_template.install_clone_function()
            self._ensure(name, force=options["force"])
        finally:
            connection.set_schema_to_public()
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [schema_template.LOCK_KEY])

    def _ensure(self, name: str, *, force: bool) -> None:
        if schema_template.exists():
            dirty = schema_template.dirty_tables()
            if dirty:
                if not force:
                    self.stderr.write(
                        self.style.ERROR(
                            f"В шаблоне {name} есть данные ({', '.join(dirty[:5])}). "
                            "Пересоздать: --force"
                        )
                    )
                    sys.exit(1)
                self._drop(name)
        created = not schema_template.exists()
        if created:
            with connection.cursor() as cursor:
                cursor.execute(f'CREATE SCHEMA "{name}"')
        call_command(
            "migrate_schemas",
            tenant=True,
            schema_name=name,
            interactive=False,
            verbosity=0,
        )
        connection.set_schema_to_public()
        left = schema_template.pending()
        if left or schema_template.dirty_tables():
            self.stderr.write(self.style.ERROR(f"Шаблон {name} не готов: {left[:5]}"))
            sys.exit(1)
        self.stdout.write(self.style.SUCCESS(f"Шаблон {name} {'создан' if created else 'свежий'}."))

    def _drop(self, name: str) -> None:
        with connection.cursor() as cursor:
            cursor.execute(f'DROP SCHEMA "{name}" CASCADE')
