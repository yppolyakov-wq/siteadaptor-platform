"""Публичная витрина брони (без логина), на корне субдомена бизнеса.

Защита публичной формы: honeypot (website), rate-limit по IP+акции и
идемпотентность сабмита (form_token) против двойной отправки по F5.
"""

import uuid

from django.contrib import messages
from django.core.cache import cache
from django.shortcuts import get_object_or_404, redirect, render

from .forms import PublicReservationForm
from .models import Promotion, Reservation
from .services import OutOfStock, ReservationLimitReached, reserve

RL_LIMIT = 5  # попыток
RL_WINDOW = 600  # за 10 минут
TOKEN_TTL = 600


def _client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or ""


def storefront_home(request):
    promos = Promotion.objects.filter(status="active").order_by("-created_at")
    return render(request, "storefront/home.html", {"promotions": promos})


def promotion_detail(request, pk):
    promo = get_object_or_404(Promotion, pk=pk, status="active")
    form = PublicReservationForm(initial={"form_token": uuid.uuid4().hex})
    return render(request, "storefront/promotion_detail.html", {"promotion": promo, "form": form})


def reservation_create(request, pk):
    promo = get_object_or_404(Promotion, pk=pk, status="active")
    if request.method != "POST":
        return redirect("storefront-promotion", pk=pk)

    # honeypot — тихо игнорируем ботов (отдаём вид успеха)
    if request.POST.get("website"):
        return redirect("storefront-promotion", pk=pk)

    form = PublicReservationForm(request.POST)
    ctx = {"promotion": promo, "form": form}
    if not form.is_valid():
        return render(request, "storefront/promotion_detail.html", ctx)

    # rate-limit по IP+акции
    rl_key = f"resv_rl:{_client_ip(request)}:{pk}"
    if cache.get(rl_key, 0) >= RL_LIMIT:
        messages.error(request, "Zu viele Versuche. Bitte später erneut.")
        return render(request, "storefront/promotion_detail.html", ctx)
    cache.set(rl_key, cache.get(rl_key, 0) + 1, RL_WINDOW)

    # идемпотентность: токен «занимаем» на время попытки, на успехе оставляем,
    # на ошибке освобождаем (чтобы клиент мог повторить с другими данными)
    token = form.cleaned_data.get("form_token")
    token_key = f"resv_token:{token}" if token else None
    if token_key and not cache.add(token_key, "1", TOKEN_TTL):
        return redirect("storefront-promotion", pk=pk)  # дубль сабмита

    try:
        res = reserve(
            promo,
            name=form.cleaned_data["name"],
            email=form.cleaned_data.get("email", ""),
            phone=form.cleaned_data.get("phone", ""),
            quantity=form.cleaned_data["quantity"],
        )
    except OutOfStock:
        if token_key:
            cache.delete(token_key)
        messages.error(request, "Leider ausverkauft.")
        return render(request, "storefront/promotion_detail.html", ctx)
    except ReservationLimitReached:
        if token_key:
            cache.delete(token_key)
        messages.error(request, "Limit pro Kunde erreicht.")
        return render(request, "storefront/promotion_detail.html", ctx)

    return redirect("storefront-confirmation", code=res.reference_code)


def reservation_confirmation(request, code):
    res = get_object_or_404(Reservation.objects.select_related("promotion"), reference_code=code)
    return render(request, "storefront/confirmation.html", {"reservation": res})
