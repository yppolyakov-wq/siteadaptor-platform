"""Celery-задачи импорта: preview (dry-run) и run (запись).

Задачи выполняются ВНЕ tenant-контекста → вся работа с БД оборачивается в
schema_context(schema_name). Идемпотентность — через idempotent_task
(dedupe по dedupe_key). См. docs/references/patterns/csv-import-wizard.md.
"""

import traceback

from django.db import transaction
from django_tenants.utils import schema_context

from apps.core.jobs import idempotent_task

from .csvutil import apply_mapping, read_rows
from .models import ImportJob, ImportRow
from .processors import get_processor

BATCH_SIZE = 500


def _mark_failed(schema_name, job_id, exc):
    """Пометить job как failed с текстом ошибки (best-effort)."""
    try:
        with schema_context(schema_name):
            job = ImportJob.objects.filter(id=job_id).first()
            if job is not None:
                job.status = "failed"
                job.error_summary = (str(exc) or repr(exc))[:5000]
                job.save(update_fields=["status", "error_summary", "updated_at"])
    except Exception:  # noqa: BLE001 — не маскируем исходную ошибку падением here
        pass


@idempotent_task()
def preview_import(dedupe_key=None, schema_name=None, job_id=None):
    """Dry-run: прогнать все строки через validate() без записи в БД."""
    try:
        with schema_context(schema_name):
            job = ImportJob.objects.get(id=job_id)
            processor = get_processor(job.resource_type)

            # перезапуск превью не должен задваивать строки
            job.rows.all().delete()

            delimiter = (job.options or {}).get("delimiter")
            total = ok = error = 0
            for line_no, raw in enumerate(
                read_rows(job.source_file, delimiter_key=delimiter), start=1
            ):
                data = apply_mapping(raw, job.column_mapping)
                errors = processor.validate(data)
                ImportRow.objects.create(
                    job=job,
                    line_no=line_no,
                    raw=raw,
                    status="error" if errors else "ok",
                    errors=errors,
                )
                total += 1
                if errors:
                    error += 1
                else:
                    ok += 1

            job.total_rows = total
            job.ok_rows = ok
            job.error_rows = error
            job.status = "previewed"
            job.save(
                update_fields=[
                    "total_rows",
                    "ok_rows",
                    "error_rows",
                    "status",
                    "updated_at",
                ]
            )
    except Exception as exc:  # noqa: BLE001
        _mark_failed(schema_name, job_id, f"{exc}\n{traceback.format_exc()}")
        raise


@idempotent_task()
def run_import(dedupe_key=None, schema_name=None, job_id=None):
    """Запись валидных строк батчами (транзакция на батч)."""
    try:
        with schema_context(schema_name):
            job = ImportJob.objects.get(id=job_id)
            processor = get_processor(job.resource_type)
            update_existing = bool(job.options.get("update_existing", False))
            match_field = (job.options or {}).get("match_field") or "sku"

            job.status = "running"
            job.processed_rows = 0
            job.save(update_fields=["status", "processed_rows", "updated_at"])

            ok_rows = list(job.rows.filter(status="ok").order_by("line_no"))
            processed = 0
            for start in range(0, len(ok_rows), BATCH_SIZE):
                batch = ok_rows[start : start + BATCH_SIZE]
                with transaction.atomic():
                    for row in batch:
                        data = apply_mapping(row.raw, job.column_mapping)
                        obj = processor.create_or_update(
                            data, update_existing=update_existing, match_field=match_field
                        )
                        row.created_object_id = str(obj.pk)
                    ImportRow.objects.bulk_update(batch, ["created_object_id"])
                processed += len(batch)
                job.processed_rows = processed
                job.save(update_fields=["processed_rows", "updated_at"])

            job.status = "completed"
            job.save(update_fields=["status", "updated_at"])
    except Exception as exc:  # noqa: BLE001
        _mark_failed(schema_name, job_id, f"{exc}\n{traceback.format_exc()}")
        raise
