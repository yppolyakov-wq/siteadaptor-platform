"""Публичная date-range-бронь на витрине (Track E / E3+E4): /unterkunft/.

Флоу без JS: список юнитов → юнит (выбор Anreise/Abreise/Gäste через GET-форму,
показ доступности + цены) → POST buchen (honeypot + rate-limit по IP, диапазон
ре-валидируется, гонку закрывает services.book_stay) → подтверждение /s/<code>/.
Модуль stays выключен → 404. Депозит (E4): при заданном депозите и подключённом
Stripe Connect ведём на оплату, иначе обычная бронь.
"""

from datetime import date, timedelta

import stripe
from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.billing import connect
from apps.core import ratelimit

from . import availability, payments, services
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
    from . import pricing

    return nights, pricing.quote_total_cents(unit, von, bis), True, None


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
    tenant = getattr(request, "tenant", None)
    deposit_required = unit.deposit_cents > 0 and getattr(tenant, "payments_enabled", False)
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
            "deposit_required": deposit_required,
            "deposit_eur": f"{unit.deposit_cents / 100:.2f}".replace(".", ","),
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

    # Депозит (E4): если у юнита задан и бизнес принимает оплату — ведём на
    # Stripe Checkout (на счёт бизнеса). Без депозита/оплаты — обычная бронь.
    tenant = getattr(request, "tenant", None)
    if (
        unit.deposit_cents > 0
        and getattr(tenant, "payments_enabled", False)
        and connect.is_connect_configured()
    ):
        booking.deposit_cents = unit.deposit_cents
        booking.payment_state = StayBooking.PAYMENT_PENDING
        booking.save(update_fields=["deposit_cents", "payment_state", "updated_at"])
        ok_url = (
            request.build_absolute_uri(reverse("storefront-stay-ok", args=[booking.reference_code]))
            + "?paid=1"
        )
        cancel_url = request.build_absolute_uri(
            reverse("storefront-unterkunft-unit", args=[unit.pk])
        )
        try:
            return redirect(
                payments.stay_deposit_checkout_url(
                    booking, tenant, success_url=ok_url, cancel_url=cancel_url
                )
            )
        except stripe.error.StripeError:
            # оплата временно недоступна — бронь остаётся (pending), не теряем её
            pass
    return redirect("storefront-stay-ok", code=booking.reference_code)


def unterkunft_confirmation(request, code):
    _require_stays_active(request)
    booking = get_object_or_404(StayBooking.objects.select_related("unit"), reference_code=code)
    from apps.telegram.notify import deep_link

    return render(
        request,
        "storefront/stay_confirmation.html",
        {"booking": booking, "telegram_link": deep_link(booking.customer)},
    )


_ICAL_SALT = "stay-ical"


def ical_token(unit) -> str:
    from django.core import signing

    return signing.dumps(str(unit.pk), salt=_ICAL_SALT)


def unterkunft_ical(request, token):
    """Публичный iCal-фид занятости юнита (A5b) — Booking.com/Airbnb/Google.

    Токен подписан (signing) и несёт pk юнита; гейтинг модулем stays. Отдаёт
    активные брони + блоки как all-day VEVENT.
    """
    _require_stays_active(request)
    from django.core import signing

    from . import ical
    from .models import UnitBlock

    try:
        unit_pk = signing.loads(token, salt=_ICAL_SALT)
    except signing.BadSignature as exc:
        raise Http404 from exc
    unit = get_object_or_404(StayUnit, pk=unit_pk)
    bookings = StayBooking.objects.filter(unit=unit, status__in=StayBooking.ACTIVE_STATUSES)
    blocks = UnitBlock.objects.filter(unit=unit)
    body = ical.build_feed(unit, bookings, blocks, host=request.get_host())
    return HttpResponse(body, content_type="text/calendar; charset=utf-8")
