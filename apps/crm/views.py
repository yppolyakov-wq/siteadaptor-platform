"""Кабинет «Клиенты» (Track C3): список с поиском, карточка, заметки.

История броней в карточке — readonly-справка (бронь живёт в promotions);
сам клиент — самостоятельная сущность, заводится и без брони.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core.csv_safe import csv_safe
from apps.core.pagination import paginate
from apps.promotions.models import Customer

from . import customer360
from .forms import CustomerForm, NoteForm
from .models import CustomerNote


def _filtered_customers(request):
    """Клиенты по поисковому запросу ?q= — общий фильтр списка и CSV-экспорта."""
    customers = Customer.objects.all()
    query = request.GET.get("q", "").strip()
    if query:
        customers = customers.filter(
            Q(name__icontains=query)
            | Q(email__icontains=query)
            | Q(phone__icontains=query)
            # тег — точным совпадением (JSONB containment; теги хранятся lower)
            | Q(tags__contains=[query.lower()])
        )
    return customers, query


@login_required
def customer_list(request):
    customers, query = _filtered_customers(request)
    page = paginate(customers, order_field="created_at", limit=25, cursor=request.GET.get("cursor"))
    return render(
        request,
        "crm/customer_list.html",
        {"nav": "crm", "page": page, "query": query},
    )


@login_required
def customer_export_csv(request):
    """CSV-экспорт списка клиентов по текущему фильтру (D1c).

    Персональные данные — файл для владельца (Verantwortlicher по DSGVO);
    индивидуальные запросы клиентов — командой dsgvo_customer.
    """
    import csv

    from django.http import HttpResponse

    customers, _query = _filtered_customers(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="kunden.csv"'
    writer = csv.writer(response)
    writer.writerow(
        ["name", "email", "phone", "tags", "marketing_opt_in", "created_source", "created_at"]
    )
    for c in customers.order_by("-created_at").iterator():
        writer.writerow(
            [
                csv_safe(c.name),
                csv_safe(c.email),
                csv_safe(c.phone),
                csv_safe(", ".join(c.tags or [])),
                "yes" if c.marketing_opt_in else "no",
                c.created_source,
                c.created_at.date().isoformat(),
            ]
        )
    return response


@login_required
def customer_create(request):
    form = CustomerForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        customer = form.save(commit=False)
        customer.created_source = Customer.SOURCE_MANUAL  # D1: источник записи
        customer.save()
        messages.success(request, _("Customer created."))
        return redirect("crm:customer-detail", pk=customer.pk)
    return render(request, "crm/customer_form.html", {"nav": "crm", "form": form})


@login_required
def customer_detail(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    # D1: выдать ваучер этому клиенту (отдельное действие — не сохранение формы).
    if request.method == "POST" and request.POST.get("action") == "issue_voucher":
        return _issue_voucher(request, customer)
    form = CustomerForm(request.POST or None, instance=customer)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Saved."))
        return redirect("crm:customer-detail", pk=customer.pk)
    reservations = customer.reservations.select_related("promotion").order_by("-created_at")[:20]
    return render(
        request,
        "crm/customer_detail.html",
        {
            "nav": "crm",
            "customer": customer,
            "form": form,
            "note_form": NoteForm(),
            "notes": customer.crm_notes.all()[:50],
            "reservations": reservations,
            # 360° (D1b): карты лояльности — readonly-справка.
            "loyalty_cards": customer.loyalty_cards.select_related("program"),
            # 360° (D2b): заказы Click & Collect.
            "orders": customer.orders.prefetch_related("items").order_by("-created_at")[:20],
            # 360° (D1): ваучеры, выданные клиенту.
            "vouchers": customer.vouchers.all()[:50],
            # CM-8: KPI-шапка (LTV из RevenueEntry) + недостающие разделы 360°
            # (termine/passes/stays/tickets/jobs/invoices/переписка/отзывы).
            "kpi": customer360.kpis(getattr(request, "tenant", None), customer),
            "sections360": customer360.sections(getattr(request, "tenant", None), customer),
        },
    )


def _issue_voucher(request, customer):
    from apps.promotions.services import generate_vouchers

    label = request.POST.get("label", "").strip()
    if label:
        try:
            max_uses = max(1, min(int(request.POST.get("max_uses", "1") or 1), 999))
        except (TypeError, ValueError):
            max_uses = 1
        generate_vouchers(label=label[:120], count=1, max_uses=max_uses, customer=customer)
        messages.success(request, _("Voucher issued."))
    else:
        messages.error(request, _("Please describe what the voucher gives."))
    return redirect("crm:customer-detail", pk=customer.pk)


@login_required
@require_POST
def note_add(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    form = NoteForm(request.POST)
    if form.is_valid():
        CustomerNote.objects.create(customer=customer, text=form.cleaned_data["text"])
        messages.success(request, _("Note added."))
    return redirect("crm:customer-detail", pk=customer.pk)
