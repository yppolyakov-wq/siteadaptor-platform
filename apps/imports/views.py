"""View'ы wizard'а импорта (все требуют логина).

Шаги: start (upload) → map → preview → status. Задачи ставятся в очередь
с передачей schema_name (connection.schema_name), т.к. Celery работает вне
tenant-контекста.
"""

import uuid
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _

from apps.ai.api import AI_LABEL
from apps.core.roles import is_owner

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
    ("label", _("Variante (leer = aus Größe/Farbe)")),
    ("size", _("Größe")),
    ("color", _("Farbe")),
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
            upload = form.cleaned_data["source_file"]
            # P0-2 (аудит 2026-09-03 §9.3): имя файла — не путь. Раньше загрузка
            # ложилась как imports/<исходное имя> и угадывалась с любого хоста.
            # Расширение сохраняем: по нему tabular.is_excel выбирает парсер.
            upload.name = f"{uuid.uuid4().hex}{Path(upload.name).suffix.lower()[:8]}"
            job = ImportJob.objects.create(
                resource_type=resource_type,
                status="uploaded",
                source_file=upload,
            )
            return redirect("imports:map", pk=job.pk)

    jobs = ImportJob.objects.all()[:20]
    return render(
        request,
        "imports/import_start.html",
        {
            "form": form,
            "jobs": jobs,
            "resources": RESOURCE_CHOICES,
            "nav": "imports",
            # T-8.27: вход в импорт с сайта — только владельцу (owner-only зона).
            "is_owner": is_owner(request.user),
        },
    )


@login_required
def import_map(request, pk):
    job = get_object_or_404(ImportJob, pk=pk)
    # P0-2: после completed файл удалён (и `cleanup_import_files` чистит
    # брошенные) — шаг маппинга без файла падал бы на read_headers. Честно
    # отправляем на статус: строки уже в job.rows, а новый импорт = новая загрузка.
    if not job.source_file:
        messages.info(
            request, _("Die Importdatei wurde bereits entfernt. Bitte laden Sie sie erneut hoch.")
        )
        return redirect("imports:status", pk=job.pk)

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


# --- T-8.27 «Импорт с сайта клиента» -----------------------------------------------------


@login_required
def website_start(request):
    """Старт: адрес сайта + согласие правообладателя → прогон в Celery."""
    from .models import SiteImportRun
    from .site import service

    tenant = request.tenant
    error = ""
    url = request.POST.get("url", "") if request.method == "POST" else tenant.website_url
    if request.method == "POST":
        if request.POST.get("consent") != "1":
            error = _("Bitte bestätigen Sie, dass Sie Inhaber der Website sind.")
        else:
            try:
                run = service.start_run(user=request.user, url=url)
            except service.StartError as exc:
                error = str(exc)
            else:
                if not tenant.website_url:
                    tenant.website_url = run.start_url
                    tenant.save(update_fields=["website_url"])
                return redirect("imports:website-run", pk=run.pk)
    return render(
        request,
        "imports/website_start.html",
        {"url": url, "error": error, "runs": SiteImportRun.objects.all()[:10]},
    )


PROFILE_LABELS = {
    "phone": _("Telefon"),
    "address": _("Adresse"),
    "opening_hours_structured": _("Öffnungszeiten"),
    "description": _("Beschreibung"),
}
_PROFILE_TENANT_ATTR = {
    "phone": "contact_phone",
    "address": "address",
    "opening_hours_structured": "opening_hours_structured",
}


def _profile_rows(run, tenant):
    rows = []
    for key, label in PROFILE_LABELS.items():
        value = (run.profile or {}).get(key)
        if not value:
            continue
        if key == "description":
            current = (tenant.site_config or {}).get("about_text", "")
        else:
            current = getattr(tenant, _PROFILE_TENANT_ATTR[key], "")
        if key == "opening_hours_structured":
            value = ", ".join(f"{d}: {v[0]}–{v[1]}" for d, v in sorted(value.items()))
        rows.append({"key": key, "label": label, "value": value, "filled": bool(current)})
    return rows


@login_required
def website_run(request, pk):
    """Статус прогона → «Prüfen & veröffentlichen»: выбор, правка, применение."""
    from apps.catalog.models import Category

    from .models import SiteImportRun
    from .site import apply

    run = get_object_or_404(SiteImportRun, pk=pk)
    tenant = request.tenant
    items = list(run.items.all())
    if request.method == "POST" and run.status == SiteImportRun.STATUS_READY:
        decisions = {
            str(item.pk): {
                "name": request.POST.get(f"name_{item.pk}", ""),
                "price": request.POST.get(f"price_{item.pk}", ""),
                "description": request.POST.get(f"desc_{item.pk}", ""),
                "category": request.POST.get(f"category_{item.pk}", ""),
            }
            for item in items
            if request.POST.get(f"take_{item.pk}") == "1"
        }
        fields = [k for k in PROFILE_LABELS if request.POST.get(f"profile_{k}") == "1"]
        result = apply.apply_items(run, tenant, decisions)
        apply.apply_profile(run, tenant, fields)
        messages.success(
            request,
            _("%(created)s neu, %(updated)s aktualisiert. Fotos werden im Hintergrund geladen.")
            % {"created": result.created, "updated": result.updated},
        )
        if result.over_limit:
            messages.warning(request, apply_limit_message(result.over_limit))
        return redirect("imports:website-run", pk=run.pk)
    return render(
        request,
        "imports/website_run.html",
        {
            "run": run,
            "items": items,
            "active": run.status in SiteImportRun.ACTIVE,
            "profile": run.profile or {},
            "profile_rows": _profile_rows(run, tenant),
            "categories": Category.objects.filter(is_active=True).order_by("sort_order"),
            "usage": apply.usage(tenant),
            "contact_email": _contact_email(),
            "ai_label": AI_LABEL,
        },
    )


def _contact_email() -> str:
    from apps.promotions.limits import contact_email

    return contact_email()


def apply_limit_message(count: int) -> str:
    return _(
        "%(n)s Artikel wurden nicht übernommen: Der kostenlose Import umfasst bis zu "
        "%(limit)s Artikel. Mehr? Schreiben Sie uns: %(contact)s"
    ) % {"n": count, "limit": settings.IMPORT_FREE_ITEMS, "contact": _contact_email()}
