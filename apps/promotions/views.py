"""Кабинет владельца: акции (CRUD + переходы статусов) и брони (управление).

Статусы акций двигаем только через PromotionSM; брони — через services
(confirm/fulfill/cancel) поверх ReservationSM. Все вьюхи требуют логина.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.fsm import IllegalTransition

from . import services
from .forms import PromotionForm
from .models import Promotion, Reservation
from .state_machine import PromotionSM

PROMO_STATUSES = ["draft", "scheduled", "active", "paused", "ended", "archived"]
RESERVATION_STATUSES = ["pending", "confirmed", "fulfilled", "cancelled", "expired"]

# подписи для кнопок переходов акции
_PROMO_ACTION_LABELS = {
    "scheduled": "Schedule",
    "active": "Activate",
    "paused": "Pause",
    "ended": "End",
    "archived": "Archive",
}


def _promo_actions(promo):
    """Доступные переходы акции как [(target, label)]."""
    return [
        (t, _PROMO_ACTION_LABELS.get(t, t)) for t in PromotionSM().allowed_targets(promo.status)
    ]


@login_required
def promotion_list(request):
    promos = Promotion.objects.select_related("product").all()
    status = request.GET.get("status", "")
    if status:
        promos = promos.filter(status=status)
    return render(
        request,
        "promotions/promotion_list.html",
        {"promotions": promos, "statuses": PROMO_STATUSES, "status": status, "nav": "promotions"},
    )


@login_required
def promotion_create(request):
    form = PromotionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        promo = form.save()
        return redirect("promotions:promotion-edit", pk=promo.pk)
    return render(
        request,
        "promotions/promotion_form.html",
        {"form": form, "is_create": True, "nav": "promotions"},
    )


@login_required
def promotion_edit(request, pk):
    promo = get_object_or_404(Promotion, pk=pk)
    form = PromotionForm(request.POST or None, instance=promo)
    if request.method == "POST" and form.is_valid():
        promo = form.save()
        return redirect("promotions:promotion-edit", pk=promo.pk)
    return render(
        request,
        "promotions/promotion_form.html",
        {
            "form": form,
            "is_create": False,
            "promotion": promo,
            "actions": _promo_actions(promo),
            "nav": "promotions",
        },
    )


@login_required
def promotion_transition(request, pk):
    promo = get_object_or_404(Promotion, pk=pk)
    if request.method == "POST":
        target = request.POST.get("target", "")
        try:
            PromotionSM().apply(promo, target, actor=request.user)
            messages.success(request, f"Status: {target}")
        except IllegalTransition:
            messages.error(request, f"Transition to {target} is not allowed.")
    return redirect("promotions:promotion-edit", pk=pk)


@login_required
def reservation_list(request):
    qs = Reservation.objects.select_related("promotion", "customer").all()
    status = request.GET.get("status", "")
    promotion_id = request.GET.get("promotion", "")
    if status:
        qs = qs.filter(status=status)
    if promotion_id:
        qs = qs.filter(promotion_id=promotion_id)
    return render(
        request,
        "promotions/reservation_list.html",
        {
            "reservations": qs[:200],
            "statuses": RESERVATION_STATUSES,
            "status": status,
            "promotions": Promotion.objects.all(),
            "selected_promotion": promotion_id,
            "nav": "reservations",
        },
    )


@login_required
def reservation_action(request, pk):
    res = get_object_or_404(Reservation, pk=pk)
    if request.method == "POST":
        action = request.POST.get("action", "")
        handler = {
            "confirm": services.confirm,
            "fulfill": services.fulfill,
            "cancel": services.cancel,
        }.get(action)
        if handler is None:
            messages.error(request, "Unknown action.")
        else:
            try:
                handler(res, actor=request.user)
                messages.success(request, f"Reservation {action}ed.")
            except IllegalTransition:
                messages.error(request, f"Cannot {action} a reservation in status “{res.status}”.")
    return redirect("promotions:reservation-list")
