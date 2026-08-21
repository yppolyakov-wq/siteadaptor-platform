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

    von, bis, entries = _period_entries(request)
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
            "today": timezone.localdate(),
        },
    )


def _period_expenses(request):
    """MX-1: (von, bis, queryset) расходов по ?von=&bis= — зеркало _period_entries."""
    from .expenses import ExpenseEntry

    today = timezone.localdate()
    von = _parse_date(request.GET.get("von"), today.replace(day=1))
    bis = _parse_date(request.GET.get("bis"), today)
    qs = ExpenseEntry.objects.filter(date__gte=von, date__lte=bis)
    category = request.GET.get("kategorie", "")
    if category in dict(ExpenseEntry.CATEGORIES):
        qs = qs.filter(category=category)
    return von, bis, qs


@login_required
def expenses(request):
    """MX-1: экран «Ausgaben» — до него расходы существовали только в коде
    (писала одна ветка тур-логистики, читал один экран заезда; ручного ввода
    не было вовсе). Ручная запись + список с фильтрами; удаление — ТОЛЬКО
    manual-строк (событийные записи держит идемпотентность источника)."""
    from .expenses import ExpenseEntry

    if request.method == "POST":
        if request.POST.get("action") == "delete":
            ExpenseEntry.objects.filter(
                pk=request.POST.get("id"), source=ExpenseEntry.SOURCE_MANUAL
            ).delete()
            messages.success(request, _("Entry deleted."))
            return redirect("finance:expenses")
        try:
            amount = Decimal(str(request.POST.get("amount", "")).replace(",", "."))
        except (InvalidOperation, ValueError):
            messages.error(request, _("Invalid amount."))
            return redirect("finance:expenses")
        if amount <= 0:
            messages.error(request, _("Amount must be positive."))
            return redirect("finance:expenses")
        category = request.POST.get("category", "")
        if category not in dict(ExpenseEntry.CATEGORIES):
            category = ExpenseEntry.CATEGORY_OTHER
        ExpenseEntry.objects.create(
            source=ExpenseEntry.SOURCE_MANUAL,
            amount=amount,
            category=category,
            date=_parse_date(request.POST.get("date"), timezone.localdate()),
            note=request.POST.get("note", "").strip()[:200],
        )
        messages.success(request, _("Entry added."))
        return redirect("finance:expenses")

    von, bis, qs = _period_expenses(request)
    by_cat = qs.values("category").annotate(sum=Sum("amount")).order_by("-sum")
    cat_labels = dict(ExpenseEntry.CATEGORIES)
    return render(
        request,
        "finance/expenses.html",
        {
            "nav": "finance",
            "von": von,
            "bis": bis,
            "entries": qs.select_related("event")[:500],
            "total": qs.aggregate(s=Sum("amount"))["s"] or Decimal("0"),
            "by_cat": [
                {"label": cat_labels.get(r["category"], r["category"]), "sum": r["sum"]}
                for r in by_cat
            ],
            "categories": ExpenseEntry.CATEGORIES,
            "active_category": request.GET.get("kategorie", ""),
            "today": timezone.localdate(),
        },
    )


def _order_cogs(entries):
    """ERP-1: Wareneinsatz по заказам, чья ВЫРУЧКА записана в период (момент =
    RevenueEntry.date, тот же, что в строке Einnahmen). Снимок EK — из позиции
    (легаси-позиции без снимка честно считаются нулём и подсвечиваются)."""
    from apps.orders.models import OrderItem

    order_ids = [r.source_ref for r in entries if r.source == "order" and r.source_ref]
    if not order_ids:
        return Decimal("0"), False
    cogs = Decimal("0")
    missing = False
    for item in OrderItem.objects.filter(order_id__in=order_ids).only(
        "qty", "cost_price", "product_id", "combo_id"
    ):
        if item.cost_price is not None:
            cogs += item.cost_price * item.qty
        elif item.product_id is not None or item.combo_id is not None:
            missing = True  # товарная позиция без EK-снимка (легаси/без закупа)
    return cogs, missing


@login_required
def ergebnis(request):
    """MX-1: «Ergebnis» — выручка − расходы за период (первый сводный P&L-срез).
    ERP-1: + Wareneinsatz (COGS по снимкам EK) и Rohertrag."""
    von, bis, entries = _period_entries(request)
    _von, _bis, expense_qs = _period_expenses(request)
    entries = list(entries)
    revenue = sum((e.amount for e in entries), Decimal("0"))
    spent = expense_qs.aggregate(s=Sum("amount"))["s"] or Decimal("0")
    cogs, cogs_partial = _order_cogs(entries)
    return render(
        request,
        "finance/ergebnis.html",
        {
            "nav": "finance",
            "von": von,
            "bis": bis,
            "revenue": revenue,
            "spent": spent,
            "result": revenue - spent,
            "cogs": cogs,
            "cogs_partial": cogs_partial,
            "rohertrag": revenue - cogs,
        },
    )


def _period_entries(request):
    """(von, bis, queryset) по ?von=&bis= — общий фильтр журнала и экспортов."""
    today = timezone.localdate()
    von = _parse_date(request.GET.get("von"), today.replace(day=1))
    bis = _parse_date(request.GET.get("bis"), today)
    entries = RevenueEntry.objects.filter(date__gte=von, date__lte=bis).select_related("customer")
    return von, bis, entries


@login_required
def journal_export_csv(request):
    """Обычный CSV за период (D4c); utf-8-sig — чтобы Excel понял умляуты."""
    from django.http import HttpResponse

    from .exports import plain_csv

    von, bis, entries = _period_entries(request)
    response = HttpResponse(
        plain_csv(entries.order_by("date")).encode("utf-8-sig"),
        content_type="text/csv; charset=utf-8",
    )
    response["Content-Disposition"] = f'attachment; filename="umsatz_{von}_{bis}.csv"'
    return response


@login_required
def journal_export_datev(request):
    """DATEV-CSV за период (D4c): упрощённый Buchungsstapel, cp1252."""
    from django.http import HttpResponse

    from .exports import datev_csv

    von, bis, entries = _period_entries(request)
    response = HttpResponse(
        datev_csv(entries.order_by("date")).encode("cp1252", errors="replace"),
        content_type="text/csv; charset=windows-1252",
    )
    response["Content-Disposition"] = f'attachment; filename="datev_{von}_{bis}.csv"'
    return response


@login_required
def invoices(request):
    """Счета (D4b): список + создание черновика (до 8 позиций без JS)."""
    from decimal import Decimal, InvalidOperation

    from apps.core.documents import business_language, language_choices
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
        customer = (
            Customer.objects.select_related("company")
            .filter(pk=request.POST.get("customer") or None)
            .first()
        )
        # CO-2: корпоративный гость без явного получателя → реквизиты компании
        # (name + адрес + USt-IdNr), а не свободный текст/имя клиента.
        company_recipient = (
            customer.company.invoice_recipient if customer and customer.company_id else ""
        )
        from apps.core.documents import business_language, clean_language

        invoice = Invoice.objects.create(
            customer=customer,
            # I18N-7b/2: язык документа выбирает владелец при создании (дефолт —
            # язык бизнеса); дальше он живёт со счётом и не зависит от того, кто
            # и на каком языке кабинета нажал «скачать».
            language=clean_language(request.POST.get("language"), request.tenant)
            or business_language(request.tenant),
            recipient=request.POST.get("recipient", "").strip()[:500]
            or company_recipient
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
            "doc_languages": language_choices(request.tenant),
            "doc_language_default": business_language(request.tenant),
        },
    )


@login_required
def invoice_detail(request, pk):
    from django.shortcuts import get_object_or_404

    from apps.core.documents import language_choices

    from .models import Invoice
    from .state_machine import InvoiceSM

    invoice = get_object_or_404(Invoice, pk=pk)
    if request.method == "POST":
        from apps.core.fsm import IllegalTransition

        from .services import issue_invoice

        action = request.POST.get("action", "")
        try:
            if action == "language" and invoice.is_editable:
                # Менять язык можно только у ЧЕРНОВИКА: выставленный счёт
                # неизменяем (GoBD) — иначе один номер дал бы два документа.
                from apps.core.documents import clean_language

                invoice.language = clean_language(request.POST.get("language"), request.tenant)
                invoice.save(update_fields=["language", "updated_at"])
                messages.success(request, _("Document language saved."))
            elif action == "issue" and invoice.is_editable:
                # Язык фиксируется в момент выставления (если владелец его не
                # выбрал — язык бизнеса), дальше документ неизменяем.
                if not invoice.language:
                    from apps.core.documents import business_language

                    invoice.language = business_language(request.tenant)
                    invoice.save(update_fields=["language", "updated_at"])
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
            "doc_languages": language_choices(request.tenant),
        },
    )


@login_required
def invoice_pdf(request, pk):
    from django.http import HttpResponse
    from django.shortcuts import get_object_or_404
    from django.utils import translation

    from apps.core.documents import document_language

    from .models import Invoice
    from .pdf import build_invoice_pdf

    invoice = get_object_or_404(Invoice, pk=pk)
    # I18N-7b/2: язык зафиксирован на счёте (GoBD: один номер — один документ); `?lang=`
    # остаётся только для черновика-предпросмотра.
    explicit = invoice.language if not invoice.is_editable else ""
    with translation.override(document_language(request, explicit=explicit)):
        pdf = build_invoice_pdf(invoice, request.tenant)
    response = HttpResponse(pdf, content_type="application/pdf")
    name = invoice.number_display if invoice.number else f"entwurf-{invoice.pk}"
    response["Content-Disposition"] = f'inline; filename="{name}.pdf"'
    return response
