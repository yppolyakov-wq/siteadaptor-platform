"""Публичная date-range-бронь на витрине (Track E / E3+E4): /unterkunft/.

Флоу без JS: список юнитов → юнит (выбор Anreise/Abreise/Gäste через GET-форму,
показ доступности + цены) → POST buchen (honeypot + rate-limit по IP, диапазон
ре-валидируется, гонку закрывает services.book_stay) → подтверждение /s/<code>/.
Модуль stays выключен → 404. Депозит (E4): при заданном депозите и подключённом
Stripe Connect ведём на оплату, иначе обычная бронь.
"""

from datetime import date, timedelta

import stripe
from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.billing import connect
from apps.core import ratelimit

from . import availability, payments, pricing, services
from .models import RatePlan, StayBooking, StayUnit

RL_LIMIT = 5  # попыток брони на IP
RL_WINDOW = 600  # за 10 минут
MAX_DAYS_AHEAD = 365  # горизонт заезда


def _require_stays_active(request):
    tenant = getattr(request, "tenant", None)
    if tenant is None or not tenant.is_module_active("stays"):
        raise Http404


def _parse_date(raw):
    try:
        return date.fromisoformat(raw or "")
    except (TypeError, ValueError):
        return None


def _parse_guests(params):
    """(adults, children) из GET/POST (H5). Поля erw/kinder; фолбэк на legacy
    `gaeste` (= adults, 0 детей) — диплинки H2 продолжают работать."""

    def _i(key, default):
        try:
            return max(0, min(int(params.get(key, "")), 50))
        except (TypeError, ValueError):
            return default

    if params.get("erw") is not None or params.get("kinder") is not None:
        return max(1, _i("erw", 2)), _i("kinder", 0)
    return max(1, _i("gaeste", 2)), 0


def _parse_rooms(params, unit):
    """G5: число номеров из GET/POST, ограничено 1..quantity юнита."""
    try:
        n = int(params.get("rooms", "1"))
    except (TypeError, ValueError):
        n = 1
    return max(1, min(n, unit.quantity))


def _quote(unit, von, bis, guests, rooms=1):
    """(nights, total_cents, available, reason) для диапазона. G5: rooms номеров —
    вместимость × rooms, занятость needed=rooms, проживание × rooms."""
    nights = (bis - von).days
    if nights < unit.min_nights:
        return nights, 0, False, "min_nights"
    if guests > unit.max_guests * rooms:
        return nights, 0, False, "guests"
    if not availability.range_available(unit, von, bis, needed=rooms):
        return nights, 0, False, "unavailable"
    return nights, pricing.quote_total_cents(unit, von, bis) * rooms, True, None


def _unit_from_price_cents(unit, von, bis, rate_plans):
    """Минимальная цена за диапазон (H2): дешевейший тариф, иначе база (H1).
    G4: применяем авто-скидку (LOS/Frühbucher/Last-Minute), чтобы «ab … €» в поиске
    отражала реальную к оплате цену проживания."""
    from . import pricing

    if rate_plans:
        room = min(pricing.quote_total_cents(unit, von, bis, rate_plan=rp) for rp in rate_plans)
    else:
        room = pricing.quote_total_cents(unit, von, bis)
    auto_cents, _label = pricing.auto_discount(room, (bis - von).days, von)
    return room - auto_cents


def _is_embed(request):
    return request.GET.get("embed") == "1" or request.POST.get("embed") == "1"


def _render_embed(request, template, ctx, embed):
    """G10: render витрины брони с минимальным шаблоном и разрешением кадрирования
    при ?embed=1 (для iframe на чужом сайте). Иначе — обычная витрина."""
    ctx = {
        **ctx,
        "embed": embed,
        "embed_qs": "&embed=1" if embed else "",
        "base_template": "storefront/_embed_base.html" if embed else "storefront/_base.html",
    }
    resp = render(request, template, ctx)
    if embed:
        resp.xframe_options_exempt = True  # XFrameOptionsMiddleware пропустит этот ответ
    return resp


def unterkunft_index(request):
    _require_stays_active(request)
    units = list(StayUnit.objects.filter(is_active=True))
    today = timezone.localdate()
    von = _parse_date(request.GET.get("von"))
    bis = _parse_date(request.GET.get("bis"))
    adults, children = _parse_guests(request.GET)
    guests = adults + children

    tenant = getattr(request, "tenant", None)
    embed = _is_embed(request)
    searched = bool(von and bis and von >= today and bis > von)
    # Один юнит без поиска — сразу на его страницу (как было); с датами — прокинем их.
    if len(units) == 1 and not searched:
        url = reverse("storefront-unterkunft-unit", args=[units[0].pk])
        return redirect(f"{url}?embed=1" if embed else url)

    results = None
    if searched:
        rate_plans = list(RatePlan.objects.filter(is_active=True))
        nights = (bis - von).days
        rows = []
        for unit in units:
            _nights_q, _total_cents, available, reason = _quote(unit, von, bis, guests)
            from_cents = _unit_from_price_cents(unit, von, bis, rate_plans) if available else 0
            rows.append(
                {
                    "unit": unit,
                    "available": available,
                    "reason": reason,
                    "from_eur": from_cents / 100,
                    "nights": nights,
                }
            )
        # Доступные — вперёд (UX); внутри — дешевле сверху.
        rows.sort(key=lambda r: (not r["available"], r["from_eur"]))
        results = rows

    # M20U-7 (per-page): раскладка сетки номеров из конфига витрины.
    from apps.tenants import siteconfig

    # SE-2b-1: при ?preview=1 берём черновик из сессии (on-canvas правка раскладки).
    _raw = getattr(tenant, "site_config", {}) or {}
    if request.GET.get("preview") == "1" and isinstance(
        request.session.get("site_preview_draft"), dict
    ):
        _raw = request.session["site_preview_draft"]
    rooms_grid = siteconfig.grid_class_string(siteconfig.normalize(_raw)["stay_index_layout"])
    return _render_embed(
        request,
        "storefront/stay_index.html",
        {
            "units": units,
            "today": today,
            "max_date": today + timedelta(days=MAX_DAYS_AHEAD),
            "von": von,
            "bis": bis,
            "adults": adults,
            "children": children,
            "searched": searched,
            "results": results,
            "rooms_grid": rooms_grid,
            "gift_active": getattr(tenant, "payments_enabled", False)
            and connect.is_connect_configured(),  # G1 ссылка на гутшайны
        },
        embed,
    )


def unterkunft_unit(request, pk):
    _require_stays_active(request)
    unit = get_object_or_404(StayUnit, pk=pk, is_active=True)
    today = timezone.localdate()
    von = _parse_date(request.GET.get("von"))
    bis = _parse_date(request.GET.get("bis"))
    adults, children = _parse_guests(request.GET)
    guests = adults + children
    rooms = _parse_rooms(request.GET, unit)  # G5: число номеров

    rate_plans = list(RatePlan.objects.filter(is_active=True))
    quote = None
    rate_options = []
    kurtaxe_eur = 0
    if von and bis and von >= today and bis > von:
        nights, total_cents, available, reason = _quote(unit, von, bis, guests, rooms)
        # H9: Kurtaxe (adults × ночи × ставка) — поверх проживания, в итог брони.
        kurtaxe_cents = pricing.kurtaxe_total_cents(adults, nights) if available else 0
        kurtaxe_eur = kurtaxe_cents / 100
        # G4: авто-скидка на проживание (без тарифа) — для показа итога без тарифов.
        auto_cents, auto_label = (
            pricing.auto_discount(total_cents, nights, von) if available else (0, "")
        )
        quote = {
            "von": von,
            "bis": bis,
            "guests": guests,
            "nights": nights,
            "total_eur": (total_cents - auto_cents + kurtaxe_cents) / 100,
            "auto_discount_eur": auto_cents / 100,
            "auto_discount_label": auto_label,
            # PAngV: разбивка цены — подытог проживания + базовая ставка за ночь
            # (за номер), чтобы показать «X € × N Nächte» рядом с Gesamtpreis.
            "accommodation_eur": total_cents / 100,
            "nightly_eur": (total_cents / nights / rooms / 100) if nights and rooms else 0,
            "available": available,
            "reason": reason,
        }
        if available and rate_plans:
            for rp in rate_plans:
                rp_cents = pricing.quote_total_cents(unit, von, bis, rate_plan=rp) * rooms  # G5
                rp_auto, rp_label = pricing.auto_discount(rp_cents, nights, von)
                rp_total_cents = rp_cents - rp_auto + kurtaxe_cents
                rp_prepay = pricing.prepayment_cents(rp_total_cents, rp)  # G7
                rate_options.append(
                    {
                        "rate": rp,
                        "total_eur": rp_total_cents / 100,
                        "auto_discount_label": rp_label,
                        "prepay_percent": rp.prepayment_percent,  # G7
                        "prepay_eur": rp_prepay / 100,
                    }
                )
    tenant = getattr(request, "tenant", None)
    payments_on = getattr(tenant, "payments_enabled", False) and connect.is_connect_configured()
    # G7: оплата при брони нужна, если бизнес принимает платежи и есть депозит юнита
    # или хотя бы один тариф с предоплатой.
    any_prepay = any(getattr(rp, "prepayment_percent", 0) for rp in rate_plans)
    deposit_required = payments_on and (unit.deposit_cents > 0 or any_prepay)
    from apps.core import extras as extras_engine

    # H3: похожие номера — другие активные юниты, тот же тип вперёд, до 3.
    similar = list(StayUnit.objects.filter(is_active=True).exclude(pk=unit.pk))
    similar.sort(key=lambda u: (u.type != unit.type, u.price_cents))
    similar = similar[:3]

    from apps.core.sellable import sellable_for

    return _render_embed(
        request,
        "storefront/stay_detail.html",
        {
            "unit": unit,
            # UA2-1 (U-A): единый контракт продаваемой сущности (шов UA3/UA4).
            "sellable": sellable_for("stay", unit),
            "today": today,
            "max_date": today + timedelta(days=MAX_DAYS_AHEAD),
            "von": von,
            "bis": bis,
            "adults": adults,
            "children": children,
            "guests": guests,
            "rooms": rooms,  # G5: выбранное число номеров
            "room_choices": range(1, unit.quantity + 1),  # G5: варианты для селектора
            "max_party": unit.max_guests * unit.quantity,  # G5: верх для гостей
            "quote": quote,
            "rate_options": rate_options,  # H1 тарифы для выбранного диапазона
            "kurtaxe_eur": kurtaxe_eur,  # H9 (в total уже включена)
            "extras": extras_engine.active_for("stays"),  # #7 доп-услуги
            "deposit_required": deposit_required,
            "deposit_eur": f"{unit.deposit_cents / 100:.2f}".replace(".", ","),
            "similar": similar,  # H3 похожие номера
            # C3: встроенный календарь наличия — начальный месяц = месяц заезда (или текущий).
            **_calendar_context(
                unit,
                (von or today).replace(day=1),
                today,
                embed_qs="&embed=1" if _is_embed(request) else "",
            ),
        },
        _is_embed(request),
    )


def _calendar_context(unit, first, today, *, embed_qs="") -> dict:
    """A5: контекст партиала `_stay_calendar.html` на месяц `first` (1-е число).
    Общий для встроенного календаря страницы номера (C3) и hx/fetch-свапа (C2)."""
    cur_first = today.replace(day=1)
    max_first = (today + timedelta(days=MAX_DAYS_AHEAD)).replace(day=1)
    first = min(max(first, cur_first), max_first)

    def _shift(d, delta):
        m = d.month - 1 + delta
        return date(d.year + m // 12, m % 12 + 1, 1)

    prev_first, next_first = _shift(first, -1), _shift(first, 1)
    return {
        "unit": unit,
        "cal_first": first,
        "cal_days": availability.month_availability(unit, first.year, first.month, today=today),
        "cal_lead_blanks": range(first.weekday()),  # пустые ячейки до 1-го (Mo-первый)
        "cal_multi": unit.quantity > 1,  # показывать «N frei»
        "prev_year": prev_first.year,
        "prev_month": prev_first.month,
        "next_year": next_first.year,
        "next_month": next_first.month,
        "show_prev": first > cur_first,
        "show_next": next_first <= max_first,
        "embed_qs": embed_qs,
    }


def unterkunft_unit_calendar(request, pk):
    """A5/C2: визуальный календарь наличия номера — server-rendered месяц-сетка.

    Отдаёт ТОЛЬКО партиал `_stay_calendar.html` (для fetch-свапа при перелистывании
    месяца ‹ ›). Месяц — из `?year=&month=` (по умолчанию текущий). Окно ограничено:
    не раньше текущего месяца, не дальше `MAX_DAYS_AHEAD`. Гейт — модуль stays.
    """
    _require_stays_active(request)
    unit = get_object_or_404(StayUnit, pk=pk, is_active=True)
    today = timezone.localdate()
    try:
        first = date(int(request.GET.get("year") or today.year), int(request.GET["month"]), 1)
    except (TypeError, ValueError, KeyError):
        first = today.replace(day=1)
    ctx = _calendar_context(unit, first, today, embed_qs="&embed=1" if _is_embed(request) else "")
    return render(request, "storefront/_stay_calendar.html", ctx)


def _back_to_unit(pk, von, bis, adults, children, embed=False):
    url = reverse("storefront-unterkunft-unit", args=[pk])
    if von and bis:
        url = f"{url}?von={von}&bis={bis}&erw={adults}&kinder={children}"
        return f"{url}&embed=1" if embed else url
    return f"{url}?embed=1" if embed else url


def unterkunft_book(request, pk):
    _require_stays_active(request)
    if request.method != "POST":
        return redirect("storefront-unterkunft-unit", pk=pk)
    unit = get_object_or_404(StayUnit, pk=pk, is_active=True)
    if request.POST.get("website"):  # honeypot
        return redirect("storefront-unterkunft-unit", pk=pk)
    if ratelimit.hit("stay", ratelimit.client_ip(request), limit=RL_LIMIT, window=RL_WINDOW):
        return HttpResponse(status=429)

    von = _parse_date(request.POST.get("von"))
    bis = _parse_date(request.POST.get("bis"))
    adults, children = _parse_guests(request.POST)
    rooms = _parse_rooms(request.POST, unit)  # G5
    embed = _is_embed(request)
    if not (von and bis):
        raise Http404
    back = _back_to_unit(pk, von, bis, adults, children, embed)

    name = request.POST.get("name", "").strip()
    if not name:
        messages.error(request, _("Please tell us your name."))
        return redirect(back)
    from apps.core import extras as extras_engine

    extras_snap = extras_engine.snapshot(
        request.POST.getlist("extra"), "stays", nights=(bis - von).days
    )
    # H1: выбранный тариф (если бизнес завёл тарифы). Невалидный/чужой pk → None
    # (бронь по базовой цене), но если тарифы есть — берём первый по порядку.
    rate_plan = None
    active_rates = list(RatePlan.objects.filter(is_active=True))
    if active_rates:
        rate_pk = request.POST.get("rate_plan")
        rate_plan = next((r for r in active_rates if str(r.pk) == str(rate_pk)), active_rates[0])
    try:
        booking = services.book_stay(
            unit,
            arrival=von,
            departure=bis,
            name=name,
            email=request.POST.get("email", "").strip(),
            phone=request.POST.get("phone", "").strip(),
            adults=adults,
            children=children,
            note=request.POST.get("note", "").strip()[:2000],
            source_channel=(request.GET.get("ch") or "")[:50],
            extras=extras_snap,
            rate_plan=rate_plan,
            voucher_code=request.POST.get("voucher_code", "").strip(),
            rooms=rooms,
        )
    except services.MinStay:
        messages.error(request, _("Please book at least the minimum number of nights."))
        return redirect(back)
    except services.MaxGuests:
        messages.error(request, _("Too many guests for this unit."))
        return redirect(back)
    except services.PromoInvalid:
        messages.error(request, _("This promo code is not valid for this booking."))
        return redirect(back)
    except (services.StayUnavailable, ValueError):
        messages.error(
            request, _("These dates are no longer available. Please pick another range.")
        )
        return redirect(back)

    # Онлайн-оплата при брони: предоплата по тарифу (G7, % от итога) или, если её
    # нет, депозит юнита (E4). Если сумма > 0 и бизнес принимает оплату — ведём на
    # Stripe Checkout (на счёт бизнеса). Иначе — обычная бронь без оплаты.
    tenant = getattr(request, "tenant", None)
    prepay = pricing.prepayment_cents(booking.total_cents, rate_plan)
    upfront = prepay if prepay > 0 else unit.deposit_cents * rooms  # G5: депозит × номера
    if (
        upfront > 0
        and getattr(tenant, "payments_enabled", False)
        and connect.is_connect_configured()
    ):
        booking.deposit_cents = upfront
        booking.payment_state = StayBooking.PAYMENT_PENDING
        booking.save(update_fields=["deposit_cents", "payment_state", "updated_at"])
        ok_url = (
            request.build_absolute_uri(reverse("storefront-stay-ok", args=[booking.reference_code]))
            + "?paid=1"
            + ("&embed=1" if embed else "")
        )
        cancel_url = request.build_absolute_uri(
            reverse("storefront-unterkunft-unit", args=[unit.pk])
        )
        try:
            return redirect(
                payments.stay_deposit_checkout_url(
                    booking, tenant, success_url=ok_url, cancel_url=cancel_url
                )
            )
        except stripe.error.StripeError:
            # оплата временно недоступна — бронь остаётся (pending), не теряем её
            pass
    ok = reverse("storefront-stay-ok", args=[booking.reference_code])
    return redirect(f"{ok}?embed=1" if embed else ok)


def unterkunft_confirmation(request, code):
    _require_stays_active(request)
    booking = get_object_or_404(StayBooking.objects.select_related("unit"), reference_code=code)
    from apps.telegram.notify import deep_link

    return _render_embed(
        request,
        "storefront/stay_confirmation.html",
        {
            "booking": booking,
            "telegram_link": deep_link(booking.customer),
            "cancel_url": cancel_url(booking),  # H4b
            "checkin_url": checkin_url(booking),  # G6 Online-Checkin
        },
        _is_embed(request),
    )


def hausordnung(request):
    """H6: страница «Hausordnung» (правила проживания) — свободный текст из
    StaySettings + Kurtaxe-инфо. Гейт модулем stays; нет текста → 404."""
    _require_stays_active(request)
    from .models import StaySettings

    settings_obj = StaySettings.load()
    if not (settings_obj.house_rules or "").strip():
        raise Http404
    return render(
        request,
        "storefront/stay_hausordnung.html",
        {"settings": settings_obj},
    )


# --- G1: Geschenkgutscheine (продажа подарочных сертификатов) ---------------------

GIFT_PRESETS_CENTS = (5000, 10000, 15000, 20000)  # 50/100/150/200 €


def _require_gift_active(request):
    """Гутшайны доступны, если активен stays И бизнес принимает онлайн-оплату."""
    _require_stays_active(request)
    tenant = getattr(request, "tenant", None)
    if not getattr(tenant, "payments_enabled", False) or not connect.is_connect_configured():
        raise Http404


def gutschein_index(request):
    _require_gift_active(request)
    return render(
        request,
        "storefront/gift_voucher.html",
        {"presets_eur": [c // 100 for c in GIFT_PRESETS_CENTS]},
    )


def gutschein_buy(request):
    _require_gift_active(request)
    if request.method != "POST":
        return redirect("storefront-gutschein")
    if request.POST.get("website"):  # honeypot
        return redirect("storefront-gutschein")
    if ratelimit.hit("gift", ratelimit.client_ip(request), limit=RL_LIMIT, window=RL_WINDOW):
        return HttpResponse(status=429)

    from apps.loyalty import gift

    try:
        amount_cents = round(float(request.POST.get("amount_eur", "0").replace(",", ".")) * 100)
    except (TypeError, ValueError):
        amount_cents = 0
    try:
        gv = gift.create_gift_voucher(
            buyer_name=request.POST.get("name", ""),
            buyer_email=request.POST.get("email", ""),
            amount_cents=amount_cents,
            recipient_name=request.POST.get("recipient", ""),
            message=request.POST.get("message", ""),
        )
    except ValueError:
        messages.error(request, _("Please enter your name, email and a valid amount."))
        return redirect("storefront-gutschein")

    tenant = request.tenant
    ok_url = request.build_absolute_uri(reverse("storefront-gutschein-ok"))
    cancel_url = request.build_absolute_uri(reverse("storefront-gutschein"))
    try:
        url = connect.connected_checkout_session(
            connect_id=tenant.stripe_connect_id,
            amount_cents=gv.amount_cents,
            product_name=f"Geschenkgutschein {gv.amount_eur:.0f} €",
            metadata={
                "kind": "gift_voucher",
                "tenant_schema": tenant.schema_name,
                "gift_id": str(gv.id),
            },
            success_url=ok_url,
            cancel_url=cancel_url,
            business_type=getattr(tenant, "business_type", ""),
        )
    except stripe.error.StripeError:
        messages.error(request, _("Payment is temporarily unavailable. Please try again later."))
        return redirect("storefront-gutschein")
    return redirect(url)


def gutschein_confirmation(request):
    _require_gift_active(request)
    return render(request, "storefront/gift_voucher_ok.html", {})


_CANCEL_SALT = "stay-cancel"


def cancel_token(booking) -> str:
    from django.core import signing

    return signing.dumps(str(booking.pk), salt=_CANCEL_SALT)


def cancel_url(booking) -> str:
    return reverse("storefront-stay-cancel", args=[cancel_token(booking)])


def unterkunft_cancel(request, token):
    """H4b: самостоятельная отмена брони гостем по подписанной ссылке.

    GET — показать политику отмены (из снимка тарифа H1) и кнопку. POST —
    отменить через FSM; при бесплатной отмене (flexible до дедлайна) и оплаченном
    депозите вернуть его (Stripe Connect). Невозвратный тариф — отмена без возврата.
    """
    _require_stays_active(request)
    from django.core import signing

    try:
        pk = signing.loads(token, salt=_CANCEL_SALT)
    except signing.BadSignature as exc:
        raise Http404 from exc
    booking = get_object_or_404(StayBooking.objects.select_related("unit"), pk=pk)
    state = services.cancellation_state(booking)

    if request.method == "POST" and state["can_cancel"]:
        from apps.core.fsm import IllegalTransition

        from .state_machine import StayBookingSM

        try:
            StayBookingSM().apply(booking, "cancelled")
        except IllegalTransition:
            messages.error(request, _("This booking can no longer be cancelled."))
            return redirect(reverse("storefront-stay-cancel", args=[token]))
        # Возврат депозита: только при бесплатной отмене и оплаченном депозите.
        tenant = getattr(request, "tenant", None)
        if (
            state["free"]
            and booking.payment_state == StayBooking.PAYMENT_PAID
            and booking.stripe_payment_intent
            and getattr(tenant, "stripe_connect_id", "")
        ):
            try:
                connect.refund(
                    connect_id=tenant.stripe_connect_id,
                    payment_intent=booking.stripe_payment_intent,
                )
                booking.payment_state = StayBooking.PAYMENT_REFUNDED
                booking.save(update_fields=["payment_state", "updated_at"])
            except stripe.error.StripeError:
                pass  # отмена состоялась; возврат можно довести вручную в кабинете
        messages.success(request, _("Your booking has been cancelled."))
        return redirect(reverse("storefront-stay-cancel", args=[token]))

    return render(
        request,
        "storefront/stay_cancel.html",
        {"booking": booking, "state": state, "token": token},
    )


_CHECKIN_SALT = "stay-checkin"


def checkin_token(booking) -> str:
    from django.core import signing

    return signing.dumps(str(booking.pk), salt=_CHECKIN_SALT)


def checkin_url(booking) -> str:
    return reverse("storefront-stay-checkin", args=[checkin_token(booking)])


def unterkunft_checkin(request, token):
    """G6: Online-Checkin — гость заполняет цифровой Meldeschein (BMG) по
    подписанной ссылке. GET — форма (префилл из брони), POST — сохранить подпись
    (Ф.И.О. печатью + время + IP). Отменённую/прошедшую бронь не чек-иним."""
    _require_stays_active(request)
    from django.core import signing

    from .models import GuestRegistration

    try:
        pk = signing.loads(token, salt=_CHECKIN_SALT)
    except signing.BadSignature as exc:
        raise Http404 from exc
    booking = get_object_or_404(StayBooking.objects.select_related("unit", "customer"), pk=pk)
    reg = GuestRegistration.objects.filter(booking=booking).first()
    done = reg is not None and bool(reg.signed_at)
    cancelled = booking.status == StayBooking.STATUS_CANCELLED

    if request.method == "POST" and not done and not cancelled:
        if not request.POST.get("confirm") or not request.POST.get("signed_name", "").strip():
            messages.error(request, _("Please fill in your name and confirm."))
            return redirect(reverse("storefront-stay-checkin", args=[token]))
        reg = reg or GuestRegistration(booking=booking)
        reg.last_name = request.POST.get("last_name", "").strip()[:120]
        reg.first_name = request.POST.get("first_name", "").strip()[:120]
        reg.birth_date = _parse_date(request.POST.get("birth_date"))
        reg.nationality = request.POST.get("nationality", "").strip()[:80]
        reg.street = request.POST.get("street", "").strip()[:200]
        reg.postal_code = request.POST.get("postal_code", "").strip()[:20]
        reg.city = request.POST.get("city", "").strip()[:120]
        reg.country = request.POST.get("country", "").strip()[:80]
        reg.doc_type = request.POST.get("doc_type", "").strip()[:40]
        reg.doc_number = request.POST.get("doc_number", "").strip()[:60]
        try:
            reg.accompanying = max(0, min(int(request.POST.get("accompanying", "0")), 50))
        except (TypeError, ValueError):
            reg.accompanying = 0
        reg.signed_name = request.POST.get("signed_name", "").strip()[:200]
        reg.signed_at = timezone.now()
        reg.signed_ip = ratelimit.client_ip(request)
        reg.save()
        messages.success(request, _("Thank you! Your check-in is complete."))
        return redirect(reverse("storefront-stay-checkin", args=[token]))

    cust = booking.customer
    name_parts = (cust.name or "").rsplit(" ", 1)
    return render(
        request,
        "storefront/stay_checkin.html",
        {
            "booking": booking,
            "reg": reg,
            "done": done,
            "cancelled": cancelled,
            "prefill_first": reg.first_name if reg else (name_parts[0] if name_parts else ""),
            "prefill_last": reg.last_name
            if reg
            else (name_parts[1] if len(name_parts) > 1 else ""),
            "token": token,
        },
    )


_ICAL_SALT = "stay-ical"


def ical_token(unit) -> str:
    from django.core import signing

    return signing.dumps(str(unit.pk), salt=_ICAL_SALT)


def unterkunft_ical(request, token):
    """Публичный iCal-фид занятости юнита (A5b) — Booking.com/Airbnb/Google.

    Токен подписан (signing) и несёт pk юнита; гейтинг модулем stays. Отдаёт
    активные брони + блоки как all-day VEVENT.
    """
    _require_stays_active(request)
    from django.core import signing

    from . import ical
    from .models import UnitBlock

    try:
        unit_pk = signing.loads(token, salt=_ICAL_SALT)
    except signing.BadSignature as exc:
        raise Http404 from exc
    unit = get_object_or_404(StayUnit, pk=unit_pk)
    bookings = StayBooking.objects.filter(unit=unit, status__in=StayBooking.ACTIVE_STATUSES)
    blocks = UnitBlock.objects.filter(unit=unit)
    body = ical.build_feed(unit, bookings, blocks, host=request.get_host())
    return HttpResponse(body, content_type="text/calendar; charset=utf-8")


FEED_DAYS = 60  # горизонт фида цен/наличия для метапоиска (G8)


def stays_feed(request):
    """G8: машиночитаемый фид наличия и цен (rates & availability) для метапоиска
    /channel/Google Hotel Center. Публичный (те же данные, что и поиск), noindex.

    На каждый активный номер — посуточно на FEED_DAYS дней вперёд: число свободных
    юнитов и базовая цена за ночь (сезон/выходные). Deep-link на прямую бронь с
    датами — чтобы метапоиск вёл сразу в наш движок (Free Booking Links)."""
    _require_stays_active(request)
    from . import pricing

    today = timezone.localdate()
    units = list(StayUnit.objects.filter(is_active=True))
    _days, rows = availability.occupancy_grid(units, today, FEED_DAYS)
    base = request.build_absolute_uri(reverse("storefront-unterkunft"))
    tenant = getattr(request, "tenant", None)
    rooms = []
    for unit, cells in rows:
        seasons = list(unit.season_rates.all())
        nights = [
            {
                "date": c["day"].isoformat(),
                "units_free": c["free"],
                "available": c["free"] > 0,
                "price": round(pricing.nightly_price_cents(unit, c["day"], seasons) / 100, 2),
            }
            for c in cells
        ]
        rooms.append(
            {
                "id": str(unit.pk),
                "name": unit.name,
                "type": unit.get_type_display(),
                "max_guests": unit.max_guests,
                "quantity": unit.quantity,
                "min_nights": unit.min_nights,
                "deeplink": f"{base}{unit.pk}/",
                "nights": nights,
            }
        )
    return JsonResponse(
        {
            "property": {
                "name": getattr(tenant, "name", "") or "",
                "url": request.build_absolute_uri("/"),
                "address": getattr(tenant, "address", "") or "",
                "city": getattr(tenant, "city", "") or "",
                "currency": "EUR",
            },
            "generated_at": timezone.now().isoformat(),
            "days": FEED_DAYS,
            "search_deeplink": base + "?von={arrival}&bis={departure}&erw={adults}",
            "rooms": rooms,
        },
        json_dumps_params={"ensure_ascii": False},
    )
