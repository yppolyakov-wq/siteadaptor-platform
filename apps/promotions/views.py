"""Кабинет владельца: акции (CRUD + переходы статусов) и брони (управление).

Статусы акций двигаем только через PromotionSM; брони — через services
(confirm/fulfill/cancel) поверх ReservationSM. Все вьюхи требуют логина.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.catalog.images import delete_stored_image, save_product_image
from apps.core.fsm import IllegalTransition
from apps.loyalty.models import LoyaltyCard, LoyaltyProgram, Voucher

from . import services
from .forms import LoyaltyProgramForm, PromotionForm, VoucherCreateForm
from .models import Customer, Promotion, Reservation
from .poster import build_shop_poster_pdf
from .presets import preset_initial, presets_for
from .state_machine import PromotionSM

PROMO_STATUSES = ["draft", "scheduled", "active", "paused", "ended", "archived"]
RESERVATION_STATUSES = ["pending", "confirmed", "fulfilled", "cancelled", "expired"]

_PROMOTION_INLINE_FIELDS = {"title"}


@login_required
@require_POST
def promotion_inline_edit(request):
    """Инлайн-правка АКЦИИ прямо на канве витрины (?preview=1) в редакторе.

    JSON {pk, field, value}. field == "title" → Promotion.title['de'] (пустым не
    сохраняем). field == "price_override" → новая цена акции (Decimal ≥0), затем сброс
    кэша витрины (новая цена сразу на публичной). Только владелец (login_required →
    tenant-скоуп). Строгий вайтлист (i18n-заголовок + price_override). 204/400.
    """
    import json
    from decimal import Decimal, InvalidOperation

    from django.http import HttpResponseBadRequest

    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, TypeError):
        return HttpResponseBadRequest()
    pk = data.get("pk")
    field = data.get("field")
    value = data.get("value", "")
    if not pk or field not in (_PROMOTION_INLINE_FIELDS | {"price_override"}):
        return HttpResponseBadRequest()
    try:
        promo = Promotion.objects.get(pk=pk)
    except (Promotion.DoesNotExist, ValidationError, ValueError):
        return HttpResponseBadRequest()

    if field == "price_override":
        raw = str(value).strip().replace(",", ".")
        try:
            price = Decimal(raw)
        except (InvalidOperation, ValueError):
            return HttpResponseBadRequest()
        if price < 0 or price > Decimal("1000000"):
            return HttpResponseBadRequest()
        promo.price_override = price.quantize(Decimal("0.01"))
        promo.save(update_fields=["price_override", "updated_at"])
        schema = getattr(getattr(request, "tenant", None), "schema_name", None)
        if schema:
            from apps.core.pagecache import bump_storefront_cache

            bump_storefront_cache(schema)
        return HttpResponse(status=204)

    # title → i18n['de'] (пустым не сохраняем)
    value = value.strip() if isinstance(value, str) else ""
    if not value:
        return HttpResponseBadRequest()
    i18n = dict(promo.title or {})
    i18n["de"] = value
    promo.title = i18n
    promo.save(update_fields=["title", "updated_at"])
    return HttpResponse(status=204)


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
def shop_poster_pdf(request):
    """A4-постер с QR на витрину для печати (Track B4). Кабинет — на субдомене
    бизнеса, поэтому корень витрины берём с того же хоста."""
    tenant = getattr(request, "tenant", None)
    business_name = getattr(tenant, "name", "") or "Unser Shop"
    storefront_url = request.build_absolute_uri(reverse("storefront-home"))
    pdf = build_shop_poster_pdf(business_name, storefront_url)
    resp = HttpResponse(pdf, content_type="application/pdf")
    slug = getattr(tenant, "slug", "") or "shop"
    resp["Content-Disposition"] = f'attachment; filename="schaufenster-poster-{slug}.pdf"'
    return resp


@login_required
def promotion_create(request):
    # request.tenant может отсутствовать (напр. в unit-тестах через RequestFactory),
    # поэтому достаём его защитно — пресеты просто схлопнутся к универсальным.
    tenant = getattr(request, "tenant", None)
    business_type = getattr(tenant, "business_type", "") or ""
    initial = {}
    if request.method == "GET" and request.GET.get("preset"):
        initial = preset_initial(business_type, request.GET["preset"])
    form = PromotionForm(request.POST or None, request.FILES or None, initial=initial or None)
    if request.method == "POST" and form.is_valid():
        promo = form.save()
        _handle_promo_uploads(request, promo)
        return redirect("promotions:promotion-edit", pk=promo.pk)
    return render(
        request,
        "promotions/promotion_form.html",
        {
            "form": form,
            "is_create": True,
            "nav": "promotions",
            "presets": presets_for(business_type),
        },
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
    from apps.billing import featured as billing_featured

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
            "stats": _promo_stats(promo),
            # Платное продвижение в агрегаторе (P2.4b): карточка-ссылка на странице
            # акции. Листинг есть, только пока акция active.
            "featured_listing": _featured_listing(promo),
            "featured_enabled": billing_featured.is_enabled(),
            "nav": "promotions",
        },
    )


def _featured_listing(promo):
    """Листинг агрегатора этой акции (SHARED/public) или None.

    Листинг материализуется, только пока акция active (sync_listing);
    featured_until на нём — то, что продаёт P2.4b. Ключ — (схема тенанта,
    promo_uuid). В unit-тестах без tenant-миддлвари схемы листинга нет → None.
    """
    from django.db import connection

    from apps.aggregator.models import AggregatorListing

    return AggregatorListing.objects.filter(
        tenant_schema=connection.schema_name, promo_uuid=promo.id
    ).first()


@login_required
def promotion_feature(request, pk):
    """Страница продвижения акции в агрегаторе (P2.4b): планы, цена, статус."""
    from apps.billing import featured as billing_featured

    promo = get_object_or_404(Promotion, pk=pk)
    listing = _featured_listing(promo)
    return render(
        request,
        "promotions/promotion_feature.html",
        {
            "promotion": promo,
            "listing": listing,
            "plans": billing_featured.get_plans(),
            "featured_enabled": billing_featured.is_enabled(),
            "is_listed": promo.status == "active" and listing is not None,
            "checkout_status": request.GET.get("status", ""),
            "nav": "promotions",
        },
    )


@login_required
@require_POST
def promotion_feature_checkout(request, pk):
    """Разовый Stripe-Checkout за продвижение акции → редирект на оплату (P2.4b)."""
    from apps.billing import featured as billing_featured
    from apps.billing import services as billing_services

    promo = get_object_or_404(Promotion, pk=pk)
    days_raw = request.POST.get("days", "")
    plan = billing_featured.get_plan(int(days_raw)) if days_raw.isdigit() else None
    if not billing_featured.is_enabled() or plan is None:
        messages.error(request, "Empfehlung ist derzeit nicht verfügbar.")
        return redirect("promotions:promotion-feature", pk=pk)
    if promo.status != "active":
        messages.error(request, "Nur aktive Aktionen können beworben werden.")
        return redirect("promotions:promotion-feature", pk=pk)

    # Гарантируем листинг к моменту оплаты (синк мог не успеть отработать);
    # featured_until при ресинке сохраняется (P2.4a).
    from django.db import connection

    from apps.aggregator.tasks import sync_listing

    sync_listing(connection.schema_name, str(promo.id))

    base = request.build_absolute_uri(reverse("promotions:promotion-feature", args=[promo.pk]))
    url = billing_services.create_featured_checkout_session(
        request.tenant,
        promo_uuid=str(promo.id),
        days=plan.days,
        title=promo.get_i18n("title") or "Aktion",
        success_url=f"{base}?status=success",
        cancel_url=f"{base}?status=cancel",
    )
    return redirect(url)


def _conversion(n_res, views):
    return round(n_res / views * 100, 1) if views else None


def _promo_stats(promo) -> dict:
    """Аналитика акции: просмотры, брони по статусам, конверсия, выдачи."""
    by_status = dict(promo.reservations.values_list("status").annotate(n=Count("id")).order_by())
    total = sum(by_status.values())
    return {
        "views": promo.views,
        "by_status": by_status,
        "total": total,
        "fulfilled": by_status.get("fulfilled", 0),
        "conversion": _conversion(total, promo.views),
    }


@login_required
def analytics_overview(request):
    promos = Promotion.objects.annotate(
        n_res=Count("reservations"),
        n_fulfilled=Count("reservations", filter=Q(reservations__status="fulfilled")),
    ).order_by("-views")
    rows = [
        {
            "promo": p,
            "views": p.views,
            "n_res": p.n_res,
            "n_fulfilled": p.n_fulfilled,
            "conversion": _conversion(p.n_res, p.views),
        }
        for p in promos
    ]
    return render(request, "promotions/analytics.html", {"rows": rows, "nav": "analytics"})


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
        d_eur = form.cleaned_data.get("discount_eur")
        min_eur = form.cleaned_data.get("min_order_eur")
        created = services.generate_vouchers(
            label=form.cleaned_data["label"],
            count=form.cleaned_data["count"],
            max_uses=form.cleaned_data["max_uses"],
            expires_at=form.cleaned_data.get("expires_at"),
            discount_percent=form.cleaned_data.get("discount_percent"),
            discount_cents=int(d_eur * 100) if d_eur else None,
            min_order_cents=int(min_eur * 100) if min_eur else 0,
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


@login_required
def newsletter_campaigns(request):
    """G3: рассылки гостям — список кампаний + создание/отправка. Отправляем только
    подтвердившим opt-in (UWG §7)."""
    from .models import NewsletterCampaign
    from .newsletter import consented_customers

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create":
            subject = (request.POST.get("subject") or "").strip()[:200]
            body = (request.POST.get("body") or "").strip()
            if subject and body:
                NewsletterCampaign.objects.create(subject=subject, body=body)
                messages.success(request, "Entwurf gespeichert.")
            else:
                messages.error(request, "Bitte Betreff und Text eingeben.")
        elif action == "send":
            from .newsletter import send_campaign

            campaign = get_object_or_404(NewsletterCampaign, pk=request.POST.get("campaign"))
            n = send_campaign(campaign, base_url=request.build_absolute_uri("/").rstrip("/"))
            messages.success(request, f"Newsletter an {n} Empfänger gesendet.")
        elif action == "delete":
            NewsletterCampaign.objects.filter(
                pk=request.POST.get("campaign"), status=NewsletterCampaign.STATUS_DRAFT
            ).delete()
        return redirect("promotions:newsletter")

    return render(
        request,
        "promotions/newsletter.html",
        {
            "nav": "promotions",
            "campaigns": list(NewsletterCampaign.objects.all()[:100]),
            "consented": consented_customers().count(),
        },
    )
