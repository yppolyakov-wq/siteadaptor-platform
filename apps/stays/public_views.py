"""Публичная date-range-бронь на витрине (Track E / E3): /unterkunft/.

Флоу без JS: список юнитов → юнит (выбор Anreise/Abreise/Gäste через GET-форму,
показ доступности + цены) → POST buchen (honeypot + rate-limit по IP, диапазон
ре-валидируется, гонку закрывает services.book_stay) → подтверждение /s/<code>/.
Модуль stays выключен → 404. Онлайн-депозит — E4.
"""

from datetime import date, timedelta

from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import ratelimit

from . import availability, services
from .models import StayBooking, StayUnit

RL_LIMIT = 5  # попыток брони на IP
RL_WINDOW = 600  # за 10 минут
MAX_DAYS_AHEAD = 365  # горизонт заезда


def _require_stays_active(request):
    tenant = getattr(request, "tenant", None)
    if tenant is None or not tenant.is_module_active("stays"):
        raise Http404


def _parse_date(raw):
    try:
        return date.fromisoformat(raw or "")
    except (TypeError, ValueError):
        return None


def _quote(unit, von, bis, guests):
    """(nights, total_cents, available, reason) для выбранного диапазона."""
    nights = (bis - von).days
    if nights < unit.min_nights:
        return nights, 0, False, "min_nights"
    if guests > unit.max_guests:
        return nights, 0, False, "guests"
    if not availability.range_available(unit, von, bis):
        return nights, 0, False, "unavailable"
    return nights, unit.price_cents * nights, True, None


def unterkunft_index(request):
    _require_stays_active(request)
    units = StayUnit.objects.filter(is_active=True)
    if units.count() == 1:
        return redirect("storefront-unterkunft-unit", pk=units.first().pk)
    return render(request, "storefront/stay_index.html", {"units": units})


def unterkunft_unit(request, pk):
    _require_stays_active(request)
    unit = get_object_or_404(StayUnit, pk=pk, is_active=True)
    today = timezone.localdate()
    von = _parse_date(request.GET.get("von"))
    bis = _parse_date(request.GET.get("bis"))
    try:
        guests = max(1, min(int(request.GET.get("gaeste", "2")), 50))
    except (TypeError, ValueError):
        guests = 2

    quote = None
    if von and bis and von >= today and bis > von:
        nights, total_cents, available, reason = _quote(unit, von, bis, guests)
        quote = {
            "von": von,
            "bis": bis,
            "guests": guests,
            "nights": nights,
            "total_eur": total_cents / 100,
            "available": available,
            "reason": reason,
        }
    return render(
        request,
        "storefront/stay_detail.html",
        {
            "unit": unit,
            "today": today,
            "max_date": today + timedelta(days=MAX_DAYS_AHEAD),
            "von": von,
            "bis": bis,
            "guests": guests,
            "quote": quote,
        },
    )


def _back_to_unit(pk, von, bis, guests):
    url = reverse("storefront-unterkunft-unit", args=[pk])
    if von and bis:
        return f"{url}?von={von}&bis={bis}&gaeste={guests}"
    return url


def unterkunft_book(request, pk):
    _require_stays_active(request)
    if request.method != "POST":
        return redirect("storefront-unterkunft-unit", pk=pk)
    unit = get_object_or_404(StayUnit, pk=pk, is_active=True)
    if request.POST.get("website"):  # honeypot
        return redirect("storefront-unterkunft-unit", pk=pk)
    if ratelimit.hit("stay", ratelimit.client_ip(request), limit=RL_LIMIT, window=RL_WINDOW):
        return HttpResponse(status=429)

    von = _parse_date(request.POST.get("von"))
    bis = _parse_date(request.POST.get("bis"))
    try:
        guests = max(1, min(int(request.POST.get("gaeste", "2")), 50))
    except (TypeError, ValueError):
        guests = 2
    if not (von and bis):
        raise Http404
    back = _back_to_unit(pk, von, bis, guests)

    name = request.POST.get("name", "").strip()
    if not name:
        messages.error(request, _("Please tell us your name."))
        return redirect(back)
    try:
        booking = services.book_stay(
            unit,
            arrival=von,
            departure=bis,
            name=name,
            email=request.POST.get("email", "").strip(),
            phone=request.POST.get("phone", "").strip(),
            guests=guests,
            note=request.POST.get("note", "").strip()[:2000],
            source_channel=(request.GET.get("ch") or "")[:50],
        )
    except services.MinStay:
        messages.error(request, _("Please book at least the minimum number of nights."))
        return redirect(back)
    except services.MaxGuests:
        messages.error(request, _("Too many guests for this unit."))
        return redirect(back)
    except (services.StayUnavailable, ValueError):
        messages.error(
            request, _("These dates are no longer available. Please pick another range.")
        )
        return redirect(back)

    return redirect("storefront-stay-ok", code=booking.reference_code)


def unterkunft_confirmation(request, code):
    _require_stays_active(request)
    booking = get_object_or_404(StayBooking.objects.select_related("unit"), reference_code=code)
    return render(request, "storefront/stay_confirmation.html", {"booking": booking})
