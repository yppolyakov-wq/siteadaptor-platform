"""Тесты чтения Excel и сквозного импорта .xlsx через tabular-диспетчер."""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook

from apps.catalog.models import Product
from apps.imports.models import ImportJob
from apps.imports.tabular import read_headers, read_rows
from apps.imports.tasks import preview_import, run_import

MAPPING = {"Name": "name_de", "Preis": "base_price", "SKU": "sku"}


def _xlsx_bytes():
    wb = Workbook()
    ws = wb.active
    ws.append(["Name", "Preis", "SKU"])
    ws.append(["Brot", 2.50, "BR-1"])
    ws.append(["Kuchen", None, "KU-1"])  # пустая цена → ошибка
    ws.append(["Milch", 1.20, "ML-1"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _make_job(**options):
    return ImportJob.objects.create(
        resource_type="product",
        status="mapped",
        source_file=SimpleUploadedFile("p.xlsx", _xlsx_bytes()),
        column_mapping=MAPPING,
        options=options,
    )


def test_read_headers_xlsx():
    f = SimpleUploadedFile("p.xlsx", _xlsx_bytes())
    assert read_headers(f) == ["Name", "Preis", "SKU"]


def test_read_rows_xlsx():
    f = SimpleUploadedFile("p.xlsx", _xlsx_bytes())
    rows = list(read_rows(f))
    assert len(rows) == 3
    assert rows[0]["Name"] == "Brot"
    assert rows[0]["SKU"] == "BR-1"


@pytest.mark.django_db
def test_xlsx_preview_and_run():
    job = _make_job()
    preview_import(dedupe_key=None, schema_name="public", job_id=str(job.id))
    job.refresh_from_db()
    assert job.status == "previewed"
    assert job.total_rows == 3
    assert job.ok_rows == 2
    assert job.error_rows == 1

    run_import(dedupe_key=None, schema_name="public", job_id=str(job.id))
    job.refresh_from_db()
    assert job.status == "completed"
    assert Product.objects.filter(sku="BR-1").exists()
    assert Product.objects.filter(sku="ML-1").exists()
    assert not Product.objects.filter(sku="KU-1").exists()
