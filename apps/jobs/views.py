"""Кабинет Aufträge/Angebote (G6 / F2): /dashboard/auftraege/.

Список заявок по статусу + ручная заявка; карточка — конструктор позиций сметы
(до 12 строк без JS), Angebot-PDF, действия по FSM (Angebot senden / beauftragt /
erledigt / Rechnung erstellen / ablehnen / stornieren). Гейтинг — модуль «jobs».
"""

from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core.fsm import IllegalTransition
from apps.finance.models import RevenueEntry

from . import services
from .models import Job
from .pdf import build_quote_pdf
from .state_machine import JobSM

MAX_LINES = 12


def _parse_date(raw):
    try:
        return date.fromisoformat(raw or "")
    except (TypeError, ValueError):
        return None


def _catalog_parts():
    """G11: активные товары/варианты для пикера расходников (value/label + остаток).

    value кодирует вид: ``p:<pk>`` товар без вариантов, ``v:<pk>`` вариант. Остаток
    в подписи — int (локаль-стабильно), только при учёте склада."""
    from apps.catalog.models import Product

    parts = []
    for p in Product.objects.filter(is_active=True).prefetch_related("variants"):
        variants = [v for v in p.variants.all() if v.is_active]
        if variants:
            for v in variants:
                label = f"{p.name_text} · {v.label}"
                if v.stock_quantity is not None:
                    label += f" (Lager: {v.stock_quantity})"
                parts.append({"value": f"v:{v.pk}", "label": label})
        else:
            label = p.name_text
            if p.stock_quantity is not None:
                label += f" (Lager: {p.stock_quantity})"
            parts.append({"value": f"p:{p.pk}", "label": label})
    return parts


def _resolve_part(raw, products, variants):
    """value пикера → (product, variant) инстансы или (None, None).

    pk — UUID-строка (каталог на UUID-PK), словари ключим по str(pk)."""
    kind, _, pk = (raw or "").partition(":")
    if not pk:
        return None, None
    if kind == "v":
        v = variants.get(pk)
        return (v.product if v else None), v
    if kind == "p":
        return products.get(pk), None
    return None, None


@login_required
def job_list(request):
    if request.method == "POST":  # ручная заявка (телефон/личный контакт)
        name = request.POST.get("name", "").strip()
        title = request.POST.get("title", "").strip()
        if not (name and title):
            messages.error(request, _("Please enter a name and a short title."))
            return redirect("jobs:list")
        job = services.create_job(
            title=title,
            name=name,
            email=request.POST.get("email", "").strip(),
            phone=request.POST.get("phone", "").strip(),
            description=request.POST.get("description", "").strip(),
            site_address=request.POST.get("site_address", "").strip(),
            source_channel="manual",
        )
        messages.success(request, _("Request created."))
        return redirect("jobs:detail", pk=job.pk)

    status = request.GET.get("status", "")
    jobs = Job.objects.select_related("customer")
    if status in dict(Job.STATUSES):
        jobs = jobs.filter(status=status)
    return render(
        request,
        "jobs/list.html",
        {
            "nav": "jobs",
            "jobs": jobs[:300],
            "statuses": Job.STATUSES,
            "active_status": status,
        },
    )


@login_required
def job_detail(request, pk):
    job = get_object_or_404(Job.objects.select_related("customer"), pk=pk)
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "save_lines":
            return _save_lines(request, job)
        if action == "invoice":
            return _make_invoice(request, job)
        if action in ("quoted", "accepted", "declined", "done", "cancelled"):
            return _transition(request, job, action)
        messages.error(request, _("Unknown action."))
        return redirect("jobs:detail", pk=job.pk)

    existing = list(job.lines.all())
    # Пред-заполненные строки конструктора (индекс + позиция или None) + текущая
    # привязка к расходнику (part_value) для пред-выбора в пикере (G11).
    rows = []
    for i in range(1, MAX_LINES + 1):
        line = existing[i - 1] if i <= len(existing) else None
        part_value = ""
        if line and line.variant_id:
            part_value = f"v:{line.variant_id}"
        elif line and line.product_id:
            part_value = f"p:{line.product_id}"
        rows.append({"i": i, "line": line, "part_value": part_value})
    return render(
        request,
        "jobs/detail.html",
        {
            "nav": "jobs",
            "job": job,
            "rows": rows,
            "parts": _catalog_parts(),  # G11: пикер расходников из каталога
            "vat_rates": RevenueEntry.VAT_RATES,
            "allowed": JobSM().allowed_targets(job.status),
            "small_business": request.tenant.small_business,
            "deposit_eur": f"{job.deposit_cents / 100:.2f}",
            "payments_enabled": getattr(request.tenant, "payments_enabled", False),
        },
    )


def _save_lines(request, job):
    from apps.catalog.models import Product, ProductVariant

    # Резолв привязок одним проходом (≤12 строк): str(pk) → инстанс (UUID-PK).
    products = {str(p.pk): p for p in Product.objects.filter(is_active=True)}
    variants = {
        str(v.pk): v
        for v in ProductVariant.objects.filter(is_active=True).select_related("product")
    }

    lines = []
    for index in range(1, MAX_LINES + 1):
        product, variant = _resolve_part(
            request.POST.get(f"line_part_{index}", ""), products, variants
        )
        text = request.POST.get(f"line_text_{index}", "").strip()
        # G11: расходник из каталога без текста → снимок названия товара/варианта.
        if product and not text:
            text = f"{product.name_text} · {variant.label}" if variant else product.name_text
        if not text:
            continue
        price_raw = str(request.POST.get(f"line_price_{index}", "")).strip()
        try:
            # A7a: дробное кол-во (часы/единицы). Ограничиваем 0,01..9999.
            qty_raw = str(request.POST.get(f"line_qty_{index}", "1") or "1").replace(",", ".")
            qty = min(max(Decimal(qty_raw), Decimal("0.01")), Decimal("9999")).quantize(
                Decimal("0.01")
            )
            # Цена пуста + выбран расходник → снимок цены товара/варианта.
            if product and not price_raw:
                unit_price = variant.price_value if variant else product.base_price
            else:
                unit_price = Decimal(price_raw.replace(",", ".") or "0")
        except (InvalidOperation, ValueError):
            messages.error(request, _("Invalid amount."))
            return redirect("jobs:detail", pk=job.pk)
        lines.append(
            {
                "text": text,
                "qty": qty,
                "unit_price": str(unit_price),
                "product": product,
                "variant": variant,
            }
        )

    vat_raw = request.POST.get("vat_rate", "19.00")
    vat_rate = next((r for r in RevenueEntry.VAT_RATES if str(r) == vat_raw), Decimal("19.00"))
    services.set_lines(job, lines, vat_rate=vat_rate, small_business=request.tenant.small_business)
    job.valid_until = _parse_date(request.POST.get("valid_until"))
    # A7c: Anzahlung (€ → cents). 0 / пусто = без депозита.
    try:
        job.deposit_cents = max(
            0,
            round(float(str(request.POST.get("deposit_eur", "0") or "0").replace(",", ".")) * 100),
        )
    except (TypeError, ValueError):
        job.deposit_cents = 0
    job.save(update_fields=["valid_until", "deposit_cents", "updated_at"])
    messages.success(request, _("Quote saved."))
    return redirect("jobs:detail", pk=job.pk)


def _transition(request, job, dst):
    try:
        JobSM().apply(job, dst, actor=request.user)
    except IllegalTransition:
        messages.error(request, _("This step is not possible in the current status."))
        return redirect("jobs:detail", pk=job.pk)
    now = timezone.now()
    if dst == "quoted" and job.quoted_at is None:
        job.quoted_at = now
        job.save(update_fields=["quoted_at", "updated_at"])
    elif dst == "accepted" and job.accepted_at is None:
        job.accepted_at = now
        job.save(update_fields=["accepted_at", "updated_at"])
    messages.success(request, _("Status updated."))
    return redirect("jobs:detail", pk=job.pk)


def _make_invoice(request, job):
    if job.status != Job.STATUS_DONE:
        messages.error(request, _("Finish the job before invoicing."))
        return redirect("jobs:detail", pk=job.pk)
    invoice = services.quote_to_invoice(job, small_business=request.tenant.small_business)
    JobSM().apply(job, Job.STATUS_INVOICED, actor=request.user)
    messages.success(request, _("Invoice draft created from the quote."))
    return redirect(f"{reverse('finance:invoice-detail', args=[invoice.pk])}")


@login_required
@require_POST
def job_delete(request, pk):
    """Удалить заявку (только пока new/declined/cancelled — без сметы в работе)."""
    job = get_object_or_404(Job, pk=pk)
    if job.status in (Job.STATUS_NEW, Job.STATUS_DECLINED, Job.STATUS_CANCELLED):
        job.delete()
        messages.success(request, _("Request deleted."))
        return redirect("jobs:list")
    messages.error(request, _("This request can no longer be deleted."))
    return redirect("jobs:detail", pk=job.pk)


@login_required
def job_pdf(request, pk):
    job = get_object_or_404(Job.objects.select_related("customer"), pk=pk)
    response = HttpResponse(build_quote_pdf(job, request.tenant), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="angebot_{job.reference_code}.pdf"'
    return response
