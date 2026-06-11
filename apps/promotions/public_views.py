"""Публичная витрина брони (без логина), на корне субдомена бизнеса.

Защита публичных форм: honeypot (website), rate-limit по IP (apps.core.ratelimit,
Hardening H8 — бронь/waitlist по IP+акции, QR-вьюхи по IP против перебора кодов)
и идемпотентность сабмита (form_token) против двойной отправки по F5.
"""

import io
import uuid
from urllib.parse import quote

import segno
from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.db.models import F
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.core import ratelimit
from apps.core.pagination import paginate
from apps.core.seo import offer_ld

from .forms import PublicReservationForm, WaitlistForm
from .models import Customer, LoyaltyCard, Promotion, Reservation, Voucher, WaitlistEntry
from .services import OutOfStock, ReservationLimitReached, reserve

RL_LIMIT = 5  # попыток (бронь/waitlist на IP+акцию)
RL_WINDOW = 600  # за 10 минут
QR_RL_LIMIT = 60  # QR-вьюх на IP (страница подтверждения рендерит их легитимно)
TOKEN_TTL = 600


def _qr_limited(request) -> bool:
    """Общий лимит QR-вьюх по IP — против перебора кодов броней/ваучеров/карт."""
    return ratelimit.hit("qr", ratelimit.client_ip(request), limit=QR_RL_LIMIT, window=RL_WINDOW)


def _abs_promo_url(request, pk) -> str:
    return request.build_absolute_uri(reverse("storefront-promotion", args=[pk]))


def _detail_ctx(request, promo, form) -> dict:
    img = promo.primary_image
    og_image = request.build_absolute_uri(img["url"]) if img and img.get("url") else ""
    share_url = _abs_promo_url(request, promo.pk)
    return {
        "promotion": promo,
        "form": form,
        "waitlist_form": WaitlistForm(),
        "share_url": share_url,
        "qr_url": reverse("storefront-promotion-qr", args=[promo.pk]),
        "og_image": og_image,
        "ld_offer": offer_ld(promo, url=share_url, image_url=og_image),
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
    # Превью каталога (Track C1): featured вперёд, дальше новинки.
    from apps.catalog.models import Product

    products_preview = Product.objects.filter(is_active=True).order_by(
        "-is_featured", "-created_at"
    )[:8]
    return render(
        request,
        "storefront/home.html",
        {"promotions": promos, "products_preview": products_preview},
    )


def product_list(request):
    """Публичный каталог витрины (Track C1): активные товары + фильтр категории."""
    from apps.catalog.models import Category, Product

    products = Product.objects.filter(is_active=True).order_by("-is_featured", "-created_at")
    category = None
    slug = request.GET.get("kategorie", "")
    if slug:
        category = Category.objects.filter(slug=slug, is_active=True).first()
        if category is None:
            return redirect("storefront-products")
        products = products.filter(category=category)
    categories = Category.objects.filter(is_active=True, products__is_active=True).distinct()
    page = paginate(products, order_field="created_at", limit=24, cursor=request.GET.get("cursor"))
    return render(
        request,
        "storefront/products.html",
        {
            "page": page,
            "categories": categories,
            "current_category": category,
        },
    )


def product_detail(request, pk):
    from apps.catalog.models import Product

    product = get_object_or_404(Product, pk=pk, is_active=True)
    related = (
        Product.objects.filter(is_active=True, category=product.category)
        .exclude(pk=product.pk)
        .order_by("-is_featured", "-created_at")[:4]
        if product.category_id
        else []
    )
    return render(
        request,
        "storefront/product_detail.html",
        {"product": product, "related": related},
    )


def promotion_detail(request, pk):
    promo = get_object_or_404(Promotion, pk=pk, status="active")
    ch = _capture_channel(request)
    # аналитика: атомарный счётчик просмотров (не блокирует рендер)
    Promotion.objects.filter(pk=promo.pk).update(views=F("views") + 1)
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
    if _qr_limited(request):
        return HttpResponse(status=429)
    code = code.strip().upper()
    get_object_or_404(Reservation, reference_code=code)
    redeem_url = request.build_absolute_uri(reverse("promotions:redeem-detail", args=[code]))
    buf = io.BytesIO()
    segno.make(redeem_url, error="m").save(buf, kind="svg", scale=6, border=2)
    return HttpResponse(buf.getvalue(), content_type="image/svg+xml")


def voucher_qr(request, code):
    """QR ваучера. Кодирует ссылку погашения в кабинете (сотрудник сканирует)."""
    if _qr_limited(request):
        return HttpResponse(status=429)
    code = code.strip().upper()
    get_object_or_404(Voucher, code=code)
    redeem_url = (
        request.build_absolute_uri(reverse("promotions:voucher-redeem")) + "?code=" + quote(code)
    )
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

    # rate-limit по IP+акции (атомарный, см. apps.core.ratelimit)
    rl_ident = f"{ratelimit.client_ip(request)}:{pk}"
    if ratelimit.hit("resv", rl_ident, limit=RL_LIMIT, window=RL_WINDOW):
        messages.error(request, "Zu viele Versuche. Bitte später erneut.")
        return render(request, "storefront/promotion_detail.html", ctx)

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
    rl_ident = f"{ratelimit.client_ip(request)}:{pk}"
    if ratelimit.hit("waitlist", rl_ident, limit=RL_LIMIT, window=RL_WINDOW):
        messages.error(request, "Zu viele Versuche. Bitte später erneut.")
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


def loyalty_card_qr(request, token):
    """QR карты лояльности: кодирует ссылку начисления штампа в кабинете."""
    if _qr_limited(request):
        return HttpResponse(status=429)
    card = get_object_or_404(LoyaltyCard.objects.select_related("program"), token=token)
    stamp_url = (
        request.build_absolute_uri(reverse("promotions:loyalty-stamp", args=[card.program_id]))
        + "?card="
        + str(card.token)
    )
    buf = io.BytesIO()
    segno.make(stamp_url, error="m").save(buf, kind="svg", scale=6, border=2)
    return HttpResponse(buf.getvalue(), content_type="image/svg+xml")


def sitemap_xml(request):
    """Sitemap витрины (Track B5): главная + активные акции, абсолютные URL хоста.

    Без django.contrib.sitemaps (мульти-тенант: домен берём из request, не из
    Sites). Простой и тестируемый XML.
    """
    from xml.sax.saxutils import escape

    urls = [request.build_absolute_uri(reverse("storefront-home"))]
    urls += [
        request.build_absolute_uri(reverse("storefront-promotion", args=[pk]))
        for pk in Promotion.objects.filter(status="active").values_list("pk", flat=True)
    ]
    # Каталог витрины (Track C1).
    from apps.catalog.models import Product

    product_pks = list(Product.objects.filter(is_active=True).values_list("pk", flat=True))
    if product_pks:
        urls.append(request.build_absolute_uri(reverse("storefront-products")))
        urls += [
            request.build_absolute_uri(reverse("storefront-product", args=[pk]))
            for pk in product_pks
        ]
    body = "".join(f"<url><loc>{escape(u)}</loc></url>" for u in urls)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{body}</urlset>"
    )
    return HttpResponse(xml, content_type="application/xml")


def robots_txt(request):
    """robots.txt витрины: всё открыто + ссылка на sitemap (Track B5)."""
    sitemap = request.build_absolute_uri(reverse("storefront-sitemap"))
    body = f"User-agent: *\nAllow: /\nSitemap: {sitemap}\n"
    return HttpResponse(body, content_type="text/plain")
