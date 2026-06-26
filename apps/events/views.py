"""Кабинет событий (A6b): CRUD, ростер участников, действия FSM, CSV-экспорт."""

import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from . import registration
from .forms import EventForm, TeacherForm
from .models import Event, Teacher, Ticket
from .services import book_ticket, notify_event_waitlist
from .state_machine import EventSM, TicketSM


def _add_event_photos(event, uploaded) -> None:
    """Сохранить загруженные фото места/мероприятия (до 12). Первое — обложка,
    если фото ещё нет. Переиспускаем catalog.images (Pillow + storage)."""
    from apps.catalog.images import save_product_image

    if not uploaded:
        return
    images = list(event.images or [])
    for f in uploaded[:12]:
        try:
            ref = save_product_image(
                f, is_primary=not images, sort_order=len(images), folder="events"
            )
        except Exception:
            continue
        images.append(ref)
    if images != list(event.images or []):
        event.images = images[:24]
        event.save(update_fields=["images"])


def _delete_event_photo(event, ref_id) -> None:
    from apps.catalog.images import delete_stored_image

    keep = [i for i in event.images if str(i.get("id")) != str(ref_id)]
    for i in event.images:
        if str(i.get("id")) == str(ref_id):
            delete_stored_image(i)
    if keep and not any(i.get("is_primary") for i in keep):
        keep[0]["is_primary"] = True
    event.images = keep
    event.save(update_fields=["images"])


@login_required
def event_list(request):
    events = Event.objects.all().order_by("-starts_at")
    return render(request, "events/event_list.html", {"events": events, "nav": "events"})


@login_required
def event_create(request):
    form = EventForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        event = form.save()
        _add_event_photos(event, request.FILES.getlist("photos"))
        messages.success(request, _("Event created."))
        return redirect("events:detail", pk=event.pk)
    return render(request, "events/event_form.html", {"form": form, "nav": "events"})


@login_required
def event_edit(request, pk):
    event = get_object_or_404(Event, pk=pk)
    form = EventForm(request.POST or None, instance=event)
    if request.method == "POST" and form.is_valid():
        form.save()
        _add_event_photos(event, request.FILES.getlist("photos"))
        if request.POST.get("delete_image"):
            _delete_event_photo(event, request.POST["delete_image"])
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
        {
            "event": event,
            "tickets": tickets,
            "waitlist": event.waitlist.all(),
            "nav": "events",
        },
    )


@login_required
@require_POST
def waitlist_notify(request, pk):
    """Разослать письма «снова frei» листу ожидания (если есть места)."""
    event = get_object_or_404(Event, pk=pk)
    sent = notify_event_waitlist(event)
    if sent:
        messages.success(request, _("Notified %(n)s people from the waitlist.") % {"n": sent})
    else:
        messages.info(request, _("No one to notify (no free spots or empty waitlist)."))
    return redirect("events:detail", pk=pk)


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
            if target == Ticket.STATUS_CANCELLED:
                # R5: освободить привязанный номер (проживание оплачивалось билетом).
                _cancel_linked_stay(ticket)
                # Отмена освободила место → уведомить лист ожидания (R1).
                notify_event_waitlist(ticket.event)
        except Exception:  # noqa: BLE001
            messages.error(request, _("Action not allowed."))
    return redirect("events:detail", pk=pk)


@login_required
@require_POST
def event_series(request, pk):
    """RT3: создать recurring-серию — N повторов события с шагом интервала."""
    from . import services

    event = get_object_or_404(Event, pk=pk)
    interval = request.POST.get("interval", "weekly")
    try:
        count = int(request.POST.get("count", "0"))
    except (TypeError, ValueError):
        count = 0
    if count < 1:
        messages.error(request, _("Please choose how many occurrences to create."))
        return redirect("events:detail", pk=pk)
    created = services.create_series(event, interval=interval, count=count)
    messages.success(
        request,
        _("Created %(n)d more dates in this series.") % {"n": len(created)},
    )
    return redirect("events:detail", pk=pk)


@login_required
def checkin(request, code):
    """RT1: Check-in билета по QR (организатор в кабинете). GET — карточка гостя и
    кнопка «Einchecken»; POST — отметить пришедшим (status→attended + checked_in_at).
    Сканирует логин-сессия владельца; чужой без логина уходит на login (защита)."""
    from django.utils import timezone

    ticket = get_object_or_404(
        Ticket.objects.select_related("event", "customer"),
        reference_code=code.strip().upper(),
    )
    if request.method == "POST":
        if ticket.status == Ticket.STATUS_CANCELLED:
            messages.error(request, _("This ticket is cancelled."))
        elif ticket.checked_in_at:
            messages.info(request, _("Already checked in."))
        else:
            if ticket.status != Ticket.STATUS_ATTENDED:
                try:
                    TicketSM().apply(ticket, Ticket.STATUS_ATTENDED)
                except Exception:  # noqa: BLE001 — из pending/cancelled переход может быть запрещён
                    ticket.status = Ticket.STATUS_ATTENDED
            ticket.checked_in_at = timezone.now()
            ticket.save(update_fields=["status", "checked_in_at", "updated_at"])
            messages.success(request, _("Checked in — welcome!"))
        return redirect("events:checkin", code=ticket.reference_code)
    return render(request, "events/checkin.html", {"ticket": ticket, "event": ticket.event})


def _cancel_linked_stay(ticket) -> None:
    """R5: отменить привязанную бронь проживания (освобождает номер)."""
    booking = ticket.stay_booking
    if booking and booking.status in (booking.STATUS_PENDING, booking.STATUS_CONFIRMED):
        booking.status = booking.STATUS_CANCELLED
        booking.save(update_fields=["status", "updated_at"])


@login_required
def teacher_list(request):
    teachers = Teacher.objects.all()
    return render(request, "events/teacher_list.html", {"teachers": teachers, "nav": "events"})


@login_required
def teacher_create(request):
    form = TeacherForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Teacher created."))
        return redirect("events:teacher-list")
    return render(request, "events/teacher_form.html", {"form": form, "nav": "events"})


@login_required
def teacher_edit(request, pk):
    teacher = get_object_or_404(Teacher, pk=pk)
    form = TeacherForm(request.POST or None, instance=teacher)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Teacher saved."))
        return redirect("events:teacher-list")
    return render(
        request,
        "events/teacher_form.html",
        {"form": form, "teacher": teacher, "nav": "events"},
    )


@login_required
@require_POST
def teacher_delete(request, pk):
    teacher = get_object_or_404(Teacher, pk=pk)
    teacher.delete()
    messages.success(request, _("Teacher deleted."))
    return redirect("events:teacher-list")


@login_required
def roster_csv(request, pk):
    """CSV-ростер участников события (utf-8-sig — Excel-friendly)."""
    event = get_object_or_404(Event, pk=pk)
    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = f'attachment; filename="roster-{event.pk}.csv"'
    writer = csv.writer(response, delimiter=";")
    question_cols = list(event.questions or [])
    reg_cols = registration.labels(event.registration_fields)  # [(key, label)]
    show_unterkunft = event.offers_accommodation
    show_waiver = event.waiver_required  # R8
    writer.writerow(
        [
            "Code",
            "Name",
            "E-Mail",
            "Telefon",
            "Plätze",
            "Status",
            "Bezahlt",
            *(["Unterkunft"] if show_unterkunft else []),
            *(["Waiver"] if show_waiver else []),
            *question_cols,
            *[label for _key, label in reg_cols],
        ]
    )
    for t in event.tickets.select_related("customer", "stay_booking__unit", "waiver").all():
        answers = t.answers or {}
        room = t.stay_booking.unit.name if t.stay_booking and t.stay_booking.unit else ""
        waiver = getattr(t, "waiver", None)
        waiver_cell = (
            f"{waiver.signed_name} ({waiver.signed_at:%d.%m.%Y})"
            if waiver and waiver.signed_at
            else ("✓" if waiver else "—")
        )
        writer.writerow(
            [
                t.reference_code,
                t.customer.name,
                t.customer.email,
                t.customer.phone,
                t.quantity,
                t.get_status_display(),
                t.get_payment_state_display(),
                *([room] if show_unterkunft else []),
                *([waiver_cell] if show_waiver else []),
                *[answers.get(q, "") for q in question_cols],
                *[answers.get(key, "") for key, _label in reg_cols],
            ]
        )
    return response
