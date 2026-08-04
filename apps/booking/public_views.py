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
from apps.promotions.services import OutOfStock as PromoSoldOut

from . import availability, payments, pricing, services
from .models import Booking, Pass, Resource, Service
from .state_machine import BookingSM

RL_LIMIT = 5  # попыток записи на IP
RL_WINDOW = 600  # за 10 минут
MAX_DAYS_AHEAD = 30  # горизонт записи
MAX_UNITS = 8  # HF-7: максимум подряд идущих единиц услуги в одной брони


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


def _parse_start(raw):
    """HF-6c: ISO-время из URL (?slot=…) или None. Мусор не должен ронять страницу.

    Ревью 2026-07-31: строка БЕЗ смещения («2026-08-08T10:00:00») парсится успешно и
    даёт naive datetime — при сортировке вперемешку с aware-стартами сетки это давало
    TypeError и 500. Наивное время — такой же мусор, как нечисло: отбрасываем.
    """
    try:
        parsed = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None
    return parsed if timezone.is_aware(parsed) else None


def _parse_units(raw) -> int:
    """HF-7: сколько подряд идущих единиц услуги берёт гость (?dauer=N).

    Фидбэк владельца: «не удаётся забронировать услугу на несколько единиц
    времени, к примеру с 8:30 до 12:30». Единица неделима (мойку 60 мин нельзя
    взять на 90), поэтому вводом служит количество единиц, а не произвольные
    границы; получившийся отрезок подписан на витрине. Мусор/вне капа → 1, то
    есть прежнее поведение байт-в-байт.
    """
    try:
        return max(1, min(MAX_UNITS, int(raw)))
    except (TypeError, ValueError):
        return 1


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


def _redeem_pass_if_code(request, bookings) -> bool:
    """G9: если предъявлен Mehrfachkarte-Code — гасим по визиту НА КАЖДЫЙ период.

    Возвращает True, когда код был предъявлен (тогда депозит/оплату пропускаем —
    карта вместо денег). Невалидный/исчерпанный код: брони остаются, на оплату НЕ
    уводим (не списываем деньги при ошибке карты), показываем сообщение — владелец
    разберётся.

    Ревью 2026-07-31 (HF-6c): раньше сюда приходила ОДНА бронь, и запись на N времён
    стоила гостю один визит с карты (до MAX_GROUP_SLOTS=6), а подтверждалась только
    первая. Гасим ровно столько визитов, сколько периодов забронировано; если визитов
    не хватило — честно говорим, сколько удалось погасить.
    """
    code = request.POST.get("pass_code", "").strip()
    if not code:
        return False
    card = Pass.objects.filter(code__iexact=code, is_active=True).first()
    if card is None:
        messages.error(request, _("This pass code is not valid."))
        return True
    done = 0
    for booking in bookings:
        try:
            services.redeem_pass(card, booking=booking)
        except services.PassInvalid:
            break
        done += 1
        # Карта = оплачено → авто-подтверждаем бронь (если ресурс не требует
        # ручного подтверждения), как при оплаченном депозите.
        if not booking.resource.require_manual_confirm:
            try:
                BookingSM().apply(booking, "confirmed")
            except IllegalTransition:
                pass
    if done == 1:
        messages.success(request, _("Pass applied — one visit redeemed."))
    elif done:
        # Отдельная строка, а не ngettext: тот же msgid уже живёт в .po как
        # ОДИНОЧНЫЙ — makemessages падает на строке, которая одновременно
        # singular и plural (урок 2026-07-31).
        messages.success(request, _("Pass applied — %(n)d visits redeemed.") % {"n": done})
    if done < len(bookings):
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
        selected = provider.selected(request.GET)
        kollektion = selected["kollektion"]
        services_qs = provider.sort(
            provider.search(provider.apply(services_base, request.GET), q), sort
        )
        # Чипы подборок — из снимка ДО фасета (present-values).
        presented = provider.present(services_base, request.GET)
        collection_chips = presented["collection_chips"]
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
                + ([("kollektion", kollektion)] if kollektion else [])
                + ([("video", "1")] if selected["video"] else []),
                # UB3-2: чипы подборок (фасет ?kollektion=<slug>).
                "collection_chips": collection_chips,
                "active_kollektion": kollektion,
                # LS-1: чип «📹 Video-Beratung» (?video=1) — авто при ≥1 видео-услуге.
                "video_available": presented["video_available"],
                "active_video": selected["video"],
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


def service_detail(request, pk):
    """Страница услуги: описание + ВЫБОР ВРЕМЕНИ на одном экране.

    Фидбэк владельца 2026-07-31: раньше деталь была SEO-страницей с кнопкой,
    которая ПЕРЕЗАГРУЖАЛА витрину на отдельный слот-пикер — гость жал «забронировать»
    и только после перезагрузки видел календарь. Теперь календарь и времена видны
    сразу, а кнопка брони появляется по выбору времени (двухшаговый buy-box).
    Старый адрес `/termin/leistung/<pk>/` остаётся (письма, QR, внешние ссылки) и
    показывает ту же страницу.

    Исключение — услуги, у которых первичное действие «запрос сметы» (A7/A9
    Handwerker, override `primary_service_cta='request'`): там бизнес СПЕЦИАЛЬНО
    хочет сначала заявку, а не бронь, поэтому деталь остаётся страницей с парой
    CTA (замки test_service_detail_primary_action_request_override и др.).
    """
    _require_booking_active(request)
    service = get_object_or_404(Service, pk=pk, is_active=True)
    tenant = getattr(request, "tenant", None)
    from apps.core import archetypes

    if archetypes.primary_service_action(service, tenant) == "request":
        return render(
            request,
            "storefront/service_detail.html",
            _service_rich_context(request, service, tenant),
        )
    return service_slots(request, pk)


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
    # HF-7: длина брони = N единиц услуги подряд (?dauer=N). Сетка считается на
    # суммарную длительность — старт годится, только если свободен ВЕСЬ отрезок.
    units = _parse_units(request.GET.get("dauer"))
    total_minutes = units * service.duration_minutes
    starts = availability.service_slots(
        service, day, resource=chosen, duration_minutes=total_minutes
    )
    # R3 empty-state: день без слотов → ближайший свободный старт (перехват
    # уходящего клиента). Скан от завтра выбранного дня; вычисляем лишь при пустом.
    next_free = None
    if not starts:
        next_free = availability.next_free_slot(
            service, day + timedelta(days=1), max_days=MAX_DAYS_AHEAD, resource=chosen
        )
    # HF-6c (фидбэк владельца: «нельзя выбрать услугу сразу на 2-3 времени»):
    # выбор — СПИСОК стартов (?slot=A&slot=B). Валидируем каждый по живой сетке,
    # порядок — как в сетке, кап — тот же, что у services.book_many.
    raw_slots = request.GET.getlist("slot")
    picked = {r for r in raw_slots if r}
    # Сетка стартов идёт с шагом расписания, а услуга может длиться дольше шага
    # (демо-прокат — 8 часов при шаге 30 мин): соседние времена ПЕРЕСЕКАЮТСЯ и
    # вместе не бронируются. Пересечения выкидываем здесь и гасим в сетке ниже —
    # иначе гость набирал заведомо невозможный набор и получал отказ на отправке.
    duration = timedelta(minutes=total_minutes)
    selected_list = []
    for one in starts:
        if one.isoformat() not in picked:
            continue
        if any(one < k + duration and k < one + duration for k in selected_list):
            continue
        selected_list.append(one)
        if len(selected_list) >= services.MAX_GROUP_SLOTS:
            break
    # Выбор с ДРУГИХ дней несём через URL, чтобы навигация по дням его не теряла.
    # Мусор и «протухшие» времена ТЕКУЩЕГО дня (их уже нет в сетке — заняли)
    # отбрасываем: иначе POST падал бы целиком из-за слота, которого гость не видит.
    other_day_dts = []
    for raw in sorted(picked - {s.isoformat() for s in starts}):
        one = _parse_start(raw)
        if one is None or one.date() == day:
            continue
        other_day_dts.append(one)
    other_day_dts = other_day_dts[: max(0, services.MAX_GROUP_SLOTS - len(selected_list))]
    other_days = [s.isoformat() for s in other_day_dts]
    selected = selected_list[0] if selected_list else None
    # Чистый набор: только то, что реально уйдёт в POST (он же — состояние ссылок).
    picked = {s.isoformat() for s in selected_list} | set(other_days)
    # Времена всей брони в хронологии — hidden-поля формы и её заголовок.
    booking_slots = sorted(selected_list + other_day_dts)
    tenant = getattr(request, "tenant", None)
    from apps.core import extras as extras_engine

    # A3: месяц-сетка наличия — день кликабелен, если у услуги есть свободный старт
    # (на выбранном мастере или любом). resource-параметр несём в ссылки дня.
    max_day = today + timedelta(days=MAX_DAYS_AHEAD)
    cal = _slot_month(
        lambda d: bool(
            availability.service_slots(service, d, resource=chosen, duration_minutes=total_minutes)
        ),
        _cal_first(request, day),
        today,
        max_day,
    )
    from apps.core.sellable import sellable_for

    ctx = {
        "service": service,
        # UA3-2: контракт для _buybox; buybox_ready = валидный выбранный слот
        # (сервер всё равно ре-валидирует в service_book).
        # HF-6c: форма нужна при ЛЮБОМ выбранном времени — в том числе когда гость
        # ушёл на соседний день добирать периоды (иначе набор есть, а оформить нечем).
        "sellable": sellable_for("service", service, buybox_ready=bool(booking_slots)),
        "day": day,
        "starts": starts,
        "next_free": next_free,  # R3: ближайший свободный старт (empty-state)
        "selected": selected,
        # HF-6c: мультивыбор — список выбранных стартов этого дня + с других дней.
        "selected_list": selected_list,
        "booking_slots": booking_slots,
        "selected_isos": [s.isoformat() for s in booking_slots],
        "cross_day": bool(other_day_dts),
        "other_day_slots": other_days,
        "selected_count": len(booking_slots),
        # Навигация по дням несёт уже выбранные времена (иначе набор терялся).
        "slot_qs_prev": _slot_carry_qs(
            day - timedelta(days=1),
            chosen,
            selected_list,
            other_days,
            embed=_is_embed(request),
            units=units,
        ),
        "slot_qs_next": _slot_carry_qs(
            day + timedelta(days=1),
            chosen,
            selected_list,
            other_days,
            embed=_is_embed(request),
            units=units,
        ),
        "slot_toggles": _slot_toggles(
            day,
            chosen,
            starts,
            picked,
            selected_list,
            duration,
            embed=_is_embed(request),
            units=units,
        ),
        # HF-7: выбор длительности — чипы «1× / 2× / …» над сеткой; отрезки
        # (начало-конец) для честного заголовка формы «09:00–12:00».
        "selected_spans": [{"start": x, "end": x + duration} for x in selected_list],
        "booking_spans": [{"start": x, "end": x + duration} for x in booking_slots],
        "units": units,
        "unit_minutes": service.duration_minutes,
        "total_minutes": total_minutes,
        "unit_options": _unit_options(day, chosen, service, units, embed=_is_embed(request)),
        "max_group_slots": services.MAX_GROUP_SLOTS,
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
        # HF-5: цена на ВЫБРАННЫЙ день. Показываем ровно то, что спишем при брони
        # (тот же резолвер) — иначе гость видел базовую цену, а платил сезонную.
        "day_price_eur": pricing.price_cents_for(service, day) * units / 100,
        "day_price_label": pricing.season_label_for(service, day),
        "day_price_differs": pricing.price_cents_for(service, day) != service.price_cents,
        **cal,
    }
    embed = _is_embed(request)
    if request.GET.get("box") == "1":
        # Багфикс 2026-07-27: фрагмент #svc-box для fetch-свопа селектора
        # (выбор даты/времени без перезагрузки страницы; фолбэк — обычный GET).
        return render(
            request,
            "storefront/_service_slots_box.html",
            {**ctx, "embed": embed, "embed_qs": "&embed=1" if embed else ""},
        )
    # HF-3 (фидбэк владельца #11): страница услуги — как карточка товара (галерея
    # слева, блок цены/выбора справа, описание и прочие секции ниже). Богатый
    # контент берём тем же билдером, что деталь, — двух разных «страниц услуги»
    # с расходящимся содержимым больше нет.
    rich = _service_rich_context(request, service, tenant)
    # Контракт sellable у слот-страницы СВОЙ: он несёт buybox_ready (выбран слот) —
    # без него двухшаговый buy-box никогда не показал бы POST-форму.
    rich.pop("sellable", None)
    ctx.update(rich)
    return _render_embed(request, "storefront/service_slots.html", ctx, embed)


def _service_rich_context(request, service, tenant) -> dict:
    """Богатый контент услуги: галерея-контракт, секции тела, отзывы, апселл.

    Общий для детали (`service_detail`) и страницы слотов (HF-3): обе показывают
    одну и ту же услугу, и расхождение содержимого между ними было бы багом по
    построению. Выбор слота сюда НЕ входит — он остаётся частью слот-страницы.
    """
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
    # B3: кросс-селл товаров на детали услуги — featured-first (реюз корзиночного
    # приёма), только при активном модуле catalog и наличии товаров.
    _upsell = []
    if tenant is not None and tenant.is_module_active("catalog"):
        from apps.catalog.models import Product

        _upsell = list(
            Product.objects.filter(is_active=True).order_by("-is_featured", "-created_at")[:4]
        )
    # LS-1: wa.me-CTA видео-консультации — только у видео-услуги при заданном
    # номере WhatsApp бизнеса (ссылка генерится на лету, ничего не храним).
    from apps.core.whatsapp import wa_link

    _video_wa_url = (
        wa_link(getattr(tenant, "whatsapp_number", ""), f"Video-Beratung: {service.name}")
        if service.is_video and tenant is not None
        else ""
    )
    _present = {
        "description": bool(service.description),
        "video": bool(_video_wa_url),
        "attributes": bool(service.attributes_list),
        "faq": bool(service.faq_list),
        "team": bool(_team),
        "reviews": True,  # секция всегда есть (пустое состояние «ещё нет отзывов»)
        "upsell": bool(_upsell),
    }
    _section_template = {
        "description": "storefront/sections/detail/_service_description.html",
        "video": "storefront/sections/detail/_service_video.html",
        "attributes": "storefront/sections/detail/_service_attributes.html",
        "faq": "storefront/sections/detail/_service_faq.html",
        "team": "storefront/sections/detail/_service_team.html",
        "reviews": "storefront/_entity_reviews.html",
        "upsell": "storefront/sections/detail/_service_upsell.html",
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

    return {
        "service": service,
        # LS-1: wa.me-ссылка видео-консультации (пусто = секция не видна).
        "video_wa_url": _video_wa_url,
        # UA2-1 (U-A): единый контракт продаваемой сущности (шов UA3/UA4).
        "sellable": sellable_for("service", service),
        # UA3-1 (реш.2): основное действие детали — booking | request (override).
        "primary_action": archetypes.primary_service_action(service, tenant),
        "resources": _team,
        "upsell": _upsell,
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
    }


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


def _unit_options(day, resource, service, units, *, embed=False) -> list[dict]:
    """HF-7: чипы длительности («1× 90 Min · 09:00–10:30» … ) — сколько единиц
    услуги подряд. Показываем только те N, для которых в этот день ЕСТЬ старт:
    предлагать заведомо невозможную длину нечестно."""
    from urllib.parse import urlencode

    rows = []
    for n in range(1, MAX_UNITS + 1):
        total = n * service.duration_minutes
        if n > 1 and not availability.service_slots(
            service, day, resource=resource, duration_minutes=total
        ):
            continue
        pairs = [("tag", day.isoformat())]
        if resource is not None:
            pairs.append(("resource", str(resource.pk)))
        if n > 1:
            pairs.append(("dauer", str(n)))
        if embed:
            pairs.append(("embed", "1"))
        rows.append(
            {
                "n": n,
                "minutes": total,
                "selected": n == units,
                "url": "?" + urlencode(pairs),
            }
        )
    return rows if len(rows) > 1 else []


def _slot_carry_qs(day, resource, selected_list, other_days, *, embed=False, units=1) -> str:
    """HF-6c: query-хвост, СОХРАНЯЮЩИЙ выбранные времена при навигации по дням.

    Без него переход на соседний день терял уже отмеченные слоты — а гость
    как раз и хочет набрать два-три времени, возможно на разных днях.
    """
    from urllib.parse import urlencode

    pairs = [("tag", day.isoformat())]
    if resource is not None:
        pairs.append(("resource", str(resource.pk)))
    if units > 1:
        pairs.append(("dauer", str(units)))
    for iso in [s.isoformat() for s in selected_list] + list(other_days):
        pairs.append(("slot", iso))
    if embed:
        pairs.append(("embed", "1"))
    return "?" + urlencode(pairs)


def _slot_toggles(
    day, resource, starts, picked, selected_list, duration, *, embed=False, units=1
) -> list:
    """HF-6c: для каждого старта — ссылка, которая ДОБАВЛЯЕТ или СНИМАЕТ его.

    Мультивыбор без JS: состояние живёт в URL (?slot=A&slot=B), клик по времени
    переключает его. `picked` уже очищен вьюхой и включает выбор с других дней —
    его ссылки несут как есть. Старт, ПЕРЕСЕКАЮЩИЙСЯ с уже выбранным (услуга
    длиннее шага сетки), помечаем `blocked`: кликать его нечестно — бронь всё
    равно не состоится.
    """
    from urllib.parse import urlencode

    rows = []
    for start in starts:
        iso = start.isoformat()
        chosen_now = iso in picked
        blocked = not chosen_now and any(
            start < k + duration and k < start + duration for k in selected_list
        )
        keep = [x for x in picked if x != iso] if chosen_now else list(picked) + [iso]
        pairs = [("tag", day.isoformat())]
        if resource is not None:
            pairs.append(("resource", str(resource.pk)))
        if units > 1:
            pairs.append(("dauer", str(units)))
        pairs += [("slot", x) for x in sorted(keep)]
        if embed:
            pairs.append(("embed", "1"))
        rows.append(
            {
                "start": start,
                "selected": chosen_now,
                "blocked": blocked,
                "url": "?" + urlencode(pairs),
            }
        )
    return rows


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
    # HF-6c: гость мог отметить НЕСКОЛЬКО времён — приходит список `start`.
    # Разбираем все, порядок сохраняем; кривой формат = 404 (как было).
    try:
        picked_starts = [
            datetime.fromisoformat(raw) for raw in request.POST.getlist("start") if raw
        ]
    except ValueError:
        raise Http404 from None
    if not picked_starts:
        raise Http404
    picked_starts = picked_starts[: services.MAX_GROUP_SLOTS]
    # #4: выбранный мастер/ресурс (если был) — бронируем именно его.
    rid = request.POST.get("resource", "")
    chosen = Resource.objects.filter(pk=rid, is_active=True).first() if rid else None
    # HF-7: гость мог взять услугу на НЕСКОЛЬКО единиц подряд («с 8:30 до 12:30»)
    # — длина брони и цена умножаются на число единиц, сетка проверяется на весь
    # отрезок. dauer вне капа/мусор → 1 (прежнее поведение).
    units = _parse_units(request.POST.get("dauer") or request.GET.get("dauer"))
    total_minutes = units * service.duration_minutes
    # Каждое время ре-валидируем по живой сетке и назначаем ему свой ресурс:
    # разные периоды может обслуживать разный мастер.
    slot_plan = []
    for one in picked_starts:
        if one not in availability.service_slots(
            service, one.date(), resource=chosen, duration_minutes=total_minutes
        ):
            messages.error(request, _("This time is no longer available. Please pick another."))
            return _embed_redirect("storefront-service-slots", embed, pk=pk)
        one_resource = availability.assign_resource(
            service, one, resource=chosen, duration_minutes=total_minutes
        )
        if one_resource is None:
            messages.error(request, _("This time is no longer available. Please pick another."))
            return _embed_redirect("storefront-service-slots", embed, pk=pk)
        slot_plan.append(
            (
                one_resource,
                one,
                one + timedelta(minutes=total_minutes),
                pricing.price_cents_for(service, one.date()) * units,
            )
        )
    resource = slot_plan[0][0]
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
    # P5 «ценовой слой»: акция услуги применяется АВТОМАТИЧЕСКИ в штатной записи
    # (как авто-скидки stays) — одиночная бронь; для группы (HF-6c) v1 без промо.
    promo = None
    if len(slot_plan) == 1:
        from apps.promotions.price_layer import promo_for_service

        r0, s0, e0, price0 = slot_plan[0]
        hit = promo_for_service(service, s0, getattr(r0, "pk", None))
        if hit is not None and hit[1] * units < price0:
            promo = hit[0]
            slot_plan[0] = (r0, s0, e0, hit[1] * units)
    try:
        # HF-6c: один период = обычная бронь (байт-в-байт как раньше), несколько —
        # группа в одной транзакции: занятый период откатывает весь набор.
        # Цена каждого периода — на его дату (HF-5), Extras/промокод — на первую
        # бронь (набор оформляется как один заказ).
        created = services.book_many(
            slot_plan,
            name=name,
            email=request.POST.get("email", "").strip(),
            phone=request.POST.get("phone", "").strip(),
            note=request.POST.get("note", "").strip()[:2000],
            source_channel=(request.GET.get("ch") or "")[:50],
            service=service,
            extras=extras_snap,
            voucher_code=request.POST.get("voucher_code", ""),
            promotion=promo,
        )
        booking = created[0]
    except services.PromoInvalid:
        # B1.2: невалидный промокод/Gutschein — бронь не создаём, слот не занят.
        messages.error(request, _("This voucher code is not valid."))
        return _embed_redirect("storefront-service-slots", embed, pk=pk)
    except (services.SlotTaken, services.ResourceClosed):
        messages.error(request, _("This time is no longer available. Please pick another."))
        return _embed_redirect("storefront-service-slots", embed, pk=pk)
    except PromoSoldOut:
        # P5: лимит акции исчерпан между показом и отправкой — бронь откатилась.
        messages.error(request, _("Diese Aktion ist leider ausverkauft."))
        return _embed_redirect("storefront-service-slots", embed, pk=pk)

    # PMS-B1 (UWG §7): галка согласия в воронке → Double-Opt-In письмо
    # (прямой opt-in не ставим; подписанным/отписанным — тишина).
    if request.POST.get("marketing") == "on":
        from apps.promotions.newsletter import maybe_send_doi

        maybe_send_doi(booking.customer, base_url=request.build_absolute_uri("/").rstrip("/"))

    # G9: Mehrfachkarte вместо оплаты — если код предъявлен, депозит пропускаем.
    # HF-6c: гасим визит на КАЖДЫЙ период группы (created), а не только на первый.
    if _redeem_pass_if_code(request, created):
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
    ctx = {
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
    }
    embed = _is_embed(request)
    if request.GET.get("box") == "1":
        # Багфикс 2026-07-27: фрагмент #svc-box для fetch-свопа селектора
        # (выбор даты/времени столика без перезагрузки; фолбэк — обычный GET).
        return render(
            request,
            "storefront/_booking_slots_box.html",
            {**ctx, "embed": embed, "embed_qs": "&embed=1" if embed else ""},
        )
    return _render_embed(
        request,
        "storefront/booking_slots.html",
        ctx,
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

    # PMS-B1 (UWG §7): галка согласия в воронке → Double-Opt-In письмо
    # (прямой opt-in не ставим; подписанным/отписанным — тишина).
    if request.POST.get("marketing") == "on":
        from apps.promotions.newsletter import maybe_send_doi

        maybe_send_doi(booking.customer, base_url=request.build_absolute_uri("/").rstrip("/"))

    # G9: Mehrfachkarte вместо оплаты — если код предъявлен, депозит пропускаем.
    if _redeem_pass_if_code(request, [booking]):
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


def termin_pay(request, code):
    """B2.2: «Jetzt bezahlen» — перегенерация Stripe Checkout для неоплаченного
    депозита (URL сессии не хранится). Не pending/прошла → назад на подтверждение."""
    _require_booking_active(request)
    booking = get_object_or_404(Booking, reference_code=code)
    tenant = getattr(request, "tenant", None)
    payable = (
        booking.payment_state == Booking.PAYMENT_PENDING
        and booking.deposit_cents > 0
        and booking.start > timezone.now()
        and getattr(tenant, "payments_enabled", False)
        and connect.is_connect_configured()
    )
    if payable:
        ok_url = (
            request.build_absolute_uri(
                reverse("storefront-termin-ok", args=[booking.reference_code])
            )
            + "?paid=1"
        )
        cancel_url = request.build_absolute_uri(
            reverse("storefront-termin-ok", args=[booking.reference_code])
        )
        try:
            return redirect(
                payments.deposit_checkout_url(
                    booking, tenant, success_url=ok_url, cancel_url=cancel_url
                )
            )
        except stripe.error.StripeError:
            messages.error(
                request, _("Payment is temporarily unavailable. Please try again later.")
            )
    return redirect("storefront-termin-ok", code=booking.reference_code)


def termin_confirmation(request, code):
    _require_booking_active(request)
    # MEDIUM-6: троттлим перебор короткого reference_code (щедро — легитимный клиент
    # открывает свою страницу пару раз).
    if ratelimit.hit("termin_confirm", ratelimit.client_ip(request), limit=60, window=RL_WINDOW):
        return HttpResponse(status=429)
    booking = get_object_or_404(Booking.objects.select_related("resource"), reference_code=code)
    from apps.telegram.notify import deep_link

    # HF-6d: бронь на несколько периодов — показываем ВСЕ времена группы. Иначе
    # гость выбрал два времени, а подтверждение называет одно (и он думает, что
    # второе не записалось).
    group, group_total_eur = [], None
    if booking.group_code:
        group = list(
            Booking.objects.filter(group_code=booking.group_code)
            .exclude(status="cancelled")
            .order_by("start")
        )
        # Ревью 2026-07-31: страница перечисляла N времён, но цену показывала за
        # ОДИН период. Считаем итог по всей группе (Extras/скидка — на первой брони).
        if group:
            group_total_eur = sum(b.total_cents for b in group) / 100
    return _render_embed(
        request,
        "storefront/booking_confirmation.html",
        {
            "booking": booking,
            "group_bookings": group,
            "group_total_eur": group_total_eur,
            "telegram_link": deep_link(booking.customer),
        },
        _is_embed(request),
    )
