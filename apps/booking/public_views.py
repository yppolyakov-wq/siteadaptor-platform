"""Публичная запись по времени на витрине (Track D / D3b): /termin/.

Флоу: выбор ресурса → день (по умолчанию сегодня, навигация ±) → свободный
слот → форма контактов (как у брони акции: honeypot + rate-limit по IP) →
подтверждение /t/<code>/. Слот валидируется по сетке free_slots, гонку
закрывает services.book (anti-double-book). Модуль booking выключен → 404.
"""

from datetime import date, datetime, timedelta

from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import ratelimit

from . import availability, services
from .models import Booking, Resource

RL_LIMIT = 5  # попыток записи на IP
RL_WINDOW = 600  # за 10 минут
MAX_DAYS_AHEAD = 30  # горизонт записи


def _require_booking_active(request):
    tenant = getattr(request, "tenant", None)
    if tenant is None or not tenant.is_module_active("booking"):
        raise Http404


def _parse_day(raw) -> date:
    today = timezone.localdate()
    try:
        day = date.fromisoformat(raw or "")
    except ValueError:
        return today
    return min(max(day, today), today + timedelta(days=MAX_DAYS_AHEAD))


def termin_index(request):
    _require_booking_active(request)
    resources = Resource.objects.filter(is_active=True)
    if resources.count() == 1:  # один ресурс — сразу к слотам
        return redirect("storefront-termin-slots", pk=resources.first().pk)
    return render(request, "storefront/booking_index.html", {"resources": resources})


def termin_slots(request, pk):
    _require_booking_active(request)
    resource = get_object_or_404(Resource, pk=pk, is_active=True)
    day = _parse_day(request.GET.get("tag"))
    today = timezone.localdate()
    slots = availability.free_slots(resource, day)
    # Выбранный слот (?slot=<start iso>) раскрывает форму контактов — без JS.
    selected = None
    raw_slot = request.GET.get("slot", "")
    if raw_slot:
        for start, end in slots:
            if start.isoformat() == raw_slot:
                selected = (start, end)
                break
    return render(
        request,
        "storefront/booking_slots.html",
        {
            "resource": resource,
            "day": day,
            "slots": slots,
            "selected": selected,
            "prev_day": day - timedelta(days=1) if day > today else None,
            "next_day": day + timedelta(days=1)
            if day < today + timedelta(days=MAX_DAYS_AHEAD)
            else None,
        },
    )


def termin_book(request, pk):
    _require_booking_active(request)
    if request.method != "POST":
        return redirect("storefront-termin-slots", pk=pk)
    resource = get_object_or_404(Resource, pk=pk, is_active=True)
    if request.POST.get("website"):  # honeypot
        return redirect("storefront-termin-slots", pk=pk)
    if ratelimit.hit("termin", ratelimit.client_ip(request), limit=RL_LIMIT, window=RL_WINDOW):
        return HttpResponse(status=429)

    try:
        start = datetime.fromisoformat(request.POST.get("start", ""))
        end = datetime.fromisoformat(request.POST.get("end", ""))
    except ValueError:
        raise Http404 from None
    # Слот должен существовать в сетке расписания — иначе произвольный интервал.
    if (start, end) not in availability.free_slots(resource, start.date()):
        messages.error(request, _("This slot is no longer available. Please pick another."))
        return redirect("storefront-termin-slots", pk=pk)

    name = request.POST.get("name", "").strip()
    if not name:
        messages.error(request, _("Please tell us your name."))
        return redirect("storefront-termin-slots", pk=pk)
    try:
        party_size = max(1, min(int(request.POST.get("party_size", "1")), 50))
    except (TypeError, ValueError):
        party_size = 1
    try:
        booking = services.book(
            resource,
            start=start,
            end=end,
            name=name,
            email=request.POST.get("email", "").strip(),
            phone=request.POST.get("phone", "").strip(),
            party_size=party_size,
            note=request.POST.get("note", "").strip()[:2000],
            source_channel=(request.GET.get("ch") or "")[:50],
        )
    except (services.SlotTaken, services.ResourceClosed):
        messages.error(request, _("This slot is no longer available. Please pick another."))
        return redirect("storefront-termin-slots", pk=pk)
    return redirect("storefront-termin-ok", code=booking.reference_code)


def termin_confirmation(request, code):
    _require_booking_active(request)
    booking = get_object_or_404(Booking.objects.select_related("resource"), reference_code=code)
    return render(request, "storefront/booking_confirmation.html", {"booking": booking})
