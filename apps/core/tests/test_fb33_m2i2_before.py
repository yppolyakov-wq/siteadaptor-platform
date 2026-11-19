"""FB-33 M2i-2-0: характеризация PDF сметы ДО своих вопросов заявки.

План — `docs/fb33-editor-model-2026-11-19.md` §«План M2i». Снимок текста PDF сметы снят до
кода M2i-2: заявка без ответов на свои вопросы (`custom_answers` пуст) печатается байт-в-байт
как раньше. Форма заявки и письмо владельцу — снимки M2i-0 (`golden_fb33m2i`).

Обновить (осознанно): FB33M2I2_GOLDEN=update uv run pytest <этот файл>
"""

import io
import os
import re
from pathlib import Path

import pytest
from django.utils import translation

pytestmark = pytest.mark.django_db
GOLDEN = Path(__file__).parent / "golden_fb33m2i"
UPDATE = os.environ.get("FB33M2I2_GOLDEN") == "update"


def _quote_text(job) -> str:
    from pypdf import PdfReader

    from apps.jobs.pdf import build_quote_pdf
    from apps.tenants.tests.factories import TenantFactory

    tenant = TenantFactory.build(name="Malerei X", address="Hauptstr. 1", city="Solingen")
    pdf = build_quote_pdf(job, tenant)
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
    text = re.sub(r"\b\d{2}\.\d{2}\.\d{4}( \d{2}:\d{2})?", "DATE", text)
    return text.replace(job.reference_code, "CODE")


def quote_job(**extra):
    from apps.jobs import services

    job = services.create_job(
        title="Zaun streichen",
        name="Herr Meyer",
        email="m@t.de",
        description="Bitte bis Mai.",
        site_address="Gartenweg 2",
        guest_count=None,
        **extra,
    )
    services.set_lines(job, [{"text": "Arbeit", "qty": 4, "unit_price": "50.00"}])
    job.refresh_from_db()
    return job


def check(name, got):
    path = GOLDEN / f"{name}.txt"
    if UPDATE or not path.exists():
        if not UPDATE:
            pytest.fail(f"нет снимка {path.name}: FB33M2I2_GOLDEN=update")
        path.write_text(got)
        return
    assert got == path.read_text(), f"PDF сметы изменился: {path.name}"


def test_quote_pdf_before():
    with translation.override("de"):
        check("pdf-quote", _quote_text(quote_job()))
