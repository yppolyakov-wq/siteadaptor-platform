"""FB-29.2: перенос прежних слайдов баннера главной в библиотеку «Website › Banner».

По всем схемам тенантов (или --schema). Перенос делается один раз: повторный запуск ничего
не создаёт. `--undo` возвращает как было — перенесённые записи удаляются (в том числе
поправленные владельцем после переноса), прежние слайды в настройках не трогались.
Сбой в одной схеме не останавливает остальные; команда завершается ошибкой со списком.
"""

from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import schema_context

from apps.core import banners
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "FB-29.2: перенести слайды баннера главной в библиотеку баннеров"

    def add_arguments(self, parser):
        parser.add_argument("--schema", default="", help="одна схема (иначе все тенанты)")
        parser.add_argument("--undo", action="store_true", help="обратный ход переноса")

    def handle(self, *args, **options):
        if options["schema"] == "public":
            raise CommandError("public — не схема бизнеса")
        if options["schema"]:
            if not Tenant.objects.filter(schema_name=options["schema"]).exists():
                raise CommandError(f"нет такого тенанта: {options['schema']}")
            schemas = [options["schema"]]
        else:
            schemas = list(
                Tenant.objects.exclude(schema_name="public").values_list("schema_name", flat=True)
            )
        created = skipped = removed = 0
        failed = []
        for schema in schemas:
            tenant = Tenant.objects.filter(schema_name=schema).first()
            try:
                with schema_context(schema):
                    if options["undo"]:
                        count = banners.undo_legacy(tenant)
                        removed += count
                        if count:
                            self.stdout.write(f"{schema}: -{count}")
                    else:
                        report = banners.import_legacy(tenant)
                        created += report["created"]
                        skipped += report["skipped"]
                        if report["created"] or report["skipped"]:
                            self.stdout.write(
                                f"{schema}: +{report['created']}, пропущено {report['skipped']}"
                            )
            except Exception as exc:  # noqa: BLE001 — одна схема не останавливает остальные
                failed.append(schema)
                self.stderr.write(f"{schema}: ОШИБКА {type(exc).__name__}: {exc}")
        if options["undo"]:
            self.stdout.write(f"Удалено {removed}")
        else:
            self.stdout.write(f"Создано {created}, пропущено {skipped}")
        if failed:
            raise CommandError(f"не обработаны схемы: {', '.join(failed)}")
        self.stdout.write(self.style.SUCCESS("Готово"))
