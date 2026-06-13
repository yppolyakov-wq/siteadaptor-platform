"""Публичная запись по времени на витрине (Track D / D3b): /termin/.

Флоу: выбор ресурса → день (по умолчанию сегодня, навигация ±) → свободный
слот → форма контактов (как у брони акции: honeypot + rate-limit по IP) →
подтверждение /t/<code>/. Слот валидируется по сетке free_slots, гонку
закрывает services.book (anti-double-book). Модуль booking выключен → 404.
"""

from datetime import date, datetime, timedelta

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
from .models import Booking, Resource, Service

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
    services_qs = Service.objects.filter(is_active=True)
    if services_qs.exists():  # G10: бизнес услуг — выбираем услугу, не ресурс
        return render(request, "storefront/service_index.html", {"services": services_qs})
    resources = Resource.objects.filter(is_active=True)
    if resources.count() == 1:  # один ресурс — сразу к слотам
        return redirect("storefront-termin-slots", pk=resources.first().pk)
    return render(request, "storefront/booking_index.html", {"resources": resources})


def service_slots(request, pk):
    """G10: свободные старты под услугу (по всем ресурсам), форма брони."""
    _require_booking_active(request)
    service = get_object_or_404(Service, pk=pk, is_active=True)
    day = _parse_day(request.GET.get("tag"))
    today = timezone.localdate()
    starts = availability.service_slots(service, day)
    selected = None
    raw = request.GET.get("slot", "")
    if raw:
        selected = next((s for s in starts if s.isoformat() == raw), None)
    tenant = getattr(request, "tenant", None)
    return render(
        request,
        "storefront/service_slots.html",
        {
            "service": service,
            "day": day,
            "starts": starts,
            "selected": selected,
            "deposit_required": service.deposit_cents > 0
            and getattr(tenant, "payments_enabled", False),
            "deposit_eur": f"{service.deposit_cents / 100:.2f}".replace(".", ","),
            "prev_day": day - timedelta(days=1) if day > today else None,
            "next_day": day + timedelta(days=1)
            if day < today + timedelta(days=MAX_DAYS_AHEAD)
            else None,
        },
    )


def service_book(request, pk):
    _require_booking_active(request)
    if request.method != "POST":
        return redirect("storefront-service-slots", pk=pk)
    service = get_object_or_404(Service, pk=pk, is_active=True)
    if request.POST.get("website"):  # honeypot
        return redirect("storefront-service-slots", pk=pk)
    if ratelimit.hit("termin", ratelimit.client_ip(request), limit=RL_LIMIT, window=RL_WINDOW):
        return HttpResponse(status=429)
    try:
        start = datetime.fromisoformat(request.POST.get("start", ""))
    except ValueError:
        raise Http404 from None
    if start not in availability.service_slots(service, start.date()):
        messages.error(request, _("This time is no longer available. Please pick another."))
        return redirect("storefront-service-slots", pk=pk)
    resource = availability.assign_resource(service, start)
    name = request.POST.get("name", "").strip()
    if resource is None or not name:
        messages.error(
            request,
            _("This time is no longer available. Please pick another.")
            if resource is None
            else _("Please tell us your name."),
        )
        return redirect("storefront-service-slots", pk=pk)
    try:
        booking = services.book(
            resource,
            start=start,
            end=start + timedelta(minutes=service.duration_minutes),
            name=name,
            email=request.POST.get("email", "").strip(),
            phone=request.POST.get("phone", "").strip(),
            note=request.POST.get("note", "").strip()[:2000],
            source_channel=(request.GET.get("ch") or "")[:50],
            service=service,
            price_cents=service.price_cents,
        )
    except (services.SlotTaken, services.ResourceClosed):
        messages.error(request, _("This time is no longer available. Please pick another."))
        return redirect("storefront-service-slots", pk=pk)

    # Депозит услуги (P2.5b): на Stripe Checkout, иначе обычная запись.
    tenant = getattr(request, "tenant", None)
    if (
        service.deposit_cents > 0
        and getattr(tenant, "payments_enabled", False)
        and connect.is_connect_configured()
    ):
        booking.deposit_cents = service.deposit_cents
        booking.payment_state = Booking.PAYMENT_PENDING
        booking.save(update_fields=["deposit_cents", "payment_state", "updated_at"])
        ok_url = (
            request.build_absolute_uri(
                reverse("storefront-termin-ok", args=[booking.reference_code])
            )
            + "?paid=1"
        )
        cancel_url = request.build_absolute_uri(
            reverse("storefront-service-slots", args=[service.pk])
        )
        try:
            return redirect(
                payments.deposit_checkout_url(
                    booking, tenant, success_url=ok_url, cancel_url=cancel_url
                )
            )
        except stripe.error.StripeError:
            pass
    return redirect("storefront-termin-ok", code=booking.reference_code)


def termin_slots(request, pk):
    _require_booking_active(request)
    resource = get_object_or_404(Resource, pk=pk, is_active=True)
    day = _parse_day(request.GET.get("tag"))
    today = timezone.localdate()
    # G9: слоты с остатком мест; для групповых курсов (capacity>1) → «N frei».
    slots = availability.free_slots_with_spots(resource, day)
    # Выбранный слот (?slot=<start iso>) раскрывает форму контактов — без JS.
    selected = None
    raw_slot = request.GET.get("slot", "")
    if raw_slot:
        for start, end, _spots in slots:
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
            "group": resource.capacity > 1,
            "selected": selected,
            "deposit_required": resource.deposit_cents > 0
            and getattr(getattr(request, "tenant", None), "payments_enabled", False),
            "deposit_eur": f"{resource.deposit_cents / 100:.2f}".replace(".", ","),
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

    # Депозит (P2.5b): если у ресурса задан и бизнес принимает оплату — ведём на
    # Stripe Checkout (на счёт бизнеса). Без депозита/оплаты — обычная бронь.
    tenant = getattr(request, "tenant", None)
    if (
        resource.deposit_cents > 0
        and getattr(tenant, "payments_enabled", False)
        and connect.is_connect_configured()
    ):
        booking.deposit_cents = resource.deposit_cents
        booking.payment_state = Booking.PAYMENT_PENDING
        booking.save(update_fields=["deposit_cents", "payment_state", "updated_at"])
        ok_url = (
            request.build_absolute_uri(
                reverse("storefront-termin-ok", args=[booking.reference_code])
            )
            + "?paid=1"
        )
        cancel_url = request.build_absolute_uri(
            reverse("storefront-termin-slots", args=[resource.pk])
        )
        try:
            return redirect(
                payments.deposit_checkout_url(
                    booking, tenant, success_url=ok_url, cancel_url=cancel_url
                )
            )
        except stripe.error.StripeError:
            # оплата временно недоступна — бронь остаётся (pending), не теряем её
            pass
    return redirect("storefront-termin-ok", code=booking.reference_code)


def termin_confirmation(request, code):
    _require_booking_active(request)
    booking = get_object_or_404(Booking.objects.select_related("resource"), reference_code=code)
    return render(request, "storefront/booking_confirmation.html", {"booking": booking})
