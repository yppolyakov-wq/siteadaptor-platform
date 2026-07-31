"""View'ы wizard'а импорта (все требуют логина).

Шаги: start (upload) → map → preview → status. Задачи ставятся в очередь
с передачей schema_name (connection.schema_name), т.к. Celery работает вне
tenant-контекста.
"""

from django.contrib.auth.decorators import login_required
from django.db import connection
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _

from .forms import ImportUploadForm
from .models import ImportJob
from .tabular import read_headers
from .tasks import preview_import, run_import

# логические поля товара для маппинга колонок
PRODUCT_FIELDS = [
    ("name_de", _("Name (DE) *")),
    ("name_en", _("Name (EN)")),
    ("description_de", _("Beschreibung (DE)")),
    ("description_en", _("Beschreibung (EN)")),
    ("sku", _("SKU")),
    ("base_price", _("Preis *")),
    ("currency", _("Währung")),
    ("stock_quantity", _("Lagerbestand")),
    ("category_slug", _("Kategorie (slug)")),
    ("is_active", _("Aktiv")),
]

# Выбор разделителя CSV (значение → подпись).
DELIMITER_CHOICES = [
    ("auto", _("Auto")),
    ("comma", _("Komma  ,")),
    ("semicolon", _("Semikolon  ;")),
    ("tab", _("Tab")),
    ("pipe", _("Pipe  |")),
]

# логические поля варианта товара (R1, A1): родитель + атрибуты варианта
VARIANT_FIELDS = [
    ("product_sku", _("Produkt-SKU *")),
    ("product_name_de", _("Produkt-Name (DE) *")),
    ("label", _("Variante (z. B. 100 g, M) *")),
    ("sku", _("Varianten-SKU")),
    ("gtin", _("EAN/GTIN")),
    ("price", _("Preis (leer = Grundpreis)")),
    ("content_amount", _("Inhalt (Grundpreis)")),
    ("stock_quantity", _("Lagerbestand")),
    ("is_active", _("Aktiv")),
]

# логические поля акции для маппинга колонок
PROMOTION_FIELDS = [
    ("title_de", _("Titel (DE) *")),
    ("title_en", _("Titel (EN)")),
    ("description_de", _("Beschreibung (DE)")),
    ("description_en", _("Beschreibung (EN)")),
    ("product_sku", _("Produkt-SKU")),
    ("promo_type", _("Typ (reservation/discount)")),
    ("discount_percent", _("Rabatt %")),
    ("price_override", _("Neuer Preis")),
    ("compare_at_price", _("Alter Preis")),
    ("available_quantity", _("Menge")),
    ("max_per_customer", _("Max pro Kunde")),
    ("reservation_ttl_hours", _("Reservierung gültig (Std.)")),
    ("auto_confirm", _("Auto-Bestätigung")),
    ("starts_at", _("Start (YYYY-MM-DD HH:MM)")),
    ("ends_at", _("Ende (YYYY-MM-DD HH:MM)")),
]

# Поле, по которому ищем существующую запись при обновлении.
MATCH_FIELD_CHOICES = [
    ("sku", _("SKU")),
    ("name_de", _("Name (DE)")),
]

RESOURCE_CHOICES = [
    ("product", _("Produkte")),
    ("product_variant", _("Produktvarianten")),
    ("promotion", _("Aktionen")),
]
RESOURCE_FIELDS = {
    "product": PRODUCT_FIELDS,
    "product_variant": VARIANT_FIELDS,
    "promotion": PROMOTION_FIELDS,
}
RESOURCE_MATCH_FIELDS = {
    "product": MATCH_FIELD_CHOICES,
    # Вариант всегда upsert по (товар, label) — поле синхронизации не выбирается.
    "product_variant": [("label", _("Variante (label)"))],
    "promotion": [("title_de", _("Titel (DE)"))],
}
RESOURCE_DEFAULT_MATCH = {"product": "sku", "product_variant": "label", "promotion": "title_de"}


@login_required
def import_start(request):
    form = ImportUploadForm()
    if request.method == "POST":
        form = ImportUploadForm(request.POST, request.FILES)
        if form.is_valid():
            resource_type = request.POST.get("resource_type", "product")
            if resource_type not in RESOURCE_FIELDS:
                resource_type = "product"
            job = ImportJob.objects.create(
                resource_type=resource_type,
                status="uploaded",
                source_file=form.cleaned_data["source_file"],
            )
            return redirect("imports:map", pk=job.pk)

    jobs = ImportJob.objects.all()[:20]
    return render(
        request,
        "imports/import_start.html",
        {"form": form, "jobs": jobs, "resources": RESOURCE_CHOICES, "nav": "imports"},
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
        default_match = RESOURCE_DEFAULT_MATCH.get(job.resource_type, "sku")
        job.options = {
            **(job.options or {}),
            "delimiter": delimiter,
            "update_existing": bool(request.POST.get("update_existing")),
            "match_field": request.POST.get("match_field") or default_match,
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
            "fields": RESOURCE_FIELDS.get(job.resource_type, PRODUCT_FIELDS),
            "delimiters": DELIMITER_CHOICES,
            "match_fields": RESOURCE_MATCH_FIELDS.get(job.resource_type, MATCH_FIELD_CHOICES),
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
