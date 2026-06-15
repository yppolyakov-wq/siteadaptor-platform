"""Кабинет date-range-броней (Track E / E2): /dashboard/stays/.

Календарь загрузки (юниты × ночи: свободно/занято/блок), действия по FSM
(confirm/fulfilled/no_show/cancelled) + перенос дат, ручная бронь (сразу
confirmed), управление юнитами (тип/цена/min_nights/max_guests/депозит) и
блокировками дат. Гейтинг — модуль «stays» из реестра (ModuleGatingMiddleware).
"""

from datetime import date, timedelta

import stripe
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.billing import connect
from apps.core.fsm import IllegalTransition

from . import availability, services
from .models import SeasonRate, StayBooking, StayUnit, UnitBlock
from .state_machine import StayBookingSM

HORIZON_DAYS = 30  # ширина окна календаря загрузки


def _int(raw, default, lo, hi) -> int:
    try:
        return max(lo, min(int(raw), hi))
    except (TypeError, ValueError):
        return default


def _eur_to_cents(raw) -> int:
    """«80» / «79,50» → центы (анти-кривой ввод → 0)."""
    try:
        return max(0, round(float(str(raw or "0").replace(",", ".")) * 100))
    except (TypeError, ValueError):
        return 0


def _parse_day(raw) -> date:
    try:
        return date.fromisoformat(raw or "")
    except ValueError:
        return timezone.localdate()


def _refund_deposit(request, booking):
    """Анти-фрод: вернуть депозит при отмене оплаченной брони (Stripe Connect)."""
    try:
        connect.refund(
            connect_id=request.tenant.stripe_connect_id,
            payment_intent=booking.stripe_payment_intent,
        )
        booking.payment_state = StayBooking.PAYMENT_REFUNDED
        booking.save(update_fields=["payment_state", "updated_at"])
        messages.success(request, _("Deposit refunded."))
    except stripe.error.StripeError:
        messages.error(request, _("Refund failed — please check Stripe."))


@login_required
def calendar(request):
    start = _parse_day(request.GET.get("von"))
    units = list(StayUnit.objects.filter(is_active=True))
    days, rows = availability.occupancy_grid(units, start, HORIZON_DAYS)
    window_end = start + timedelta(days=HORIZON_DAYS)
    bookings = (
        StayBooking.objects.filter(
            status__in=StayBooking.ACTIVE_STATUSES,
            arrival__lt=window_end,
            departure__gt=start,
        )
        .select_related("unit", "customer")
        .order_by("arrival")
    )
    return render(
        request,
        "stays/calendar.html",
        {
            "nav": "stays",
            "start": start,
            "prev": start - timedelta(days=HORIZON_DAYS),
            "next": start + timedelta(days=HORIZON_DAYS),
            "today": timezone.localdate(),
            "days": days,
            "rows": rows,
            "bookings": bookings,
            "units": units,
        },
    )


@login_required
@require_POST
def stay_action(request, pk):
    booking = get_object_or_404(StayBooking, pk=pk)
    action = request.POST.get("action", "")
    back = f"{reverse('stays:calendar')}?von={booking.arrival.isoformat()}"
    if action == "move":
        try:
            arrival = date.fromisoformat(request.POST.get("arrival", ""))
            departure = date.fromisoformat(request.POST.get("departure", ""))
            services.move_stay(booking, arrival=arrival, departure=departure)
            messages.success(request, _("Stay moved."))
        except ValueError:
            messages.error(request, _("Invalid dates."))
        except services.MinStay:
            messages.error(request, _("Below the minimum number of nights."))
        except services.StayUnavailable:
            messages.error(request, _("Those dates are no longer available."))
        return redirect(back)
    if action in ("confirmed", "fulfilled", "no_show", "cancelled"):
        try:
            StayBookingSM().apply(booking, action, actor=request.user)
        except IllegalTransition:
            messages.error(request, _("This step is not possible in the current status."))
            return redirect(back)
        messages.success(request, _("Stay updated."))
        # анти-фрод: отмена оплаченной брони возвращает депозит (E4 wires Stripe)
        if (
            action == "cancelled"
            and booking.payment_state == StayBooking.PAYMENT_PAID
            and booking.stripe_payment_intent
        ):
            _refund_deposit(request, booking)
    else:
        messages.error(request, _("Unknown action."))
    return redirect(back)


@login_required
@require_POST
def stay_create(request):
    """Ручное добавление (телефонная/личная бронь): сразу confirmed."""
    unit = get_object_or_404(StayUnit, pk=request.POST.get("unit"), is_active=True)
    try:
        arrival = date.fromisoformat(request.POST.get("arrival", ""))
        departure = date.fromisoformat(request.POST.get("departure", ""))
    except ValueError:
        messages.error(request, _("Invalid dates."))
        return redirect("stays:calendar")
    name = request.POST.get("name", "").strip() or _("Walk-in")
    try:
        booking = services.book_stay(
            unit,
            arrival=arrival,
            departure=departure,
            name=name,
            email=request.POST.get("email", "").strip(),
            phone=request.POST.get("phone", "").strip(),
            guests=_int(request.POST.get("guests", "1"), 1, 1, 50),
            note=request.POST.get("note", "").strip()[:2000],
            source_channel="manual",
            auto_confirm=True,
        )
    except services.MinStay:
        messages.error(request, _("Below the minimum number of nights."))
        return redirect("stays:calendar")
    except services.MaxGuests:
        messages.error(request, _("Too many guests for this unit."))
        return redirect("stays:calendar")
    except services.StayUnavailable:
        messages.error(request, _("Those dates are no longer available."))
        return redirect("stays:calendar")
    except ValueError:
        messages.error(request, _("Invalid dates."))
        return redirect("stays:calendar")
    messages.success(request, _("Stay created."))
    return redirect(f"{reverse('stays:calendar')}?von={booking.arrival.isoformat()}")


@login_required
def units(request):
    """Юниты (тип/цена/вместимость/депозит) + блокировки дат — POST-формы."""
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "unit":
            name = request.POST.get("name", "").strip()
            if name:
                StayUnit.objects.create(
                    name=name,
                    type=request.POST.get("type", StayUnit.TYPE_ROOM),
                    quantity=_int(request.POST.get("quantity", "1"), 1, 1, 999),
                    price_cents=_eur_to_cents(request.POST.get("price_eur")),
                    weekend_price_cents=_eur_to_cents(request.POST.get("weekend_price_eur")),
                    min_nights=_int(request.POST.get("min_nights", "1"), 1, 1, 365),
                    max_guests=_int(request.POST.get("max_guests", "2"), 2, 1, 99),
                    deposit_cents=_eur_to_cents(request.POST.get("deposit_eur")),
                    require_manual_confirm=bool(request.POST.get("require_manual_confirm")),
                )
                messages.success(request, _("Unit created."))
        elif action == "unit_settings":
            unit = get_object_or_404(StayUnit, pk=request.POST.get("unit"))
            unit.price_cents = _eur_to_cents(request.POST.get("price_eur"))
            unit.weekend_price_cents = _eur_to_cents(request.POST.get("weekend_price_eur"))
            unit.quantity = _int(request.POST.get("quantity", "1"), 1, 1, 999)
            unit.min_nights = _int(request.POST.get("min_nights", "1"), 1, 1, 365)
            unit.max_guests = _int(request.POST.get("max_guests", "2"), 2, 1, 99)
            unit.deposit_cents = _eur_to_cents(request.POST.get("deposit_eur"))
            unit.require_manual_confirm = bool(request.POST.get("require_manual_confirm"))
            unit.save(
                update_fields=[
                    "price_cents",
                    "weekend_price_cents",
                    "quantity",
                    "min_nights",
                    "max_guests",
                    "deposit_cents",
                    "require_manual_confirm",
                    "updated_at",
                ]
            )
            messages.success(request, _("Unit saved."))
        elif action == "rate":  # A5a: сезонный тариф
            unit = get_object_or_404(StayUnit, pk=request.POST.get("unit"))
            try:
                start_date = date.fromisoformat(request.POST.get("start_date", ""))
                end_date = date.fromisoformat(request.POST.get("end_date", ""))
                if end_date < start_date:
                    raise ValueError
                SeasonRate.objects.create(
                    unit=unit,
                    label=request.POST.get("label", "").strip()[:120],
                    start_date=start_date,
                    end_date=end_date,
                    price_cents=_eur_to_cents(request.POST.get("price_eur")),
                )
                messages.success(request, _("Season rate added."))
            except (TypeError, ValueError):
                messages.error(request, _("Invalid dates."))
        elif action == "rate_delete":
            SeasonRate.objects.filter(pk=request.POST.get("rate")).delete()
        elif action == "toggle":
            unit = get_object_or_404(StayUnit, pk=request.POST.get("unit"))
            unit.is_active = not unit.is_active
            unit.save(update_fields=["is_active", "updated_at"])
        elif action == "block":
            unit = get_object_or_404(StayUnit, pk=request.POST.get("unit"))
            try:
                start_date = date.fromisoformat(request.POST.get("start_date", ""))
                end_date = date.fromisoformat(request.POST.get("end_date", ""))
                if end_date < start_date:
                    raise ValueError
                UnitBlock.objects.create(
                    unit=unit,
                    start_date=start_date,
                    end_date=end_date,
                    reason=request.POST.get("reason", "").strip()[:120],
                )
                messages.success(request, _("Dates blocked."))
            except (TypeError, ValueError):
                messages.error(request, _("Invalid dates."))
        elif action == "block_delete":
            UnitBlock.objects.filter(pk=request.POST.get("block")).delete()
        return redirect("stays:units")

    return render(
        request,
        "stays/units.html",
        {
            "nav": "stays",
            "units": StayUnit.objects.prefetch_related("blocks", "season_rates").order_by(
                "-is_active", "name"
            ),
            "types": StayUnit.TYPES,
            "today": timezone.localdate(),
        },
    )
