"""View'ы wizard'а импорта (все требуют логина).

Шаги: start (upload) → map → preview → status. Задачи ставятся в очередь
с передачей schema_name (connection.schema_name), т.к. Celery работает вне
tenant-контекста.
"""

from django.contrib.auth.decorators import login_required
from django.db import connection
from django.shortcuts import get_object_or_404, redirect, render

from .csvutil import read_headers
from .forms import ImportUploadForm
from .models import ImportJob
from .tasks import preview_import, run_import

# логические поля товара для маппинга колонок
PRODUCT_FIELDS = [
    ("name_de", "Name (DE) *"),
    ("name_en", "Name (EN)"),
    ("description_de", "Beschreibung (DE)"),
    ("description_en", "Beschreibung (EN)"),
    ("sku", "SKU"),
    ("base_price", "Preis *"),
    ("currency", "Währung"),
    ("stock_quantity", "Lagerbestand"),
    ("category_slug", "Kategorie (slug)"),
    ("is_active", "Aktiv"),
]

# Выбор разделителя CSV (значение → подпись).
DELIMITER_CHOICES = [
    ("auto", "Auto"),
    ("comma", "Komma  ,"),
    ("semicolon", "Semikolon  ;"),
    ("tab", "Tab"),
    ("pipe", "Pipe  |"),
]

# Поле, по которому ищем существующий товар при обновлении.
MATCH_FIELD_CHOICES = [
    ("sku", "SKU"),
    ("name_de", "Name (DE)"),
]


@login_required
def import_start(request):
    form = ImportUploadForm()
    if request.method == "POST":
        form = ImportUploadForm(request.POST, request.FILES)
        if form.is_valid():
            job = ImportJob.objects.create(
                resource_type="product",
                status="uploaded",
                source_file=form.cleaned_data["source_file"],
            )
            return redirect("imports:map", pk=job.pk)

    jobs = ImportJob.objects.all()[:20]
    return render(
        request,
        "imports/import_start.html",
        {"form": form, "jobs": jobs, "nav": "imports"},
    )


@login_required
def import_map(request, pk):
    job = get_object_or_404(ImportJob, pk=pk)

    if request.method == "POST":
        delimiter = request.POST.get("delimiter", "auto")
        mapping = {}
        # заголовки читаем уже выбранным разделителем
        for header in read_headers(job.source_file, delimiter_key=delimiter):
            logical = request.POST.get(f"map__{header}", "").strip()
            if logical:
                mapping[header] = logical
        job.column_mapping = mapping
        job.options = {
            **(job.options or {}),
            "delimiter": delimiter,
            "update_existing": bool(request.POST.get("update_existing")),
            "match_field": request.POST.get("match_field", "sku"),
        }
        job.status = "mapped"
        job.save(update_fields=["column_mapping", "options", "status", "updated_at"])

        preview_import.delay(
            dedupe_key=f"preview:{job.id}",
            schema_name=connection.schema_name,
            job_id=str(job.id),
        )
        return redirect("imports:preview", pk=job.pk)

    # GET: показываем заголовки по авто-определённому разделителю
    headers = read_headers(job.source_file)
    return render(
        request,
        "imports/import_map.html",
        {
            "job": job,
            "headers": headers,
            "fields": PRODUCT_FIELDS,
            "delimiters": DELIMITER_CHOICES,
            "match_fields": MATCH_FIELD_CHOICES,
            "nav": "imports",
        },
    )


@login_required
def import_preview(request, pk):
    job = get_object_or_404(ImportJob, pk=pk)

    if request.method == "POST":
        run_import.delay(
            dedupe_key=f"run:{job.id}",
            schema_name=connection.schema_name,
            job_id=str(job.id),
        )
        return redirect("imports:status", pk=job.pk)

    error_rows = job.rows.filter(status="error")[:50]
    return render(
        request,
        "imports/import_preview.html",
        {"job": job, "error_rows": error_rows, "nav": "imports"},
    )


@login_required
def import_status(request, pk):
    job = get_object_or_404(ImportJob, pk=pk)
    template = (
        "imports/_status_card.html"
        if request.headers.get("HX-Request")
        else "imports/import_status.html"
    )
    return render(request, template, {"job": job, "nav": "imports"})
