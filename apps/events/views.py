"""Кабинет событий (A6b): CRUD, ростер участников, действия FSM, CSV-экспорт."""

import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .forms import EventForm
from .models import Event, Ticket
from .services import book_ticket
from .state_machine import EventSM, TicketSM


@login_required
def event_list(request):
    events = Event.objects.all().order_by("-starts_at")
    return render(request, "events/event_list.html", {"events": events, "nav": "events"})


@login_required
def event_create(request):
    form = EventForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        event = form.save()
        messages.success(request, _("Event created."))
        return redirect("events:detail", pk=event.pk)
    return render(request, "events/event_form.html", {"form": form, "nav": "events"})


@login_required
def event_edit(request, pk):
    event = get_object_or_404(Event, pk=pk)
    form = EventForm(request.POST or None, instance=event)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Event saved."))
        return redirect("events:detail", pk=event.pk)
    return render(
        request, "events/event_form.html", {"form": form, "event": event, "nav": "events"}
    )


@login_required
def event_detail(request, pk):
    event = get_object_or_404(Event, pk=pk)
    tickets = event.tickets.select_related("customer").all()
    return render(
        request,
        "events/event_detail.html",
        {"event": event, "tickets": tickets, "nav": "events"},
    )


@login_required
@require_POST
def event_action(request, pk):
    """Публикация/снятие/отмена события (EventSM)."""
    event = get_object_or_404(Event, pk=pk)
    target = request.POST.get("target", "")
    try:
        EventSM().apply(event, target)
        messages.success(request, _("Event updated."))
    except Exception:  # noqa: BLE001 — недопустимый переход
        messages.error(request, _("Action not allowed."))
    return redirect("events:detail", pk=pk)


@login_required
@require_POST
def ticket_add(request, pk):
    """Ручная запись участника (без оплаты) — сразу подтверждён."""
    event = get_object_or_404(Event, pk=pk)
    name = (request.POST.get("name") or "").strip()
    if not name:
        messages.error(request, _("Name is required."))
        return redirect("events:detail", pk=pk)
    try:
        qty = max(1, int(request.POST.get("quantity", "1")))
    except (TypeError, ValueError):
        qty = 1
    from .services import EventNotBookable, SoldOut

    try:
        book_ticket(
            event,
            name=name,
            email=(request.POST.get("email") or "").strip(),
            phone=(request.POST.get("phone") or "").strip(),
            quantity=qty,
            auto_confirm=True,
        )
        messages.success(request, _("Attendee added."))
    except SoldOut:
        messages.error(request, _("Not enough seats left."))
    except EventNotBookable:
        messages.error(request, _("Publish the event first."))
    return redirect("events:detail", pk=pk)


@login_required
@require_POST
def ticket_action(request, pk, tid):
    """Действия по билету: confirm / attended / cancel (FSM) + mark paid."""
    ticket = get_object_or_404(Ticket, pk=tid, event_id=pk)
    target = request.POST.get("target", "")
    if target == "paid":
        ticket.payment_state = Ticket.PAYMENT_PAID
        ticket.save(update_fields=["payment_state", "updated_at"])
        if ticket.status == Ticket.STATUS_PENDING:
            TicketSM().apply(ticket, Ticket.STATUS_CONFIRMED)
        messages.success(request, _("Marked as paid."))
    else:
        try:
            TicketSM().apply(ticket, target)
            messages.success(request, _("Ticket updated."))
        except Exception:  # noqa: BLE001
            messages.error(request, _("Action not allowed."))
    return redirect("events:detail", pk=pk)


@login_required
def roster_csv(request, pk):
    """CSV-ростер участников события (utf-8-sig — Excel-friendly)."""
    event = get_object_or_404(Event, pk=pk)
    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = f'attachment; filename="roster-{event.pk}.csv"'
    writer = csv.writer(response, delimiter=";")
    question_cols = list(event.questions or [])
    writer.writerow(
        ["Code", "Name", "E-Mail", "Telefon", "Plätze", "Status", "Bezahlt", *question_cols]
    )
    for t in event.tickets.select_related("customer").all():
        answers = t.answers or {}
        writer.writerow(
            [
                t.reference_code,
                t.customer.name,
                t.customer.email,
                t.customer.phone,
                t.quantity,
                t.get_status_display(),
                t.get_payment_state_display(),
                *[answers.get(q, "") for q in question_cols],
            ]
        )
    return response
