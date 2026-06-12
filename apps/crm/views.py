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


@login_required
def customer_list(request):
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
    page = paginate(customers, order_field="created_at", limit=25, cursor=request.GET.get("cursor"))
    return render(
        request,
        "crm/customer_list.html",
        {"nav": "crm", "page": page, "query": query},
    )


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
