"""Тесты задач preview_import / run_import.

Задачи вызываются синхронно через нижележащую функцию task'а
(idempotent_task возвращает Celery task; вызываем её напрямую, не .delay).
В тестах схема — public, все приложения SHARED (config.settings.test).
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.catalog.models import Product
from apps.imports.models import ImportJob
from apps.imports.tasks import preview_import, run_import

CSV = (
    "Name,Preis,SKU\n"
    "Brot,2.50,BR-1\n"
    "Kuchen,,KU-1\n"  # пустая цена → ошибка
    "Milch,1.20,ML-1\n"
)

MAPPING = {"Name": "name_de", "Preis": "base_price", "SKU": "sku"}


def _make_job(**options):
    return ImportJob.objects.create(
        resource_type="product",
        status="mapped",
        source_file=SimpleUploadedFile("p.csv", CSV.encode("utf-8")),
        column_mapping=MAPPING,
        options=options,
    )


@pytest.mark.django_db
def test_preview_counts_ok_and_error():
    job = _make_job()
    preview_import(dedupe_key=None, schema_name="public", job_id=str(job.id))
    job.refresh_from_db()
    assert job.status == "previewed"
    assert job.total_rows == 3
    assert job.ok_rows == 2
    assert job.error_rows == 1
    assert job.rows.filter(status="ok").count() == 2
    assert job.rows.filter(status="error").count() == 1


@pytest.mark.django_db
def test_run_creates_products():
    job = _make_job()
    preview_import(dedupe_key=None, schema_name="public", job_id=str(job.id))
    run_import(dedupe_key=None, schema_name="public", job_id=str(job.id))
    job.refresh_from_db()
    assert job.status == "completed"
    assert job.processed_rows == 2
    assert Product.objects.filter(sku="BR-1").exists()
    assert Product.objects.filter(sku="ML-1").exists()
    assert not Product.objects.filter(sku="KU-1").exists()


@pytest.mark.django_db
def test_run_update_existing_does_not_duplicate():
    Product.objects.create(name={"de": "Old"}, base_price="0.50", sku="BR-1")
    job = _make_job(update_existing=True)
    preview_import(dedupe_key=None, schema_name="public", job_id=str(job.id))
    run_import(dedupe_key=None, schema_name="public", job_id=str(job.id))
    assert Product.objects.filter(sku="BR-1").count() == 1
    updated = Product.objects.get(sku="BR-1")
    assert updated.name["de"] == "Brot"
