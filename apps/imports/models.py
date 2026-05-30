"""Модели импорта (TENANT-схема): ImportJob + ImportRow.

4-шаговый wizard: uploaded → mapped → previewed → running → completed | failed.
Спецификация: docs/references/patterns/csv-import-wizard.md.
"""

from django.db import models

from apps.core.models import TimestampedModel


class ImportJob(TimestampedModel):
    """Задание импорта: один загруженный файл и его конвейер обработки."""

    STATUS = ["uploaded", "mapped", "previewed", "running", "completed", "failed"]

    resource_type = models.CharField(max_length=50, default="product")
    status = models.CharField(max_length=20, default="uploaded", db_index=True)
    source_file = models.FileField(upload_to="imports/")
    # сопоставление колонок файла → логические поля: {"Name": "name_de", "Preis": "base_price"}
    column_mapping = models.JSONField(default=dict, blank=True)
    options = models.JSONField(default=dict, blank=True)  # update_existing, delimiter...

    total_rows = models.IntegerField(default=0)
    processed_rows = models.IntegerField(default=0)
    ok_rows = models.IntegerField(default=0)
    error_rows = models.IntegerField(default=0)
    error_summary = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Import {self.resource_type} [{self.status}]"


class ImportRow(TimestampedModel):
    """Одна строка исходного файла + результат её валидации/записи."""

    job = models.ForeignKey(
        ImportJob,
        related_name="rows",
        on_delete=models.CASCADE,
    )
    line_no = models.IntegerField()
    raw = models.JSONField(default=dict)  # исходная строка как dict
    status = models.CharField(max_length=20, default="pending")  # ok|error|skipped|pending
    errors = models.JSONField(default=list, blank=True)
    created_object_id = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["line_no"]
        indexes = [
            models.Index(fields=["job", "status"], name="importrow_job_status_idx"),
        ]

    def __str__(self):
        return f"Row {self.line_no} [{self.status}]"
