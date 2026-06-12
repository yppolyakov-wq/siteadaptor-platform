"""Кабинет Light-Finance (Track D / D4a): /dashboard/finance/ — журнал выручки.

Период (?von=&bis=, по умолчанию текущий месяц), итоги по сумме и по ставкам
НДС, ручное добавление записи. Автозаписи приходят из хуков OrderSM/ReservationSM
(см. apps.finance.services). Гейтинг — модуль «finance» из реестра.
"""

from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import RevenueEntry
from .services import record_revenue


def _parse_date(raw, fallback):
    try:
        return date.fromisoformat(raw or "")
    except ValueError:
        return fallback


@login_required
def journal(request):
    if request.method == "POST":
        try:
            amount = Decimal(str(request.POST.get("amount", "")).replace(",", "."))
        except (InvalidOperation, ValueError):
            messages.error(request, _("Invalid amount."))
            return redirect("finance:journal")
        vat_raw = request.POST.get("vat_rate", "19.00")
        vat_rate = next(
            (rate for rate in RevenueEntry.VAT_RATES if str(rate) == vat_raw),
            Decimal("19.00"),
        )
        entry = record_revenue(
            source=RevenueEntry.SOURCE_MANUAL,
            amount=amount,
            vat_rate=vat_rate,
            date=_parse_date(request.POST.get("date"), timezone.localdate()),
            note=request.POST.get("note", "").strip(),
        )
        if entry is None:
            messages.error(request, _("Amount must be positive."))
        else:
            messages.success(request, _("Entry added."))
        return redirect("finance:journal")

    today = timezone.localdate()
    von = _parse_date(request.GET.get("von"), today.replace(day=1))
    bis = _parse_date(request.GET.get("bis"), today)
    entries = RevenueEntry.objects.filter(date__gte=von, date__lte=bis).select_related("customer")
    by_vat = entries.values("vat_rate").annotate(sum=Sum("amount")).order_by("-vat_rate")
    return render(
        request,
        "finance/journal.html",
        {
            "nav": "finance",
            "von": von,
            "bis": bis,
            "entries": entries[:500],
            "total": entries.aggregate(s=Sum("amount"))["s"] or Decimal("0"),
            "by_vat": by_vat,
            "vat_rates": RevenueEntry.VAT_RATES,
            "today": today,
        },
    )


@login_required
def invoices(request):
    """Счета (D4b): список + создание черновика (до 8 позиций без JS)."""
    from decimal import Decimal, InvalidOperation

    from apps.promotions.models import Customer

    from .models import Invoice
    from .services import compute_totals

    if request.method == "POST":
        lines = []
        for index in range(1, 9):
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
                return redirect("finance:invoices")
            lines.append({"text": text[:200], "qty": qty, "unit_price": str(unit_price)})
        if not lines:
            messages.error(request, _("Add at least one line."))
            return redirect("finance:invoices")

        vat_raw = request.POST.get("vat_rate", "19.00")
        vat_rate = next(
            (rate for rate in RevenueEntry.VAT_RATES if str(rate) == vat_raw), Decimal("19.00")
        )
        small = request.tenant.small_business
        net, vat, gross = compute_totals(lines, vat_rate, small_business=small)
        customer = Customer.objects.filter(pk=request.POST.get("customer") or None).first()
        invoice = Invoice.objects.create(
            customer=customer,
            recipient=request.POST.get("recipient", "").strip()[:500]
            or (str(customer) if customer else ""),
            lines=lines,
            vat_rate=Decimal("0") if small else vat_rate,
            net=net,
            vat_amount=vat,
            gross=gross,
            note=request.POST.get("note", "").strip()[:200],
        )
        messages.success(request, _("Draft created."))
        return redirect("finance:invoice-detail", pk=invoice.pk)

    return render(
        request,
        "finance/invoices.html",
        {
            "nav": "finance",
            "invoices": Invoice.objects.all()[:200],
            "customers": Customer.objects.order_by("name")[:200],
            "vat_rates": RevenueEntry.VAT_RATES,
            "small_business": request.tenant.small_business,
        },
    )


@login_required
def invoice_detail(request, pk):
    from django.shortcuts import get_object_or_404

    from .models import Invoice
    from .state_machine import InvoiceSM

    invoice = get_object_or_404(Invoice, pk=pk)
    if request.method == "POST":
        from apps.core.fsm import IllegalTransition

        from .services import issue_invoice

        action = request.POST.get("action", "")
        try:
            if action == "issue" and invoice.is_editable:
                invoice = issue_invoice(invoice)
                messages.success(request, _("Invoice issued."))
            elif action == "delete" and invoice.is_editable:
                invoice.delete()  # черновик без номера — дыры в нумерации нет
                messages.success(request, _("Draft deleted."))
                return redirect("finance:invoices")
            elif action in ("paid", "cancelled"):
                InvoiceSM().apply(invoice, action, actor=request.user)
                messages.success(request, _("Invoice updated."))
            else:
                messages.error(request, _("This step is not possible in the current status."))
        except IllegalTransition:
            messages.error(request, _("This step is not possible in the current status."))
        return redirect("finance:invoice-detail", pk=invoice.pk)

    return render(
        request,
        "finance/invoice_detail.html",
        {
            "nav": "finance",
            "invoice": invoice,
            "allowed": InvoiceSM().allowed_targets(invoice.status),
        },
    )


@login_required
def invoice_pdf(request, pk):
    from django.http import HttpResponse
    from django.shortcuts import get_object_or_404

    from .models import Invoice
    from .pdf import build_invoice_pdf

    invoice = get_object_or_404(Invoice, pk=pk)
    response = HttpResponse(
        build_invoice_pdf(invoice, request.tenant), content_type="application/pdf"
    )
    name = invoice.number_display if invoice.number else f"entwurf-{invoice.pk}"
    response["Content-Disposition"] = f'inline; filename="{name}.pdf"'
    return response
