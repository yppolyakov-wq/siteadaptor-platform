"""P0-2 (аудит 2026-09-03 §9.3): убрать легаси-загрузки импорта из общего /media/.

До правки файлы мастера импорта ложились как `imports/<исходное имя>` и жили
вечно; гейт `core.media_views` их больше не отдаёт, а новые импорты удаляют
файл сами (`tasks.drop_source_file`). Остаток — уже лежащее в проде: файлы
завершённых импортов и брошенные/упавшие загрузки. Команда проходит КАЖДУЮ
схему тенанта (ImportJob — tenant-модель):

* status=completed — файл удаляется всегда (строки давно в job.rows);
* прочие статусы — если job не обновлялся дольше `--older-than-days` (30):
  брошенная загрузка/упавший импорт, повтор всё равно = новая загрузка.

По умолчанию dry-run (как `rotate_secrets`); `--apply` пишет. Идемпотентна:
после удаления поле очищено, повторный прогон ничего не находит; файл, уже
пропавший из storage, просто отвязывается. Ошибка в одной схеме не валит обход.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, get_tenant_model, schema_context

from apps.imports.models import ImportJob
from apps.imports.tasks import drop_source_file


class Command(BaseCommand):
    help = "Удалить файлы завершённых/брошенных импортов из /media/ (dry-run; --apply пишет)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Удалять (иначе только отчёт).")
        parser.add_argument(
            "--older-than-days",
            type=int,
            default=30,
            help="Незавершённые импорты без обновлений дольше N дней тоже чистим (30).",
        )

    def handle(self, *args, apply=False, older_than_days=30, **options):
        mode = "apply" if apply else "dry-run"
        total = 0
        tenant_model = get_tenant_model()
        schemas = tenant_model.objects.exclude(schema_name=get_public_schema_name()).values_list(
            "schema_name", flat=True
        )
        for schema in schemas:
            try:
                with schema_context(schema):
                    n = self._schema(apply, older_than_days)
            except Exception as exc:  # noqa: BLE001 — одна схема не валит обход
                self.stderr.write(f"{schema}: ОШИБКА {exc!r}")
                continue
            if n:
                self.stdout.write(f"{schema}: {n}")
            total += n
        self.stdout.write(f"[{mode}] файлов импорта к удалению: {total}")

    def _schema(self, apply: bool, older_than_days: int) -> int:
        stale_before = timezone.now() - timedelta(days=older_than_days)
        jobs = ImportJob.objects.exclude(source_file="")
        completed = jobs.filter(status="completed")
        stale = jobs.exclude(status="completed").filter(updated_at__lt=stale_before)
        n = 0
        for job in list(completed) + list(stale):
            n += 1
            if apply:
                drop_source_file(job)
        return n
