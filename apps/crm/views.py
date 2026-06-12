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

from apps.core.pagination import paginate
from apps.promotions.models import Customer

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
                c.name,
                c.email,
                c.phone,
                ", ".join(c.tags or []),
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
        },
    )


@login_required
@require_POST
def note_add(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    form = NoteForm(request.POST)
    if form.is_valid():
        CustomerNote.objects.create(customer=customer, text=form.cleaned_data["text"])
        messages.success(request, _("Note added."))
    return redirect("crm:customer-detail", pk=customer.pk)
