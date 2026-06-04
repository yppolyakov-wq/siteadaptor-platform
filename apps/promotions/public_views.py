"""Публичная витрина брони (без логина), на корне субдомена бизнеса.

Защита публичной формы: honeypot (website), rate-limit по IP+акции и
идемпотентность сабмита (form_token) против двойной отправки по F5.
"""

import io
import uuid
from urllib.parse import quote

import segno
from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import PublicReservationForm, WaitlistForm
from .models import Customer, Promotion, Reservation, WaitlistEntry
from .services import OutOfStock, ReservationLimitReached, reserve

RL_LIMIT = 5  # попыток
RL_WINDOW = 600  # за 10 минут
TOKEN_TTL = 600


def _client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or ""


def _abs_promo_url(request, pk) -> str:
    return request.build_absolute_uri(reverse("storefront-promotion", args=[pk]))


def _detail_ctx(request, promo, form) -> dict:
    img = promo.primary_image
    og_image = request.build_absolute_uri(img["url"]) if img and img.get("url") else ""
    return {
        "promotion": promo,
        "form": form,
        "waitlist_form": WaitlistForm(),
        "share_url": _abs_promo_url(request, promo.pk),
        "qr_url": reverse("storefront-promotion-qr", args=[promo.pk]),
        "og_image": og_image,
    }


def _capture_channel(request) -> str:
    """Канал из ?ch= запоминаем в сессии, чтобы донести до момента брони."""
    ch = (request.GET.get("ch") or "").strip()[:50]
    if ch:
        request.session["src_ch"] = ch
    return ch or request.session.get("src_ch", "")


def storefront_home(request):
    _capture_channel(request)
    promos = Promotion.objects.filter(status="active").order_by("-created_at")
    return render(request, "storefront/home.html", {"promotions": promos})


def promotion_detail(request, pk):
    promo = get_object_or_404(Promotion, pk=pk, status="active")
    ch = _capture_channel(request)
    form = PublicReservationForm(initial={"form_token": uuid.uuid4().hex, "channel": ch})
    return render(request, "storefront/promotion_detail.html", _detail_ctx(request, promo, form))


def set_language(request):
    """Переключатель языка витрины: ставит cookie, LocaleMiddleware подхватит."""
    lang = request.GET.get("lang", settings.LANGUAGE_CODE)
    if lang not in dict(settings.LANGUAGES):
        lang = settings.LANGUAGE_CODE
    resp = redirect(request.GET.get("next") or reverse("storefront-home"))
    resp.set_cookie(settings.LANGUAGE_COOKIE_NAME, lang, max_age=60 * 60 * 24 * 365)
    return resp


def promotion_qr(request, pk):
    """SVG QR акции. С ?ch=<канал> кодирует ссылку с меткой источника
    (instagram/flyer/schaufenster…) — для печати на каждый канал свой QR."""
    promo = get_object_or_404(Promotion, pk=pk, status="active")
    url = _abs_promo_url(request, promo.pk)
    ch = (request.GET.get("ch") or "").strip()
    if ch:
        url += ("&" if "?" in url else "?") + "ch=" + quote(ch)
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="svg", scale=6, border=2)
    return HttpResponse(buf.getvalue(), content_type="image/svg+xml")


def reservation_qr(request, code):
    """Персональный QR брони. Кодирует ссылку погашения в кабинете —
    сотрудник сканирует штатной камерой и попадает на страницу выдачи."""
    code = code.strip().upper()
    get_object_or_404(Reservation, reference_code=code)
    redeem_url = request.build_absolute_uri(reverse("promotions:redeem-detail", args=[code]))
    buf = io.BytesIO()
    segno.make(redeem_url, error="m").save(buf, kind="svg", scale=6, border=2)
    return HttpResponse(buf.getvalue(), content_type="image/svg+xml")


def reservation_create(request, pk):
    promo = get_object_or_404(Promotion, pk=pk, status="active")
    if request.method != "POST":
        return redirect("storefront-promotion", pk=pk)

    # honeypot — тихо игнорируем ботов (отдаём вид успеха)
    if request.POST.get("website"):
        return redirect("storefront-promotion", pk=pk)

    form = PublicReservationForm(request.POST)
    ctx = _detail_ctx(request, promo, form)
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

    channel = (form.cleaned_data.get("channel") or request.session.get("src_ch") or "").strip()
    try:
        res = reserve(
            promo,
            name=form.cleaned_data["name"],
            email=form.cleaned_data.get("email", ""),
            phone=form.cleaned_data.get("phone", ""),
            quantity=form.cleaned_data["quantity"],
            source_channel=channel,
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


def waitlist_join(request, pk):
    """Записать в лист ожидания распроданной акции."""
    promo = get_object_or_404(Promotion, pk=pk, status="active")
    if request.method != "POST" or request.POST.get("website"):
        return redirect("storefront-promotion", pk=pk)
    form = WaitlistForm(request.POST)
    if form.is_valid():
        WaitlistEntry.objects.get_or_create(
            promotion=promo,
            email=form.cleaned_data["email"].lower(),
            defaults={"name": form.cleaned_data.get("name", "")},
        )
        messages.success(request, "Wir benachrichtigen Sie, sobald wieder verfügbar.")
    else:
        messages.error(request, "Bitte eine gültige E-Mail angeben.")
    return redirect("storefront-promotion", pk=pk)


def reservation_confirmation(request, code):
    res = get_object_or_404(Reservation.objects.select_related("promotion"), reference_code=code)
    return render(request, "storefront/confirmation.html", {"reservation": res})


def unsubscribe(request, token):
    """Быстрая отписка от писем по токену (one-click, GET и POST)."""
    customer = Customer.objects.filter(unsubscribe_token=token).first()
    if customer is not None and not customer.unsubscribed:
        customer.unsubscribed = True
        customer.save(update_fields=["unsubscribed", "updated_at"])
    return render(request, "storefront/unsubscribed.html", {"ok": customer is not None})


def _legal_page(request, title, body):
    return render(request, "storefront/legal.html", {"legal_title": title, "legal_body": body})


def impressum(request):
    return _legal_page(request, "Impressum", request.tenant.impressum_text())


def privacy(request):
    return _legal_page(request, "Datenschutz", request.tenant.privacy_text())


def withdrawal(request):
    return _legal_page(request, "Widerruf", request.tenant.withdrawal_text())
