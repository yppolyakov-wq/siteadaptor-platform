"""Кабинет владельца: акции (CRUD + переходы статусов) и брони (управление).

Статусы акций двигаем только через PromotionSM; брони — через services
(confirm/fulfill/cancel) поверх ReservationSM. Все вьюхи требуют логина.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from apps.catalog.images import delete_stored_image, save_product_image
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


def _handle_promo_uploads(request, promo) -> None:
    """Сохраняет загруженные файлы в promo.images (FileRef-envelope)."""
    files = request.FILES.getlist("images")
    if not files:
        return
    images = list(promo.images or [])
    has_primary = any(img.get("is_primary") for img in images)
    for f in files:
        try:
            ref = save_product_image(
                f, is_primary=not has_primary, sort_order=len(images), folder="promotions"
            )
        except ValidationError as exc:
            messages.error(request, f"{f.name}: {'; '.join(exc.messages)}")
            continue
        has_primary = True
        images.append(ref)
    promo.images = images
    promo.save(update_fields=["images", "updated_at"])


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
    form = PromotionForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        promo = form.save()
        _handle_promo_uploads(request, promo)
        return redirect("promotions:promotion-edit", pk=promo.pk)
    return render(
        request,
        "promotions/promotion_form.html",
        {"form": form, "is_create": True, "nav": "promotions"},
    )


@login_required
def promotion_edit(request, pk):
    promo = get_object_or_404(Promotion, pk=pk)
    form = PromotionForm(request.POST or None, request.FILES or None, instance=promo)
    if request.method == "POST" and form.is_valid():
        promo = form.save()
        _handle_promo_uploads(request, promo)
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
def promotion_image_delete(request, pk, image_id):
    promo = get_object_or_404(Promotion, pk=pk)
    if request.method == "POST":
        images = list(promo.images or [])
        kept, removed_primary = [], False
        for img in images:
            if img.get("id") == image_id:
                delete_stored_image(img)
                removed_primary = img.get("is_primary", False)
            else:
                kept.append(img)
        if removed_primary and kept:
            kept[0]["is_primary"] = True
        promo.images = kept
        promo.save(update_fields=["images", "updated_at"])
    return redirect("promotions:promotion-edit", pk=pk)


@login_required
def promotion_image_primary(request, pk, image_id):
    promo = get_object_or_404(Promotion, pk=pk)
    if request.method == "POST":
        images = list(promo.images or [])
        for img in images:
            img["is_primary"] = img.get("id") == image_id
        promo.images = images
        promo.save(update_fields=["images", "updated_at"])
    return redirect("promotions:promotion-edit", pk=pk)


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
