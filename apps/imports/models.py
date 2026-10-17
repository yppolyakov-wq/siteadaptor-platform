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


class SiteImportRun(TimestampedModel):
    """T-8.27: один прогон импорта с сайта клиента (обход → черновик → применение).

    Согласие владельца фиксируется на прогоне (когда, кто, какой текст); тела страниц
    не храним — только журнал обхода и извлечённые кандидаты (`items`)."""

    STATUS_QUEUED = "queued"
    STATUS_CRAWLING = "crawling"
    STATUS_READY = "ready"
    STATUS_APPLIED = "applied"
    STATUS_FAILED = "failed"
    ACTIVE = (STATUS_QUEUED, STATUS_CRAWLING)
    STATUSES = [
        (STATUS_QUEUED, "queued"),
        (STATUS_CRAWLING, "crawling"),
        (STATUS_READY, "ready"),
        (STATUS_APPLIED, "applied"),
        (STATUS_FAILED, "failed"),
    ]

    start_url = models.URLField(max_length=500)
    host = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUSES, default=STATUS_QUEUED)
    consent_at = models.DateTimeField()
    consent_by_id = models.IntegerField(null=True, blank=True)  # User схемы тенанта
    consent_version = models.CharField(max_length=20)
    pages = models.JSONField(default=list, blank=True)  # журнал обхода: url/status/bytes
    html_lang = models.CharField(max_length=8, blank=True)
    method = models.CharField(max_length=20, blank=True)  # structured | ai | mixed
    ai_used = models.BooleanField(default=False)
    error_code = models.CharField(max_length=40, blank=True)
    profile = models.JSONField(default=dict, blank=True)  # кандидат профиля бизнеса
    stats = models.JSONField(default=dict, blank=True)
    previous_run = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "created_at"], name="siterun_status_idx")]

    def __str__(self):
        return f"Website-Import {self.host} [{self.status}]"


class SiteImportItem(TimestampedModel):
    """Кандидат позиции из прогона: данные, статус дифа, решение владельца, цель."""

    DIFF_NEW = "new"
    DIFF_CHANGED = "changed"
    DIFF_UNCHANGED = "unchanged"
    DIFF_REMOVED = "removed"
    DIFFS = [(d, d) for d in (DIFF_NEW, DIFF_CHANGED, DIFF_UNCHANGED, DIFF_REMOVED)]
    DECISIONS = [(d, d) for d in ("pending", "accepted", "skipped")]

    run = models.ForeignKey(SiteImportRun, related_name="items", on_delete=models.CASCADE)
    kind = models.CharField(max_length=20)  # product | service
    diff = models.CharField(max_length=20, choices=DIFFS, default=DIFF_NEW)
    decision = models.CharField(max_length=20, choices=DECISIONS, default="pending")
    source_url = models.URLField(max_length=500, blank=True)
    data = models.JSONField(default=dict)
    fingerprint = models.CharField(max_length=64)
    identity_key = models.CharField(max_length=64, db_index=True)
    ai_generated = models.BooleanField(default=False)
    target_kind = models.CharField(max_length=20, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)  # шов Г3 (автопротухание)
    errors = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["run", "diff"], name="siteitem_run_diff_idx")]

    def __str__(self):
        return f"{self.kind}: {self.data.get('name', '')}"
