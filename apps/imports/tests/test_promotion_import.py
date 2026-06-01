"""Тест импорта акций через wizard (preview + run)."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.imports.models import ImportJob
from apps.imports.tasks import preview_import, run_import
from apps.promotions.models import Promotion

CSV = (
    "Titel,Rabatt,Menge\n"
    "Sommeraktion,20,50\n"
    ",10,5\n"  # без title → ошибка
)

MAPPING = {"Titel": "title_de", "Rabatt": "discount_percent", "Menge": "available_quantity"}


def _job(**options):
    return ImportJob.objects.create(
        resource_type="promotion",
        status="mapped",
        source_file=SimpleUploadedFile("p.csv", CSV.encode("utf-8")),
        column_mapping=MAPPING,
        options=options,
    )


@pytest.mark.django_db
def test_promotion_preview_counts():
    job = _job()
    preview_import(dedupe_key=None, schema_name="public", job_id=str(job.id))
    job.refresh_from_db()
    assert job.status == "previewed"
    assert job.total_rows == 2
    assert job.ok_rows == 1
    assert job.error_rows == 1


@pytest.mark.django_db
def test_promotion_run_creates_draft():
    job = _job()
    preview_import(dedupe_key=None, schema_name="public", job_id=str(job.id))
    run_import(dedupe_key=None, schema_name="public", job_id=str(job.id))
    job.refresh_from_db()
    assert job.status == "completed"
    promo = Promotion.objects.get(title__de="Sommeraktion")
    assert promo.status == "draft"
    assert promo.discount_percent == 20
    assert promo.available_quantity == 50
