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

    _owner_only(request)
    from .site import verify

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
                # website_url ставится только после подтверждения владения (service).
                return redirect("imports:website-run", pk=run.pk)
    return render(
        request,
        "imports/website_start.html",
        {
            "url": url,
            "error": error,
            "runs": SiteImportRun.objects.all()[:10],
            "verify_meta": verify.meta_tag(),
            "verify_token": verify.token(),
            "verify_file": verify.FILE_PATH,
            "verified_host": verify.verified_host(),
        },
    )


def _owner_only(request) -> None:
    """Импорт с сайта — только владельцу (защита в глубину поверх middleware)."""
    from django.core.exceptions import PermissionDenied

    if not is_owner(request.user):
        raise PermissionDenied


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
    from .site import apply, verify

    _owner_only(request)
    run = get_object_or_404(SiteImportRun, pk=pk)
    tenant = request.tenant
    items = list(run.items.all())
    action = request.POST.get("action") if request.method == "POST" else None
    if action == "verify":
        if verify.ensure(run):
            from .site.service import _adopt_website

            _adopt_website(run)
            messages.success(request, _("Website bestätigt."))
        else:
            messages.error(
                request,
                _("Der Bestätigungscode wurde auf Ihrer Website nicht gefunden."),
            )
        return redirect("imports:website-run", pk=run.pk)
    if action == "eintrag":
        # T-8.27d (Р-A): визитка — витрина без каталога, позиции ведут на сайт владельца.
        if not _can_eintrag(tenant, run):
            messages.error(request, _("Die Visitenkarte ist für diesen Import nicht möglich."))
            return redirect("imports:website-run", pk=run.pk)
        _enable_eintrag(tenant)
        messages.success(
            request, _("Visitenkarte aktiviert: Ihre Artikel verlinken auf Ihre Website.")
        )
        return redirect("imports:website-run", pk=run.pk)
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
        try:
            result = apply.apply_items(run, tenant, decisions)
        except apply.ApplyError as exc:
            messages.error(request, APPLY_ERRORS.get(str(exc), APPLY_ERRORS["not_ready"]))
            return redirect("imports:website-run", pk=run.pk)
        apply.apply_profile(run, tenant, fields)
        messages.success(
            request,
            _("%(created)s neu, %(updated)s aktualisiert. Fotos werden im Hintergrund geladen.")
            % {"created": result.created, "updated": result.updated},
        )
        if result.over_limit:
            messages.warning(request, apply_limit_message(result.over_limit))
        if result.errors:
            messages.error(
                request,
                _("Nicht gespeichert: %(names)s. Bitte prüfen und erneut versuchen.")
                % {"names": ", ".join(result.errors[:10])},
            )
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
            "can_eintrag": _can_eintrag(tenant, run),
            "verified": verify.is_verified(run),
            "verify_meta": verify.meta_tag(),
            "verify_file": verify.FILE_PATH,
            "verify_token": verify.token(),
        },
    )


APPLY_ERRORS = {
    "not_ready": _("Dieser Import wurde bereits übernommen oder ist nicht mehr aktuell."),
    "stale": _("Es gibt einen neueren Import. Bitte übernehmen Sie den neuesten."),
    "unverified": _("Bitte bestätigen Sie zuerst, dass die Website Ihnen gehört."),
}


def _can_eintrag(tenant, run) -> bool:
    """Предложить визитку: импорт применён, сайт подтверждён, сайт бизнеса — https на
    подтверждённом хосте, профиль ещё не лёгкий. Проверяется и на POST (сервер)."""
    from apps.core import storefront_profile

    from .site.crawl import same_site
    from .site.verify import verified_host

    website = tenant.website_url or ""
    own = verified_host()
    return (
        run.status == run.STATUS_APPLIED
        and bool(own)
        and website.startswith("https://")
        and same_site(website, own)
        and not storefront_profile.is_aktionen(tenant)
    )


def _enable_eintrag(tenant) -> None:
    """Профиль «eintrag» — точечной записью свежего конфига, затем пересинхронизация
    каталога города: листинги сразу ведут на сайт владельца (не ждут ночной сверки)."""
    from django.db import connection, transaction

    from apps.aggregator.tasks import reconcile_city_catalog
    from apps.core import storefront_profile
    from apps.tenants.models import Tenant

    fresh = (Tenant.objects.filter(pk=tenant.pk).first() if tenant.pk else None) or tenant
    config = dict(fresh.site_config or {})
    config["profile"] = storefront_profile.EINTRAG
    fresh.site_config = config
    fresh.save(update_fields=["site_config"])
    tenant.site_config = config
    schema = connection.schema_name
    transaction.on_commit(
        lambda: reconcile_city_catalog.delay(
            dedupe_key=f"city-reconcile:{schema}:eintrag", tenant_schema=schema
        )
    )


def _contact_email() -> str:
    from apps.promotions.limits import contact_email

    return contact_email()


def apply_limit_message(count: int) -> str:
    return _(
        "%(n)s Artikel wurden nicht übernommen: Der kostenlose Import umfasst bis zu "
        "%(limit)s Artikel. Mehr? Schreiben Sie uns: %(contact)s"
    ) % {"n": count, "limit": settings.IMPORT_FREE_ITEMS, "contact": _contact_email()}
