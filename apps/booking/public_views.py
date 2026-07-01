"""Публичная запись по времени на витрине (Track D / D3b): /termin/.

Флоу: выбор ресурса → день (по умолчанию сегодня, навигация ±) → свободный
слот → форма контактов (как у брони акции: honeypot + rate-limit по IP) →
подтверждение /t/<code>/. Слот валидируется по сетке free_slots, гонку
закрывает services.book (anti-double-book). Модуль booking выключен → 404.
"""

from datetime import date, datetime, timedelta

import stripe
from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.billing import connect
from apps.core import ratelimit
from apps.core.fsm import IllegalTransition

from . import availability, payments, services
from .models import Booking, Pass, Resource, Service
from .state_machine import BookingSM

RL_LIMIT = 5  # попыток записи на IP
RL_WINDOW = 600  # за 10 минут
MAX_DAYS_AHEAD = 30  # горизонт записи


def _require_booking_active(request):
    tenant = getattr(request, "tenant", None)
    if tenant is None or not tenant.is_module_active("booking"):
        raise Http404


def _parse_day(raw) -> date:
    today = timezone.localdate()
    try:
        day = date.fromisoformat(raw or "")
    except ValueError:
        return today
    return min(max(day, today), today + timedelta(days=MAX_DAYS_AHEAD))


def _redeem_pass_if_code(request, booking) -> bool:
    """G9: если предъявлен Mehrfachkarte-Code — гасим один визит. Возвращает True,
    когда код был предъявлен (тогда депозит/оплату пропускаем — карта вместо денег).

    Невалидный/исчерпанный код: бронь остаётся, на оплату НЕ уводим (не списываем
    деньги при ошибке карты), показываем сообщение — владелец разберётся."""
    code = request.POST.get("pass_code", "").strip()
    if not code:
        return False
    card = Pass.objects.filter(code__iexact=code, is_active=True).first()
    if card is None:
        messages.error(request, _("This pass code is not valid."))
        return True
    try:
        services.redeem_pass(card, booking=booking)
        messages.success(request, _("Pass applied — one visit redeemed."))
        # Карта = оплачено → авто-подтверждаем бронь (если ресурс не требует
        # ручного подтверждения), как при оплаченном депозите.
        if not booking.resource.require_manual_confirm:
            try:
                BookingSM().apply(booking, "confirmed")
            except IllegalTransition:
                pass
    except services.PassInvalid:
        messages.error(request, _("This pass has no visits left or has expired."))
    return True


def _passes_enabled() -> bool:
    return Pass.objects.filter(is_active=True).exists()


def termin_index(request):
    _require_booking_active(request)
    from .models import PassPlan

    has_pass_plans = PassPlan.objects.filter(is_active=True).exists()  # A3: ссылка на абонементы
    services_qs = Service.objects.filter(is_active=True)
    if services_qs.exists():  # G10: бизнес услуг — выбираем услугу, не ресурс
        return render(
            request,
            "storefront/service_index.html",
            {"services": services_qs, "has_pass_plans": has_pass_plans},
        )
    resources = Resource.objects.filter(is_active=True)
    if resources.count() == 1 and not has_pass_plans:  # один ресурс — сразу к слотам
        return redirect("storefront-termin-slots", pk=resources.first().pk)
    return render(
        request,
        "storefront/booking_index.html",
        {"resources": resources, "has_pass_plans": has_pass_plans},
    )


def karten(request):
    """A3: публичная покупка Mehrfachkarte — список тарифов (PassPlan)."""
    _require_booking_active(request)
    from .models import PassPlan

    tenant = getattr(request, "tenant", None)
    can_buy = getattr(tenant, "payments_enabled", False) and connect.is_connect_configured()
    plans = PassPlan.objects.filter(is_active=True).select_related("service")
    return render(request, "storefront/passes.html", {"plans": plans, "can_buy": can_buy})


def karte_kaufen(request, pk):
    """A3: купить тариф абонемента → Stripe Checkout на счёт бизнеса."""
    _require_booking_active(request)
    from . import pass_payments
    from .models import PassPlan

    if request.method != "POST":
        return redirect("storefront-karten")
    if request.POST.get("website"):  # honeypot
        return redirect("storefront-karten")
    if ratelimit.hit("karte", ratelimit.client_ip(request), limit=RL_LIMIT, window=RL_WINDOW):
        return HttpResponse(status=429)
    plan = get_object_or_404(PassPlan, pk=pk, is_active=True)
    tenant = getattr(request, "tenant", None)
    name = request.POST.get("name", "").strip()
    email = request.POST.get("email", "").strip()
    if not (name and email):
        messages.error(request, _("Please enter your name and email."))
        return redirect("storefront-karten")
    if not (getattr(tenant, "payments_enabled", False) and connect.is_connect_configured()):
        messages.error(request, _("Online purchase isn't available — please buy on site."))
        return redirect("storefront-karten")
    ok_url = request.build_absolute_uri(reverse("storefront-karten")) + "?bought=1"
    cancel_url = request.build_absolute_uri(reverse("storefront-karten"))
    try:
        return redirect(
            pass_payments.pass_checkout_url(
                plan, tenant, name=name, email=email, success_url=ok_url, cancel_url=cancel_url
            )
        )
    except stripe.error.StripeError:
        messages.error(request, _("Payment could not be started — please try again."))
        return redirect("storefront-karten")


def service_slots(request, pk):
    """G10: свободные старты под услугу (по всем ресурсам), форма брони."""
    _require_booking_active(request)
    service = get_object_or_404(Service, pk=pk, is_active=True)
    day = _parse_day(request.GET.get("tag"))
    today = timezone.localdate()
    # #4: опциональный выбор конкретного мастера/ресурса (если их несколько).
    resources = list(Resource.objects.filter(is_active=True))
    chosen = None
    rid = request.GET.get("resource", "")
    if rid:
        chosen = next((r for r in resources if str(r.pk) == rid), None)
    starts = availability.service_slots(service, day, resource=chosen)
    selected = None
    raw = request.GET.get("slot", "")
    if raw:
        selected = next((s for s in starts if s.isoformat() == raw), None)
    tenant = getattr(request, "tenant", None)
    from apps.core import extras as extras_engine

    return render(
        request,
        "storefront/service_slots.html",
        {
            "service": service,
            "day": day,
            "starts": starts,
            "selected": selected,
            "resources": resources if len(resources) > 1 else [],  # пикер только при >1
            "chosen_resource": chosen,
            "extras": extras_engine.active_for("booking"),  # #7 доп-услуги
            "deposit_required": service.deposit_cents > 0
            and getattr(tenant, "payments_enabled", False),
            "deposit_eur": f"{service.deposit_cents / 100:.2f}".replace(".", ","),
            "passes_enabled": _passes_enabled(),  # G9: поле Mehrfachkarte-Code
            "prev_day": day - timedelta(days=1) if day > today else None,
            "next_day": day + timedelta(days=1)
            if day < today + timedelta(days=MAX_DAYS_AHEAD)
            else None,
        },
    )


def service_detail(request, pk):
    """UA1-1 (E-1): страница-деталь услуги (описание/фото/цена) с CTA на слот-пикер.

    Сплит (решение владельца): деталь = SEO/описание услуги; сама бронь (выбор
    слота) остаётся на `storefront-service-slots`, куда ведёт primary-CTA. Для A7/A9
    (активен jobs) показываем вторичную кнопку «запрос сметы» (`/anfrage/`).
    """
    _require_booking_active(request)
    service = get_object_or_404(Service, pk=pk, is_active=True)
    tenant = getattr(request, "tenant", None)
    resources = list(Resource.objects.filter(is_active=True))
    return render(
        request,
        "storefront/service_detail.html",
        {
            "service": service,
            "resources": resources if len(resources) > 1 else [],
            "jobs_active": bool(tenant and tenant.is_module_active("jobs")),
            "deposit_required": service.deposit_cents > 0
            and getattr(tenant, "payments_enabled", False),
            "deposit_eur": f"{service.deposit_cents / 100:.2f}".replace(".", ","),
        },
    )


def service_book(request, pk):
    _require_booking_active(request)
    if request.method != "POST":
        return redirect("storefront-service-slots", pk=pk)
    service = get_object_or_404(Service, pk=pk, is_active=True)
    if request.POST.get("website"):  # honeypot
        return redirect("storefront-service-slots", pk=pk)
    if ratelimit.hit("termin", ratelimit.client_ip(request), limit=RL_LIMIT, window=RL_WINDOW):
        return HttpResponse(status=429)
    try:
        start = datetime.fromisoformat(request.POST.get("start", ""))
    except ValueError:
        raise Http404 from None
    # #4: выбранный мастер/ресурс (если был) — бронируем именно его.
    rid = request.POST.get("resource", "")
    chosen = Resource.objects.filter(pk=rid, is_active=True).first() if rid else None
    if start not in availability.service_slots(service, start.date(), resource=chosen):
        messages.error(request, _("This time is no longer available. Please pick another."))
        return redirect("storefront-service-slots", pk=pk)
    resource = availability.assign_resource(service, start, resource=chosen)
    name = request.POST.get("name", "").strip()
    if resource is None or not name:
        messages.error(
            request,
            _("This time is no longer available. Please pick another.")
            if resource is None
            else _("Please tell us your name."),
        )
        return redirect("storefront-service-slots", pk=pk)
    from apps.core import extras as extras_engine

    extras_snap = extras_engine.snapshot(request.POST.getlist("extra"), "booking")
    try:
        booking = services.book(
            resource,
            start=start,
            end=start + timedelta(minutes=service.duration_minutes),
            name=name,
            email=request.POST.get("email", "").strip(),
            phone=request.POST.get("phone", "").strip(),
            note=request.POST.get("note", "").strip()[:2000],
            source_channel=(request.GET.get("ch") or "")[:50],
            service=service,
            price_cents=service.price_cents,
            extras=extras_snap,
        )
    except (services.SlotTaken, services.ResourceClosed):
        messages.error(request, _("This time is no longer available. Please pick another."))
        return redirect("storefront-service-slots", pk=pk)

    # G9: Mehrfachkarte вместо оплаты — если код предъявлен, депозит пропускаем.
    if _redeem_pass_if_code(request, booking):
        return redirect("storefront-termin-ok", code=booking.reference_code)

    # Депозит услуги (P2.5b): на Stripe Checkout, иначе обычная запись.
    tenant = getattr(request, "tenant", None)
    if (
        service.deposit_cents > 0
        and getattr(tenant, "payments_enabled", False)
        and connect.is_connect_configured()
    ):
        booking.deposit_cents = service.deposit_cents
        booking.payment_state = Booking.PAYMENT_PENDING
        booking.save(update_fields=["deposit_cents", "payment_state", "updated_at"])
        ok_url = (
            request.build_absolute_uri(
                reverse("storefront-termin-ok", args=[booking.reference_code])
            )
            + "?paid=1"
        )
        cancel_url = request.build_absolute_uri(
            reverse("storefront-service-slots", args=[service.pk])
        )
        try:
            return redirect(
                payments.deposit_checkout_url(
                    booking, tenant, success_url=ok_url, cancel_url=cancel_url
                )
            )
        except stripe.error.StripeError:
            pass
    return redirect("storefront-termin-ok", code=booking.reference_code)


def termin_slots(request, pk):
    _require_booking_active(request)
    resource = get_object_or_404(Resource, pk=pk, is_active=True)
    day = _parse_day(request.GET.get("tag"))
    today = timezone.localdate()
    # G9: слоты с остатком мест; для групповых курсов (capacity>1) → «N frei».
    slots = availability.free_slots_with_spots(resource, day)
    # Выбранный слот (?slot=<start iso>) раскрывает форму контактов — без JS.
    selected = None
    raw_slot = request.GET.get("slot", "")
    if raw_slot:
        for start, end, _spots in slots:
            if start.isoformat() == raw_slot:
                selected = (start, end)
                break
    from apps.core import extras as extras_engine

    return render(
        request,
        "storefront/booking_slots.html",
        {
            "resource": resource,
            "day": day,
            "slots": slots,
            "group": resource.capacity > 1,
            "selected": selected,
            "extras": extras_engine.active_for("booking"),  # #7 доп-услуги
            "deposit_required": resource.deposit_cents > 0
            and getattr(getattr(request, "tenant", None), "payments_enabled", False),
            "deposit_eur": f"{resource.deposit_cents / 100:.2f}".replace(".", ","),
            "passes_enabled": _passes_enabled(),  # G9: поле Mehrfachkarte-Code
            "prev_day": day - timedelta(days=1) if day > today else None,
            "next_day": day + timedelta(days=1)
            if day < today + timedelta(days=MAX_DAYS_AHEAD)
            else None,
        },
    )


def termin_book(request, pk):
    _require_booking_active(request)
    if request.method != "POST":
        return redirect("storefront-termin-slots", pk=pk)
    resource = get_object_or_404(Resource, pk=pk, is_active=True)
    if request.POST.get("website"):  # honeypot
        return redirect("storefront-termin-slots", pk=pk)
    if ratelimit.hit("termin", ratelimit.client_ip(request), limit=RL_LIMIT, window=RL_WINDOW):
        return HttpResponse(status=429)

    try:
        start = datetime.fromisoformat(request.POST.get("start", ""))
        end = datetime.fromisoformat(request.POST.get("end", ""))
    except ValueError:
        raise Http404 from None
    # Слот должен существовать в сетке расписания — иначе произвольный интервал.
    if (start, end) not in availability.free_slots(resource, start.date()):
        messages.error(request, _("This slot is no longer available. Please pick another."))
        return redirect("storefront-termin-slots", pk=pk)

    name = request.POST.get("name", "").strip()
    if not name:
        messages.error(request, _("Please tell us your name."))
        return redirect("storefront-termin-slots", pk=pk)
    try:
        party_size = max(1, min(int(request.POST.get("party_size", "1")), 50))
    except (TypeError, ValueError):
        party_size = 1
    from apps.core import extras as extras_engine

    extras_snap = extras_engine.snapshot(request.POST.getlist("extra"), "booking")
    try:
        booking = services.book(
            resource,
            start=start,
            end=end,
            name=name,
            email=request.POST.get("email", "").strip(),
            phone=request.POST.get("phone", "").strip(),
            party_size=party_size,
            note=request.POST.get("note", "").strip()[:2000],
            source_channel=(request.GET.get("ch") or "")[:50],
            extras=extras_snap,
        )
    except (services.SlotTaken, services.ResourceClosed):
        messages.error(request, _("This slot is no longer available. Please pick another."))
        return redirect("storefront-termin-slots", pk=pk)

    # G9: Mehrfachkarte вместо оплаты — если код предъявлен, депозит пропускаем.
    if _redeem_pass_if_code(request, booking):
        return redirect("storefront-termin-ok", code=booking.reference_code)

    # Депозит (P2.5b): если у ресурса задан и бизнес принимает оплату — ведём на
    # Stripe Checkout (на счёт бизнеса). Без депозита/оплаты — обычная бронь.
    tenant = getattr(request, "tenant", None)
    if (
        resource.deposit_cents > 0
        and getattr(tenant, "payments_enabled", False)
        and connect.is_connect_configured()
    ):
        booking.deposit_cents = resource.deposit_cents
        booking.payment_state = Booking.PAYMENT_PENDING
        booking.save(update_fields=["deposit_cents", "payment_state", "updated_at"])
        ok_url = (
            request.build_absolute_uri(
                reverse("storefront-termin-ok", args=[booking.reference_code])
            )
            + "?paid=1"
        )
        cancel_url = request.build_absolute_uri(
            reverse("storefront-termin-slots", args=[resource.pk])
        )
        try:
            return redirect(
                payments.deposit_checkout_url(
                    booking, tenant, success_url=ok_url, cancel_url=cancel_url
                )
            )
        except stripe.error.StripeError:
            # оплата временно недоступна — бронь остаётся (pending), не теряем её
            pass
    return redirect("storefront-termin-ok", code=booking.reference_code)


def termin_confirmation(request, code):
    _require_booking_active(request)
    booking = get_object_or_404(Booking.objects.select_related("resource"), reference_code=code)
    from apps.telegram.notify import deep_link

    return render(
        request,
        "storefront/booking_confirmation.html",
        {"booking": booking, "telegram_link": deep_link(booking.customer)},
    )
