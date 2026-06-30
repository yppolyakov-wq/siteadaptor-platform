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
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext as _
from django.views.decorators.clickjacking import xframe_options_sameorigin

from apps.core import ratelimit
from apps.core.pagecache import cache_storefront_page
from apps.core.pagination import paginate
from apps.core.seo import offer_ld
from apps.loyalty.models import LoyaltyCard, LoyaltyProgram, Voucher

from .forms import PublicReservationForm, WaitlistForm
from .models import (
    Customer,
    Promotion,
    Reservation,
    WaitlistEntry,
)
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


# Same-origin framing разрешён: кабинет владельца (тот же субдомен-origin)
# показывает витрину в iframe (live-preview конструктора + страница Preview).
# Прод ставит X-Frame-Options: DENY глобально — это бы блокировало iframe.
@xframe_options_sameorigin
@cache_storefront_page
def storefront_home(request):
    _capture_channel(request)
    # Конструктор витрины v1 (Track C2): главная собирается из секций конфига.
    from apps.tenants import siteconfig

    # V1 live-preview: при ?preview=1 и черновике в сессии (из конструктора
    # главной) рендерим несохранённое состояние. Только для вошедшего владельца
    # (черновик в его сессии); standalone-редирект в превью пропускаем.
    preview = request.GET.get("preview") == "1"
    raw = request.tenant.site_config
    if preview and isinstance(request.session.get("site_preview_draft"), dict):
        raw = request.session["site_preview_draft"]
    site = siteconfig.normalize(raw)
    # S4: standalone-режим — корень `/` ведёт на лендинг выбранного архетипа
    # (если он активен и имеет публичную страницу), иначе обычная главная.
    root = site.get("storefront_root", "home")
    if root and root != "home" and not preview:
        from apps.core import modules

        spec = modules.get_module(root)
        if spec and spec.storefront_landing and modules.is_module_active(request.tenant, root):
            try:
                return redirect(reverse(spec.storefront_landing))
            except NoReverseMatch:
                pass
    # H2 (мультиархетип-дефолт главной): если владелец НЕ настраивал композицию (в сыром
    # конфиге нет "sections"), включаем «главный» блок КАЖДОГО активного архетипа в его
    # естественной позиции (магазин+ретриты+услуги → products+events+services …). Рендер
    # гейтится модулем+данными → пустых секций не появится. Если "sections" заданы — НЕ
    # трогаем (не переписываем интент владельца). Обобщает прежний M20U-2 (одна primary →
    # все): products/promotions включены по умолчанию (enable идемпотентен), events/
    # stay_rooms/services — добавляются для активных архетипов.
    if not (isinstance(raw, dict) and raw.get("sections")):
        from apps.core import archetypes

        want = {a["key"] for a in archetypes.aggregate_primary_sections(request.tenant)}
        for s in site["sections"]:
            if s["key"] in want:
                s["enabled"] = True
    # Двуязычная витрина (i18n): свернуть тексты site_config к текущей локали —
    # EN-оверлей поверх базовых DE-значений. Платформенный механизм; переводы
    # сидятся демо-китом. DE/без оверлея → базовые значения (без изменений).
    from django.utils.translation import get_language

    site = siteconfig.localize(site, get_language())
    sections = [s["key"] for s in site["sections"] if s["enabled"]]
    # D.2: полные записи включённых секций (фикс + C-блоки с данными) для рендера
    # через {% render_block %}; `sections` (ключи) остаётся для гейтинга запросов.
    section_blocks = [s for s in site["sections"] if s["enabled"]]

    promos = (
        Promotion.objects.filter(status="active").order_by("-created_at")
        if "promotions" in sections
        else Promotion.objects.none()
    )
    products_preview = []
    if "products" in sections:
        from apps.catalog.models import Product

        # M20U-7: источник товаров секции (избранные/новые/избранные-первыми).
        prod_qs = Product.objects.filter(is_active=True)
        source = siteconfig.product_source(site)
        if source == "featured_only":
            prod_qs = prod_qs.filter(is_featured=True).order_by("-created_at")
        elif source == "newest":
            prod_qs = prod_qs.order_by("-created_at")
        else:  # featured_first
            prod_qs = prod_qs.order_by("-is_featured", "-created_at")
        products_preview = prod_qs[: siteconfig.section_limit(site, "products")]
    # M20U-2: сетка категорий каталога (верхний уровень, активные).
    categories = []
    if "categories" in sections:
        from apps.catalog.models import Category

        categories = list(
            Category.objects.filter(is_active=True, parent__isnull=True).order_by(
                "sort_order", "slug"
            )
        )
    # S2: сетка тизеров активных архетипов («Наши разделы»).
    archetype_teasers = []
    if "archetypes" in sections:
        from apps.tenants import storefront

        archetype_teasers = storefront.archetype_teasers(request.tenant)
    # Карточки номеров на главной (только при активном модуле stays).
    from apps.core import modules

    stay_rooms = []
    if "stay_rooms" in sections and modules.is_module_active(request.tenant, "stays"):
        from apps.stays.models import StayUnit

        stay_rooms = list(StayUnit.objects.filter(is_active=True))
    # M20U-2: ближайшие мероприятия/ретриты (primary items архетипа events).
    events_preview = []
    if "events" in sections and modules.is_module_active(request.tenant, "events"):
        from django.utils import timezone

        from apps.events.models import Event

        events_preview = list(
            Event.objects.filter(
                status=Event.STATUS_PUBLISHED, starts_at__gte=timezone.now()
            ).order_by("starts_at")[: siteconfig.section_limit(site, "events")]
        )
    # A3: блок «Leistungen & Preise» — услуги (Service) при активном модуле booking.
    services_preview = []
    if "services" in sections and modules.is_module_active(request.tenant, "booking"):
        from apps.booking.models import Service

        services_preview = list(Service.objects.filter(is_active=True))
    # A9/A7: у ремесла/автосервиса (активен модуль jobs — Angebot/Kostenvoranschlag)
    # услуги с ценой подаём как Festpreis — сигнал доверия (прозрачные фикс-цены).
    services_festpreis = modules.is_module_active(request.tenant, "jobs")
    # M20U-5: «главный товар» архетипа — для CTA hero-баннера (ведёт на лендинг
    # primary item: магазин → товары, ретрит → события, отель → номера…).
    from apps.core import archetypes

    primary_item = archetypes.primary_item(request.tenant)
    return render(
        request,
        "storefront/home.html",
        {
            "sections": sections,
            "section_blocks": section_blocks,
            "site": site,
            "promotions": promos,
            "products_preview": products_preview,
            "categories": categories,
            "archetype_teasers": archetype_teasers,
            "stay_rooms": stay_rooms,
            "events_preview": events_preview,
            "services_preview": services_preview,
            "services_festpreis": services_festpreis,
            "primary_item": primary_item,
        },
    )


def promotion_list(request):
    """Публичный список акций /aktionen/ (S6) с фильтром по группе/направлению."""
    from apps.core import modules

    if not modules.is_module_active(request.tenant, "promotions"):
        raise Http404
    qs = Promotion.objects.filter(status="active").order_by("-created_at")
    groups = sorted({g for g in qs.values_list("group", flat=True) if g})
    selected = (request.GET.get("gruppe") or "").strip()
    if selected:
        qs = qs.filter(group=selected)
    return render(
        request,
        "storefront/promotions_list.html",
        {"promotions": qs, "groups": groups, "selected_group": selected},
    )


def about_page(request):
    """Отдельная страница «О компании» /ueber-uns/ (S8): тексты about + контакты."""
    from django.utils.translation import get_language

    from apps.tenants import siteconfig

    site = siteconfig.localize(siteconfig.normalize(request.tenant.site_config), get_language())
    return render(request, "storefront/about.html", {"site": site, "sections": []})


def loyalty_page(request):
    """Публичная страница программы лояльности /treue/ (S5).

    Описывает активные штамп-карты и приглашает завести аккаунт (если включён
    модуль customer_account) для сбора штампов. Гейтинг модуля loyalty → 404.
    """
    from apps.core import modules

    if not modules.is_module_active(request.tenant, "loyalty"):
        raise Http404
    programs = LoyaltyProgram.objects.filter(is_active=True).order_by("label")
    return render(
        request,
        "storefront/loyalty.html",
        {
            "programs": programs,
            "account_enabled": modules.is_module_active(request.tenant, "customer_account"),
        },
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
    # A4: фасет-фильтр по диете (vegan/vegetarisch/…) — JSON contains код. Показываем
    # чипы только тех диет, что реально встречаются среди активных товаров.
    from apps.catalog import food

    diet = request.GET.get("diet", "")
    diet = diet if diet in food.VALID_DIETS else ""
    if diet:
        products = products.filter(diets__contains=[diet])
    present_diets = set()
    for vals in Product.objects.filter(is_active=True).values_list("diets", flat=True):
        present_diets.update(v for v in (vals or []) if v in food.VALID_DIETS)
    diet_chips = [
        {"code": c, "label": label, "icon": icon}
        for c, label, icon in food.DIETS
        if c in present_diets
    ]
    categories = Category.objects.filter(is_active=True, products__is_active=True).distinct()
    # M20U-3: подкатегории выбранной категории — выводим карточками первыми.
    subcategories = (
        list(category.children.filter(is_active=True).order_by("sort_order", "slug"))
        if category is not None
        else []
    )
    page = paginate(products, order_field="created_at", limit=24, cursor=request.GET.get("cursor"))
    # A4: комбо-наборы (Menü-Sets/Tagesgericht), если есть и модуль orders активен.
    # M20U/A4: показываем тизер-карточками вверху меню (до 3) — не только текст-ссылкой,
    # — чтобы Kombo/Tagesgericht были на виду (сильный апселл гастро). Только на 1-й
    # странице каталога без выбранной категории (чтобы не дублировать при пагинации/фильтре).
    from apps.catalog.combos import active_combos

    has_combos = request.tenant.is_module_active("orders") and active_combos().exists()
    combos_teaser = (
        list(active_combos()[:3])
        if has_combos and category is None and not request.GET.get("cursor")
        else []
    )
    # M20U-7 (per-page): раскладка сетки каталога из конфига витрины.
    # SE-2a-2: при ?preview=1 берём черновик из сессии (как storefront_home) —
    # чтобы on-canvas правка раскладки каталога была видна сразу.
    from apps.tenants import siteconfig

    is_preview = request.GET.get("preview") == "1"
    raw_cfg = request.tenant.site_config
    if is_preview and isinstance(request.session.get("site_preview_draft"), dict):
        raw_cfg = request.session["site_preview_draft"]
    cfg = siteconfig.normalize(raw_cfg)
    catalog_grid = siteconfig.grid_class_string(cfg["catalog_layout"])
    return render(
        request,
        "storefront/products.html",
        {
            "page": page,
            "categories": categories,
            "current_category": category,
            # H1.2: кастомные заголовок/интро страницы каталога (инлайн-правка на канве).
            "catalog_title": cfg.get("catalog_title", ""),
            "catalog_intro": cfg.get("catalog_intro", ""),
            "subcategories": subcategories,
            "has_combos": has_combos,
            "combos_teaser": combos_teaser,  # A4: тизер-карточки Kombo/Tagesgericht
            "diet_chips": diet_chips,  # A4: фасет-чипы диет (только встречающиеся)
            "active_diet": diet,
            "catalog_grid": catalog_grid,
            # SE-2c-2: в режиме редактора (?preview=1) на чипах категорий — ссылка
            # «✎» на полную правку категории в кабинете (имя/slug/родитель/иконка).
            "is_preview": is_preview,
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
    from apps.tenants import siteconfig

    related_grid = siteconfig.grid_class_string(
        siteconfig.normalize(request.tenant.site_config)["detail_related_layout"]
    )
    from apps.catalog import reviews as product_reviews

    return render(
        request,
        "storefront/product_detail.html",
        {
            "product": product,
            "related": related,
            "related_grid": related_grid,
            # Кнопка «Zur Abholung bestellen» (D2a) — только при активном модуле.
            "orders_enabled": request.tenant.is_module_active("orders"),
            # A1/A2: отзывы о товаре (только верифицированные покупатели).
            "reviews": list(product_reviews.published_for(product)),
            "review_summary": product_reviews.summary(product),
            "review_form_token": uuid.uuid4().hex,
        },
    )


def product_review_submit(request, pk):
    """A1/A2: приём отзыва о товаре. Только верифицированный покупатель (есть заказ
    с этим товаром по email). Один отзыв на (товар, email) — повтор обновляет."""
    from apps.catalog import reviews as product_reviews
    from apps.catalog.models import Product, ProductReview

    product = get_object_or_404(Product, pk=pk, is_active=True)
    detail_url = reverse("storefront-product", args=[product.pk])
    if request.method != "POST":
        return redirect(detail_url)
    # Рейтлимит на отправку (анти-спам), как в публичных формах акций/заявок.
    if ratelimit.hit("product_review", ratelimit.client_ip(request), limit=10, window=3600):
        messages.error(request, _("Zu viele Versuche. Bitte später erneut."))
        return redirect(detail_url)
    name = (request.POST.get("author_name") or "").strip()[:120]
    email = (request.POST.get("email") or "").strip()
    comment = (request.POST.get("comment") or "").strip()
    try:
        rating = int(request.POST.get("rating") or 0)
    except (TypeError, ValueError):
        rating = 0
    if not (name and email and 1 <= rating <= 5):
        messages.error(request, _("Bitte Name, E-Mail und Bewertung (1–5) angeben."))
        return redirect(detail_url)
    if not product_reviews.has_purchased(product, email):
        messages.error(
            request,
            _(
                "Nur verifizierte Käufer können bewerten — wir haben keine Bestellung mit dieser E-Mail gefunden."
            ),
        )
        return redirect(detail_url)
    ProductReview.objects.update_or_create(
        product=product,
        email=email.lower(),
        defaults={"rating": rating, "author_name": name, "comment": comment, "is_published": True},
    )
    messages.success(request, _("Danke für Ihre Bewertung!"))
    return redirect(detail_url + "#bewertungen")


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


def newsletter_signup(request):
    """G3: подписка на рассылку с Double-Opt-In (UWG §7). POST — создаём/находим
    клиента по e-mail и шлём письмо подтверждения; согласие ставит только
    переход по ссылке из письма."""
    from . import newsletter

    state = "form"
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        name = (request.POST.get("name") or "").strip()
        if "@" not in email:
            return render(request, "storefront/newsletter.html", {"state": "error"})
        customer = Customer.objects.filter(email__iexact=email).order_by("created_at").first()
        if customer is None:
            customer = Customer.objects.create(
                name=name, email=email, created_source=Customer.SOURCE_MANUAL
            )
        if customer.marketing_opt_in and not customer.unsubscribed:
            state = "already"
        else:
            newsletter.send_doi_email(
                customer, base_url=request.build_absolute_uri("/").rstrip("/")
            )
            state = "sent"
    return render(request, "storefront/newsletter.html", {"state": state})


def newsletter_confirm(request, token):
    """G3: подтверждение Double-Opt-In по подписанной ссылке из письма."""
    from . import newsletter

    customer = newsletter.load_doi_token(token)
    if customer is not None:
        newsletter.confirm_opt_in(customer)
    return render(
        request, "storefront/newsletter.html", {"state": "confirmed" if customer else "error"}
    )


def _legal_page(request, title, body):
    return render(request, "storefront/legal.html", {"legal_title": title, "legal_body": body})


def impressum(request):
    return _legal_page(request, "Impressum", request.tenant.impressum_text())


def privacy(request):
    return _legal_page(request, "Datenschutz", request.tenant.privacy_text())


def withdrawal(request):
    # C.1: для дистанционной продажи товаров показываем кнопку онлайн-Widerruf.
    return render(
        request,
        "storefront/legal.html",
        {
            "legal_title": "Widerruf",
            "legal_body": request.tenant.withdrawal_text(),
            "show_widerruf_button": bool(getattr(request.tenant, "delivery_enabled", False)),
        },
    )


def withdrawal_form(request):
    """C.1: онлайн-форма Widerruf (§ 312k BGB) — заявление уходит продавцу.

    Доступна всегда (право на отзыв нельзя «спрятать»). honeypot + rate-limit.
    Заявление и копию показываем клиенту; продавцу — письмом (+ inbox-тред, если
    модуль активен), чтобы Widerruf был зафиксирован независимо от настроек.
    """
    tenant = request.tenant
    fields = ("name", "email", "address", "goods", "ordered_at", "order_code")
    if request.method == "POST":
        if request.POST.get("website"):  # honeypot
            return redirect("storefront-withdrawal-form")
        if ratelimit.hit("widerruf", ratelimit.client_ip(request), limit=5, window=600):
            return HttpResponse(status=429)
        data = {k: request.POST.get(k, "").strip()[:500] for k in fields}
        if not (data["name"] and data["goods"]):
            messages.error(request, _("Please enter your name and the goods."))
            return render(request, "storefront/withdrawal_form.html", {"data": data})
        _deliver_withdrawal(request, tenant, data)
        return render(request, "storefront/withdrawal_form.html", {"sent": True, "data": data})
    return render(request, "storefront/withdrawal_form.html", {"data": {}})


def _deliver_withdrawal(request, tenant, data):
    """Доставить заявление о Widerruf продавцу: inbox-тред (если активен) + email."""
    decl = (
        "Widerruf eines Kaufvertrags\n\n"
        f"Hiermit widerrufe ich den Vertrag über den Kauf folgender Waren:\n{data['goods']}\n\n"
        f"Bestellnummer: {data['order_code'] or '—'}\n"
        f"Bestellt/erhalten am: {data['ordered_at'] or '—'}\n"
        f"Name: {data['name']}\n"
        f"E-Mail: {data['email'] or '—'}\n"
        f"Anschrift: {data['address'] or '—'}\n"
    )
    # 1) inbox-тред (бизнес видит в кабинете), если модуль активен.
    if tenant.is_module_active("inbox"):
        try:
            from apps.inbox import services as inbox_services

            inbox_services.start_conversation(
                subject="Widerruf",
                body=decl[:5000],
                name=data["name"],
                email=data["email"],
                phone="",
            )
        except Exception:
            pass
    # 2) письмо продавцу (фиксирует Widerruf независимо от inbox).
    to = tenant.public_email or tenant.contact_email
    if to:
        try:
            from django.core.mail import send_mail

            send_mail(
                f"Widerruf — {tenant.name}",
                decl,
                getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com"),
                [to],
                fail_silently=True,
            )
        except Exception:
            pass


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


def product_feed_xml(request):
    """Product-feed (M23b): Google Merchant / Meta Commerce RSS по активным товарам.

    Публичный URL на субдомене бизнеса; площадки тянут по расписанию. Домен —
    из request (мульти-тенант). Без фото/идентификатора товар всё равно в фиде.
    """
    from apps.catalog.feed import build_google_feed
    from apps.catalog.models import Product

    products = (
        Product.objects.filter(is_active=True).prefetch_related("variants").order_by("-created_at")
    )
    tenant = getattr(request, "tenant", None)
    name = getattr(tenant, "name", "") or "Shop"
    xml = build_google_feed(
        products=products,
        title=name,
        link=request.build_absolute_uri(reverse("storefront-home")),
        description=_("Products from %(name)s") % {"name": name},
        product_url=lambda p: request.build_absolute_uri(
            reverse("storefront-product", args=[p.pk])
        ),
        absolutize=request.build_absolute_uri,
    )
    return HttpResponse(xml, content_type="application/xml")
