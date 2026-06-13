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
    # Пред-заполненные строки конструктора (индекс + позиция или None).
    rows = [
        {"i": i, "line": existing[i - 1] if i <= len(existing) else None}
        for i in range(1, MAX_LINES + 1)
    ]
    return render(
        request,
        "jobs/detail.html",
        {
            "nav": "jobs",
            "job": job,
            "rows": rows,
            "vat_rates": RevenueEntry.VAT_RATES,
            "allowed": JobSM().allowed_targets(job.status),
            "small_business": request.tenant.small_business,
        },
    )


def _save_lines(request, job):
    lines = []
    for index in range(1, MAX_LINES + 1):
        text = request.POST.get(f"line_text_{index}", "").strip()
        if not text:
            continue
        try:
            qty = max(1, min(int(request.POST.get(f"line_qty_{index}", "1") or 1), 9999))
            unit_price = Decimal(
                str(request.POST.get(f"line_price_{index}", "0")).replace(",", ".")
            )
        except (InvalidOperation, ValueError):
            messages.error(request, _("Invalid amount."))
            return redirect("jobs:detail", pk=job.pk)
        lines.append({"text": text, "qty": qty, "unit_price": str(unit_price)})

    vat_raw = request.POST.get("vat_rate", "19.00")
    vat_rate = next((r for r in RevenueEntry.VAT_RATES if str(r) == vat_raw), Decimal("19.00"))
    services.set_lines(job, lines, vat_rate=vat_rate, small_business=request.tenant.small_business)
    job.valid_until = _parse_date(request.POST.get("valid_until"))
    job.save(update_fields=["valid_until", "updated_at"])
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
