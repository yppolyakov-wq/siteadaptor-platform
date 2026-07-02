"""Публичная запись по времени на витрине (Track D / D3b): /termin/.

Флоу: выбор ресурса → день (по умолчанию сегодня, навигация ±) → свободный
слот → форма контактов (как у брони акции: honeypot + rate-limit по IP) →
подтверждение /t/<code>/. Слот валидируется по сетке free_slots, гонку
закрывает services.book (anti-double-book). Модуль booking выключен → 404.
"""

import uuid
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


def _cal_first(request, day) -> date:
    """A3: 1-е число отображаемого месяца календаря — из ?cal=YYYY-MM или месяц `day`."""
    try:
        y, m = (request.GET.get("cal") or "").split("-")
        return date(int(y), int(m), 1)
    except (ValueError, AttributeError):
        return day.replace(day=1)


def _slot_month(check_has_slots, first, today, max_day) -> dict:
    """A3: контекст месяц-сетки `_booking_calendar.html`. `check_has_slots(day)->bool`
    зовём только для дней в окне [today, max_day] (прошлое/за горизонтом — не считаем)."""
    cur_first = today.replace(day=1)
    max_first = max_day.replace(day=1)
    first = min(max(first, cur_first), max_first)

    def _shift(d, delta):
        m = d.month - 1 + delta
        return date(d.year + m // 12, m % 12 + 1, 1)

    days, d = [], first
    while d.month == first.month:
        in_window = today <= d <= max_day
        days.append(
            {"day": d, "has_slots": bool(in_window and check_has_slots(d)), "is_past": d < today}
        )
        d += timedelta(days=1)
    next_first = _shift(first, 1)
    return {
        "cal_first": first,
        "cal_days": days,
        "cal_lead_blanks": range(first.weekday()),  # пустые ячейки до 1-го (Mo-первый)
        "cal_prev": _shift(first, -1),
        "cal_next": next_first,
        "cal_show_prev": first > cur_first,
        "cal_show_next": next_first <= max_first,
    }


def _is_embed(request) -> bool:
    """A4: iframe-режим витрины записи (для встраивания на чужой сайт)."""
    return request.GET.get("embed") == "1" or request.POST.get("embed") == "1"


def _render_embed(request, template, ctx, embed):
    """A4: render витрины записи с минимальным шаблоном и разрешением кадрирования
    при ?embed=1 (iframe-виджет, зеркало stays G10). Иначе — обычная витрина."""
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


def _embed_redirect(name, embed, **kwargs):
    """A4: redirect на именованный URL c сохранением ?embed=1 (флоу не выходит из iframe)."""
    url = reverse(name, kwargs=kwargs) if kwargs else reverse(name)
    return redirect(f"{url}?embed=1" if embed else url)


def termin_index(request):
    _require_booking_active(request)
    from .models import PassPlan

    embed = _is_embed(request)
    has_pass_plans = PassPlan.objects.filter(is_active=True).exists()  # A3: ссылка на абонементы
    # UB2-1/2-2/3-2: единая точка фасетов/поиска/сортировки листинга (FacetProvider).
    # Ветку «бизнес услуг» решаем ДО фасета/поиска — пустая выдача ?q=/?kollektion=
    # не должна переключать на листинг ресурсов.
    from apps.core import facets as facets_registry

    provider = facets_registry.provider_for("service")
    services_base = Service.objects.filter(is_active=True)
    if services_base.exists():  # G10: бизнес услуг — выбираем услугу, не ресурс
        q = (request.GET.get("q") or "").strip()
        sort = request.GET.get("sort") or ""
        kollektion = provider.selected(request.GET)["kollektion"]
        services_qs = provider.sort(
            provider.search(provider.apply(services_base, request.GET), q), sort
        )
        # Чипы подборок — из снимка ДО фасета (present-values).
        collection_chips = provider.present(services_base, request.GET)["collection_chips"]
        # UB1-1: раскладка листинга из site_config (+черновик канвы при ?preview=1).
        # Ключ не задан → services_grid=None → шаблон держит легаси-грид (max-w-3xl).
        from apps.tenants import siteconfig

        raw_cfg = request.tenant.site_config
        if request.GET.get("preview") == "1" and isinstance(
            request.session.get("site_preview_draft"), dict
        ):
            raw_cfg = request.session["site_preview_draft"]
        services_grid = None
        if isinstance((raw_cfg or {}).get("service_index_layout"), dict):
            cfg = siteconfig.normalize(raw_cfg)
            services_grid = siteconfig.grid_class_string(cfg["service_index_layout"])
        return _render_embed(
            request,
            "storefront/service_index.html",
            {
                "services": services_qs,
                "has_pass_plans": has_pass_plans,
                "services_grid": services_grid,
                # UB2-2: тулбар каркаса (поиск + сортировка); embed/подборку несём в carry.
                "show_listing_toolbar": True,
                "q": q,
                "sort": sort,
                "sort_options": provider.sort_options(),
                "toolbar_hidden": ([("embed", "1")] if embed else [])
                + ([("kollektion", kollektion)] if kollektion else []),
                # UB3-2: чипы подборок (фасет ?kollektion=<slug>).
                "collection_chips": collection_chips,
                "active_kollektion": kollektion,
            },
            embed,
        )
    resources = Resource.objects.filter(is_active=True)
    if resources.count() == 1 and not has_pass_plans:  # один ресурс — сразу к слотам
        return _embed_redirect("storefront-termin-slots", embed, pk=resources.first().pk)
    return _render_embed(
        request,
        "storefront/booking_index.html",
        {"resources": resources, "has_pass_plans": has_pass_plans},
        embed,
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

    # A3: месяц-сетка наличия — день кликабелен, если у услуги есть свободный старт
    # (на выбранном мастере или любом). resource-параметр несём в ссылки дня.
    max_day = today + timedelta(days=MAX_DAYS_AHEAD)
    cal = _slot_month(
        lambda d: bool(availability.service_slots(service, d, resource=chosen)),
        _cal_first(request, day),
        today,
        max_day,
    )
    from apps.core.sellable import sellable_for

    return _render_embed(
        request,
        "storefront/service_slots.html",
        {
            "service": service,
            # UA3-2: контракт для _buybox; buybox_ready = валидный выбранный слот
            # (сервер всё равно ре-валидирует в service_book).
            "sellable": sellable_for("service", service, buybox_ready=selected is not None),
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
            "next_day": day + timedelta(days=1) if day < max_day else None,
            "cal_qs": f"&resource={chosen.pk}" if chosen else "",  # A3: параметр дня
            **cal,
        },
        _is_embed(request),
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
    from apps.core import archetypes, detail_sections
    from apps.core.sellable import sellable_for
    from apps.reviews import services as review_services
    from apps.tenants import siteconfig

    # UA4-1 slice C: скрытые секции детали услуги (билдер) — под ?preview=1 из черновика.
    _raw = getattr(request.tenant, "site_config", {}) or {}
    if request.GET.get("preview") == "1" and isinstance(
        request.session.get("site_preview_draft"), dict
    ):
        _raw = request.session["site_preview_draft"]
    _hidden = siteconfig.detail_section_hidden(_raw, "booking")
    _team = resources if len(resources) > 1 else []
    # UA4-2: data-driven секции тела детали — порядок из реестра (booking), видимость =
    # (контент присутствует) И (не скрыта в билдере). Шаблон рендерит их циклом
    # (вместо per-template if/elif); замок — снапшот-паритет тест порядка секций.
    _present = {
        "description": bool(service.description),
        "attributes": bool(service.attributes_list),
        "faq": bool(service.faq_list),
        "team": bool(_team),
        "reviews": True,  # секция всегда есть (пустое состояние «ещё нет отзывов»)
    }
    _section_template = {
        "description": "storefront/sections/detail/_service_description.html",
        "attributes": "storefront/sections/detail/_service_attributes.html",
        "faq": "storefront/sections/detail/_service_faq.html",
        "team": "storefront/sections/detail/_service_team.html",
        "reviews": "storefront/_entity_reviews.html",
    }
    body_sections = [
        {
            "key": k,
            "template": _section_template[k],
            "visible": _present.get(k, False) and k not in _hidden,
        }
        for k in detail_sections.section_keys("booking")
        if k in _section_template
    ]

    return render(
        request,
        "storefront/service_detail.html",
        {
            "service": service,
            # UA2-1 (U-A): единый контракт продаваемой сущности (шов UA3/UA4).
            "sellable": sellable_for("service", service),
            # UA3-1 (реш.2): основное действие детали — booking | request (override).
            "primary_action": archetypes.primary_service_action(service, tenant),
            "resources": _team,
            "jobs_active": bool(tenant and tenant.is_module_active("jobs")),
            "deposit_required": service.deposit_cents > 0
            and getattr(tenant, "payments_enabled", False),
            "deposit_eur": f"{service.deposit_cents / 100:.2f}".replace(".", ","),
            # UA4-4b: отзывы об услуге (generic reviews.Review, только верифиц. клиенты).
            "reviews": list(review_services.published_for("service", service.pk)),
            "review_summary": review_services.summary("service", service.pk),
            "review_form_token": uuid.uuid4().hex,
            "review_action": reverse("storefront-service-review", args=[service.pk]),
            # UA4-1 slice C: скрытые секции (для совместимости/отладки); рендер — через body_sections.
            "detail_hidden": _hidden,
            # UA4-2: упорядоченные секции тела детали (data-driven рендер).
            "body_sections": body_sections,
        },
    )


def service_review_submit(request, pk):
    """UA4-4b: приём отзыва об услуге (только верифицированный клиент — есть бронь
    этой услуги по e-mail). Один отзыв на (услуга, email) — повтор обновляет."""
    _require_booking_active(request)
    service = get_object_or_404(Service, pk=pk, is_active=True)
    from apps.reviews.submit import handle_review_submit

    return handle_review_submit(
        request,
        entity_kind="service",
        obj=service,
        detail_url=reverse("storefront-service-detail", args=[service.pk]),
    )


def service_book(request, pk):
    _require_booking_active(request)
    embed = _is_embed(request)  # A4: сохраняем iframe-режим во всём флоу
    if request.method != "POST":
        return _embed_redirect("storefront-service-slots", embed, pk=pk)
    service = get_object_or_404(Service, pk=pk, is_active=True)
    if request.POST.get("website"):  # honeypot
        return _embed_redirect("storefront-service-slots", embed, pk=pk)
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
        return _embed_redirect("storefront-service-slots", embed, pk=pk)
    resource = availability.assign_resource(service, start, resource=chosen)
    name = request.POST.get("name", "").strip()
    if resource is None or not name:
        messages.error(
            request,
            _("This time is no longer available. Please pick another.")
            if resource is None
            else _("Please tell us your name."),
        )
        return _embed_redirect("storefront-service-slots", embed, pk=pk)
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
        return _embed_redirect("storefront-service-slots", embed, pk=pk)

    # G9: Mehrfachkarte вместо оплаты — если код предъявлен, депозит пропускаем.
    if _redeem_pass_if_code(request, booking):
        return _embed_redirect("storefront-termin-ok", embed, code=booking.reference_code)

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
            + ("&embed=1" if embed else "")
        )
        cancel_url = request.build_absolute_uri(
            reverse("storefront-service-slots", args=[service.pk])
        ) + ("?embed=1" if embed else "")
        try:
            return redirect(
                payments.deposit_checkout_url(
                    booking, tenant, success_url=ok_url, cancel_url=cancel_url
                )
            )
        except stripe.error.StripeError:
            pass
    return _embed_redirect("storefront-termin-ok", embed, code=booking.reference_code)


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

    # A3: месяц-сетка наличия — день кликабелен, если у ресурса есть свободный слот.
    max_day = today + timedelta(days=MAX_DAYS_AHEAD)
    cal = _slot_month(
        lambda d: bool(availability.free_slots_with_spots(resource, d)),
        _cal_first(request, day),
        today,
        max_day,
    )
    return _render_embed(
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
            "next_day": day + timedelta(days=1) if day < max_day else None,
            "cal_qs": "",  # A3: ресурс уже в пути URL — доп. параметров дня нет
            **cal,
        },
        _is_embed(request),
    )


def termin_book(request, pk):
    _require_booking_active(request)
    embed = _is_embed(request)  # A4: сохраняем iframe-режим во всём флоу
    if request.method != "POST":
        return _embed_redirect("storefront-termin-slots", embed, pk=pk)
    resource = get_object_or_404(Resource, pk=pk, is_active=True)
    if request.POST.get("website"):  # honeypot
        return _embed_redirect("storefront-termin-slots", embed, pk=pk)
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
        return _embed_redirect("storefront-termin-slots", embed, pk=pk)

    name = request.POST.get("name", "").strip()
    if not name:
        messages.error(request, _("Please tell us your name."))
        return _embed_redirect("storefront-termin-slots", embed, pk=pk)
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
        return _embed_redirect("storefront-termin-slots", embed, pk=pk)

    # G9: Mehrfachkarte вместо оплаты — если код предъявлен, депозит пропускаем.
    if _redeem_pass_if_code(request, booking):
        return _embed_redirect("storefront-termin-ok", embed, code=booking.reference_code)

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
            + ("&embed=1" if embed else "")
        )
        cancel_url = request.build_absolute_uri(
            reverse("storefront-termin-slots", args=[resource.pk])
        ) + ("?embed=1" if embed else "")
        try:
            return redirect(
                payments.deposit_checkout_url(
                    booking, tenant, success_url=ok_url, cancel_url=cancel_url
                )
            )
        except stripe.error.StripeError:
            # оплата временно недоступна — бронь остаётся (pending), не теряем её
            pass
    return _embed_redirect("storefront-termin-ok", embed, code=booking.reference_code)


def termin_confirmation(request, code):
    _require_booking_active(request)
    booking = get_object_or_404(Booking.objects.select_related("resource"), reference_code=code)
    from apps.telegram.notify import deep_link

    return _render_embed(
        request,
        "storefront/booking_confirmation.html",
        {"booking": booking, "telegram_link": deep_link(booking.customer)},
        _is_embed(request),
    )
