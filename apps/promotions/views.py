"""Кабинет владельца: акции (CRUD + переходы статусов) и брони (управление).

Статусы акций двигаем только через PromotionSM; брони — через services
(confirm/fulfill/cancel) поверх ReservationSM. Все вьюхи требуют логина.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.catalog.images import delete_stored_image, save_product_image
from apps.core.fsm import IllegalTransition

from . import services
from .forms import LoyaltyProgramForm, PromotionForm, VoucherCreateForm
from .models import Customer, LoyaltyCard, LoyaltyProgram, Promotion, Reservation, Voucher
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
    # атрибуция: брони по каналам привлечения
    channel_stats = list(
        promo.reservations.values("source_channel").annotate(n=Count("id")).order_by("-n")
    )
    # предустановленные каналы для генерации QR
    preset_channels = ["instagram", "facebook", "flyer", "schaufenster", "website"]
    return render(
        request,
        "promotions/promotion_form.html",
        {
            "form": form,
            "is_create": False,
            "promotion": promo,
            "actions": _promo_actions(promo),
            "channel_stats": channel_stats,
            "preset_channels": preset_channels,
            "waitlist_count": promo.waitlist.count(),
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


# ---------------------------------------------------------------------------
# Погашение брони (Einlösen): скан QR / ручной ввод кода → выдача
# ---------------------------------------------------------------------------


@login_required
def redeem_home(request):
    """Страница погашения: браузерный сканер + ручной ввод кода."""
    if request.method == "POST":
        code = (request.POST.get("code") or "").strip().upper()
        if code:
            return redirect("promotions:redeem-detail", code=code)
        messages.error(request, "Bitte einen Code eingeben.")
    return render(request, "promotions/redeem.html", {"nav": "redeem"})


@login_required
def redeem_detail(request, code):
    code = code.strip().upper()
    res = (
        Reservation.objects.select_related("promotion", "customer")
        .filter(reference_code=code)
        .first()
    )
    # авто-погашение по скану (если включено у бизнеса): сотрудник открыл QR →
    # бронь сразу выдаётся. Идемпотентно (повторный скан выданной — no-op).
    auto = getattr(getattr(request, "tenant", None), "auto_redeem_on_scan", False)
    if res is not None and auto and res.status in ("pending", "confirmed"):
        try:
            if res.status == "pending":
                services.confirm(res, actor=request.user)
            services.fulfill(res, actor=request.user)
            res.refresh_from_db()
            messages.success(request, f"{code}: ausgegeben ✓ (Auto)")
        except IllegalTransition:
            pass
    return render(
        request,
        "promotions/redeem_detail.html",
        {"reservation": res, "code": code, "nav": "redeem"},
    )


@login_required
def redeem_action(request, code):
    code = code.strip().upper()
    res = get_object_or_404(Reservation, reference_code=code)
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
                messages.success(request, f"{code}: {action} ✓")
            except IllegalTransition:
                messages.error(request, f"Status „{res.status}“ — Aktion „{action}“ nicht möglich.")
    return redirect("promotions:redeem-detail", code=code)


# ---------------------------------------------------------------------------
# Ваучеры / промокоды
# ---------------------------------------------------------------------------

_VOUCHER_ERRORS = {
    "not_found": "Code nicht gefunden.",
    "inactive": "Voucher deaktiviert.",
    "expired": "Voucher abgelaufen.",
    "used_up": "Voucher bereits eingelöst.",
}


@login_required
def voucher_list(request):
    form = VoucherCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        created = services.generate_vouchers(
            label=form.cleaned_data["label"],
            count=form.cleaned_data["count"],
            max_uses=form.cleaned_data["max_uses"],
            expires_at=form.cleaned_data.get("expires_at"),
        )
        messages.success(request, f"{len(created)} Voucher erstellt.")
        return redirect("promotions:voucher-list")
    return render(
        request,
        "promotions/vouchers.html",
        {"form": form, "vouchers": Voucher.objects.all()[:200], "nav": "vouchers"},
    )


@login_required
def voucher_redeem(request):
    if request.method == "POST":
        try:
            voucher = services.redeem_voucher(request.POST.get("code", ""))
            uses = f" ({voucher.used_count}/{voucher.max_uses})" if voucher.max_uses else ""
            messages.success(request, f"{voucher.code}: {voucher.label} ✓{uses}")
        except services.VoucherError as exc:
            messages.error(request, _VOUCHER_ERRORS.get(exc.reason, exc.reason))
        return redirect("promotions:voucher-redeem")

    code = (request.GET.get("code") or "").strip().upper()
    voucher = Voucher.objects.filter(code=code).first() if code else None
    # авто-погашение по скану, если включено у бизнеса
    auto = getattr(getattr(request, "tenant", None), "auto_redeem_on_scan", False)
    if voucher is not None and auto and voucher.is_redeemable:
        try:
            voucher = services.redeem_voucher(code)
            messages.success(request, f"{voucher.code}: {voucher.label} ✓ (Auto)")
        except services.VoucherError as exc:
            messages.error(request, _VOUCHER_ERRORS.get(exc.reason, exc.reason))
            voucher = Voucher.objects.filter(code=code).first()
    return render(
        request,
        "promotions/voucher_redeem.html",
        {"code": code, "voucher": voucher, "nav": "vouchers"},
    )


# ---------------------------------------------------------------------------
# Лояльность (штампы)
# ---------------------------------------------------------------------------


@login_required
def loyalty_list(request):
    form = LoyaltyProgramForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Programm erstellt.")
        return redirect("promotions:loyalty-list")
    return render(
        request,
        "promotions/loyalty.html",
        {"form": form, "programs": LoyaltyProgram.objects.all(), "nav": "loyalty"},
    )


def _resolve_card(program, *, token="", email=""):
    if token:
        return (
            LoyaltyCard.objects.filter(program=program, token=token)
            .select_related("customer")
            .first()
        )
    if email:
        customer = Customer.objects.filter(email__iexact=email).order_by("created_at").first()
        if customer is None:
            customer = Customer.objects.create(email=email, name="")
        return services.get_or_create_card(program, customer)
    return None


@login_required
def loyalty_stamp(request, program_id):
    program = get_object_or_404(LoyaltyProgram, pk=program_id)

    if request.method == "POST":
        card = (
            LoyaltyCard.objects.filter(pk=request.POST.get("card_id"))
            .select_related("program")
            .first()
        )
        if card is not None:
            try:
                card, reward = services.add_stamp(card)
                msg = f"Stempel +1 ({card.stamps}/{program.stamps_required})"
                if reward is not None:
                    msg += f" — Belohnung: {reward.label} [{reward.code}]"
                messages.success(request, msg)
            except services.LoyaltyError:
                messages.error(request, "Zu schnell — bitte kurz warten.")
            return redirect(
                f"{reverse('promotions:loyalty-stamp', args=[program.pk])}?card={card.token}"
            )
        messages.error(request, "Karte nicht gefunden.")
        return redirect("promotions:loyalty-stamp", program_id=program.pk)

    card = _resolve_card(
        program,
        token=(request.GET.get("card") or "").strip(),
        email=(request.GET.get("email") or "").strip().lower(),
    )
    return render(
        request,
        "promotions/loyalty_stamp.html",
        {"program": program, "card": card, "nav": "loyalty"},
    )
