"""Кабинет записи по времени (Track D / D3c): /dashboard/booking/.

Календарь-день (записи по ресурсам, навигация ±), действия по FSM
(confirm/fulfill/no_show/cancel) и перенос (services.move с anti-double-book),
ручное добавление записи (сразу confirmed), управление ресурсами: создание,
недельные правила, выходные. Гейтинг — модуль «booking» из реестра.
"""

from datetime import datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core.fsm import IllegalTransition

from . import services
from .models import AvailabilityRule, Booking, ClosedDate, Resource
from .state_machine import BookingSM


@login_required
def calendar(request):
    day = _parse_day_any(request.GET.get("tag"))
    tz = timezone.get_current_timezone()
    day_start = datetime.combine(day, time.min, tzinfo=tz)
    day_end = day_start + timedelta(days=1)
    bookings = (
        Booking.objects.filter(start__gte=day_start, start__lt=day_end)
        .select_related("resource", "customer")
        .order_by("resource__name", "start")
    )
    return render(
        request,
        "booking/calendar.html",
        {
            "nav": "booking",
            "day": day,
            "prev_day": day - timedelta(days=1),
            "next_day": day + timedelta(days=1),
            "bookings": bookings,
            "resources": Resource.objects.filter(is_active=True),
        },
    )


def _parse_day_any(raw):
    """Дата без ограничения горизонтом (кабинету нужна и история)."""
    from datetime import date

    try:
        return date.fromisoformat(raw or "")
    except ValueError:
        return timezone.localdate()


@login_required
@require_POST
def booking_action(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    action = request.POST.get("action", "")
    back = f"{reverse('booking:calendar')}?tag={booking.start.date().isoformat()}"
    if action == "move":
        tz = timezone.get_current_timezone()
        try:
            start = datetime.fromisoformat(request.POST.get("start", ""))
            if timezone.is_naive(start):  # datetime-local приходит без TZ
                start = start.replace(tzinfo=tz)
            end = start + (booking.end - booking.start)  # длительность сохраняем
            services.move(booking, start=start, end=end)
            messages.success(request, _("Booking moved."))
        except ValueError:
            messages.error(request, _("Invalid date."))
        except services.SlotTaken:
            messages.error(request, _("That time is already taken."))
        return redirect(back)
    if action in ("confirmed", "fulfilled", "no_show", "cancelled"):
        try:
            BookingSM().apply(booking, action, actor=request.user)
            messages.success(request, _("Booking updated."))
        except IllegalTransition:
            messages.error(request, _("This step is not possible in the current status."))
    else:
        messages.error(request, _("Unknown action."))
    return redirect(back)


@login_required
@require_POST
def booking_create(request):
    """Ручное добавление (телефонная запись): сразу confirmed."""
    resource = get_object_or_404(Resource, pk=request.POST.get("resource"), is_active=True)
    tz = timezone.get_current_timezone()
    try:
        start = datetime.fromisoformat(request.POST.get("start", ""))
        if timezone.is_naive(start):
            start = start.replace(tzinfo=tz)
        minutes = max(5, min(int(request.POST.get("minutes", "60")), 24 * 60))
    except (TypeError, ValueError):
        messages.error(request, _("Invalid date."))
        return redirect("booking:calendar")
    name = request.POST.get("name", "").strip() or _("Walk-in")
    try:
        booking = services.book(
            resource,
            start=start,
            end=start + timedelta(minutes=minutes),
            name=name,
            email=request.POST.get("email", "").strip(),
            phone=request.POST.get("phone", "").strip(),
            note=request.POST.get("note", "").strip()[:2000],
            source_channel="manual",
            auto_confirm=True,
        )
    except services.SlotTaken:
        messages.error(request, _("That time is already taken."))
        return redirect("booking:calendar")
    except services.ResourceClosed:
        messages.error(request, _("Closed on this date."))
        return redirect("booking:calendar")
    messages.success(request, _("Booking created."))
    return redirect(f"{reverse('booking:calendar')}?tag={booking.start.date().isoformat()}")


@login_required
def resources(request):
    """Ресурсы + недельные правила + выходные — простые POST-формы."""
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "resource":
            name = request.POST.get("name", "").strip()
            if name:
                Resource.objects.create(
                    name=name,
                    type=request.POST.get("type", Resource.TYPE_TABLE),
                    capacity=max(1, min(int(request.POST.get("capacity", "1") or 1), 100)),
                )
                messages.success(request, _("Resource created."))
        elif action == "rule":
            resource = get_object_or_404(Resource, pk=request.POST.get("resource"))
            try:
                AvailabilityRule.objects.create(
                    resource=resource,
                    weekday=int(request.POST.get("weekday", "0")),
                    start_time=request.POST.get("start_time") or "09:00",
                    end_time=request.POST.get("end_time") or "18:00",
                    slot_minutes=max(5, min(int(request.POST.get("slot_minutes", "30")), 480)),
                )
                messages.success(request, _("Opening hours added."))
            except (TypeError, ValueError):
                messages.error(request, _("Invalid input."))
        elif action == "rule_delete":
            AvailabilityRule.objects.filter(pk=request.POST.get("rule")).delete()
        elif action == "closed":
            try:
                ClosedDate.objects.create(
                    date=request.POST.get("date"),
                    reason=request.POST.get("reason", "").strip()[:120],
                )
                messages.success(request, _("Closed date added."))
            except Exception:  # noqa: BLE001 — кривой ввод даты
                messages.error(request, _("Invalid date."))
        elif action == "toggle":
            resource = get_object_or_404(Resource, pk=request.POST.get("resource"))
            resource.is_active = not resource.is_active
            resource.save(update_fields=["is_active", "updated_at"])
        return redirect("booking:resources")

    return render(
        request,
        "booking/resources.html",
        {
            "nav": "booking",
            "resources": Resource.objects.prefetch_related("rules").order_by("-is_active", "name"),
            "closed_dates": ClosedDate.objects.filter(date__gte=timezone.localdate()),
            "types": Resource.TYPES,
            "weekdays": AvailabilityRule.WEEKDAYS,
        },
    )
