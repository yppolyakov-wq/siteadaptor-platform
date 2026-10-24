"""Кабинет записи по времени (Track D / D3c): /dashboard/booking/.

Календарь-день (записи по ресурсам, навигация ±), действия по FSM
(confirm/fulfill/no_show/cancel) и перенос (services.move с anti-double-book),
ручное добавление записи (сразу confirmed), управление ресурсами: создание,
недельные правила, выходные. Гейтинг — модуль «booking» из реестра.
"""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from apps.core import deal_links, freshness, refunds, vat
from apps.core import transactions as core_transactions
from apps.core.fsm import IllegalTransition
from apps.core.i18n_input import (
    apply_i18n_overlay,
    apply_seq_overlay,
    extra_locales,
    i18n_inputs_for,
)

from . import services
from .models import (
    AvailabilityRule,
    Booking,
    ClosedDate,
    Resource,
    Service,
    ServiceSeasonRate,
    ServiceVariant,
)
from .services import MAX_BUFFER_MINUTES, resync_occupancy


def _eur_to_cents(raw) -> int:
    """«5» / «5,50» → центы (анти-кривой ввод → 0)."""
    try:
        return max(0, round(float(str(raw or "0").replace(",", ".")) * 100))
    except (TypeError, ValueError):
        return 0


def _uploaded_image_ref(request, field="image", folder="services") -> dict | None:
    """A3: FileRef из загруженного фото (поле `field`) или None.

    Невалидный файл (не картинка) → None (фото просто не меняем), страница не падает."""
    uploaded = request.FILES.get(field)
    if not uploaded:
        return None
    from apps.catalog.images import save_product_image

    try:
        return save_product_image(uploaded, is_primary=True, folder=folder)
    except Exception:  # noqa: BLE001 — кривой файл не должен ронять CRUD
        return None


@login_required
def calendar(request):
    """W10-6: легаси-вход Tagesplan — 302 на вкладку booking единой страницы
    (GET сохраняется: ?tag/?box живут на Verkäufe; тело по-прежнему собирает
    `calendar_context` — его зовёт вкладка booking)."""
    from apps.core.sales_page import legacy_redirect

    return legacy_redirect(request, tab="booking", view="kalender")


def calendar_context(request):
    day = _parse_day_any(request.GET.get("tag"))
    tz = timezone.get_current_timezone()
    day_start = datetime.combine(day, time.min, tzinfo=tz)
    day_end = day_start + timedelta(days=1)
    bookings = list(
        Booking.objects.filter(start__gte=day_start, start__lt=day_end)
        .select_related("resource", "customer", "service")
        .order_by("resource__name", "start")
    )
    from django.urls import reverse

    from apps.core import status_labels, status_registry, transition_rules

    # KA-12 E6.4a: неявки клиентов дня — одним агрегатом, бейдж «N×» у записи.
    from . import no_shows, tagesplan

    counts = no_shows.counts_for({b.customer_id for b in bookings})
    for b in bookings:
        b.no_show_n = counts.get(b.customer_id, 0)
    resources = list(Resource.objects.filter(is_active=True).prefetch_related("rules"))
    # KA-12 E4.2b: сетка «ресурс × время» (двигаются только действующие записи).
    grid = tagesplan.build(
        resources,
        day,
        bookings,
        active_statuses=status_registry.active_statuses_for("booking"),
        tenant=getattr(request, "tenant", None),
    )
    return {
        "nav": "booking",
        "grid": grid,
        "day": day,
        "prev_day": day - timedelta(days=1),
        "next_day": day + timedelta(days=1),
        "bookings": bookings,
        # Фидбэк владельца 2026-08-04: месячная сетка над списком дня — быстрый
        # переход на любую дату (клик по дню разворачивает его брони ниже).
        **_month_grid_context(request, day),
        "resources": resources,
        # KA-H7: услуга в ручной записи (цена/длительность).
        # KA-12 E4.4b: варианты строками «Услуга · Вариант» (значение `<svc>:<variant>`).
        "manual_services": Service.objects.filter(is_active=True)
        .order_by("name")
        .prefetch_related(
            Prefetch(
                "variants",
                queryset=ServiceVariant.objects.filter(is_active=True).order_by("sort_order", "id"),
                to_attr="active_variants",
            )
        ),
        # A4: iframe-виджет записи для своего сайта.
        "embed_url": request.build_absolute_uri(reverse("storefront-termin")) + "?embed=1",
        # FB-4b: строки панели «Status-Namen» (status, дефолт, своё имя).
        "status_label_rows": status_labels.label_rows(
            getattr(request, "tenant", None), "booking", Booking.STATUSES
        ),
        # FB-3: строки панели «Statusübergänge» (правила переходов).
        "transition_rows": transition_rules.editor_rows(
            getattr(request, "tenant", None), "booking"
        ),
    }


def _parse_day_any(raw):
    """Дата без ограничения горизонтом (кабинету нужна и история)."""
    from datetime import date

    try:
        return date.fromisoformat(raw or "")
    except ValueError:
        return timezone.localdate()


def _month_grid_context(request, day):
    """Месячная сетка Tagesplan: `?cal=YYYY-MM` (дефолт — месяц выбранного дня).

    Счётчик броней по дням — ОДИН запрос на месяц, бакетирование в локальной TZ
    (паттерн Auftragsbuch; TruncDate в SQL считал бы по TIME_ZONE базы). Клампа
    «не в прошлое» витринного `_slot_month` здесь нет — кабинету нужна история.
    Префикс bcal_* — verkaeufe.html мержит контексты нескольких kind'ов."""
    import calendar as _calendar
    from datetime import date

    raw = request.GET.get("cal") or ""
    try:
        year, month = raw.split("-")
        first = date(int(year), int(month), 1)
    except ValueError:
        first = day.replace(day=1)
    days_in_month = _calendar.monthrange(first.year, first.month)[1]
    tz = timezone.get_current_timezone()
    month_start = datetime.combine(first, time.min, tzinfo=tz)
    month_end = datetime.combine(first + timedelta(days=days_in_month), time.min, tzinfo=tz)
    counts: dict = {}
    for start in Booking.objects.filter(start__gte=month_start, start__lt=month_end).values_list(
        "start", flat=True
    ):
        d = timezone.localtime(start).date()
        counts[d] = counts.get(d, 0) + 1
    today = timezone.localdate()
    rows = []
    for i in range(days_in_month):
        d = first + timedelta(days=i)
        rows.append(
            {
                "day": d,
                "count": counts.get(d, 0),
                "is_today": d == today,
                "is_selected": d == day,
            }
        )
    return {
        "bcal_first": first,
        "bcal_lead_blanks": range(first.weekday()),  # Mo-первый
        "bcal_days": rows,
        "bcal_prev": (first - timedelta(days=1)).replace(day=1),
        "bcal_next": first + timedelta(days=days_in_month),
    }


@login_required
def booking_detail(request, pk):
    """Фидбэк 2026-08-05 («перекидывает на непонятную страницу»): карточка брони
    услуги — клиент/услуга/время/цена/статус + действия FSM и перенос. Зеркало
    stays booking-detail (FB-11); сюда ведут доска/списки продаж и Tagesplan."""
    booking = get_object_or_404(
        Booking.objects.select_related("customer", "service", "resource"), pk=pk
    )
    # MX-3: правка состава допов — опции услуги (scope-wide + адресные) и
    # выбранные из снимка. Запись без услуги (бронь стола) — только scope-wide.
    from apps.core import extras as extras_engine

    if booking.service_id:
        edit_extras = extras_engine.active_for(
            "booking", entity_kind="service", entity_id=str(booking.service_id)
        )
    else:
        edit_extras = extras_engine.active_for("booking")
    chosen_extra_ids = {
        str(e.get("id")) for e in (booking.extras or []) if isinstance(e, dict) and e.get("id")
    }
    # DC-1: общий скелет карточки сделки (core/deal_card_base.html) — голова,
    # статус, клиент, связи и календарь приходят из одного источника; здесь
    # остаётся только специфика записи.
    from apps.core import deal_card

    from . import no_shows  # KA-12 E6.4a

    return render(
        request,
        "booking/booking_detail.html",
        {
            "b": booking,
            "no_show": no_shows.summary(booking.customer),
            "service_notes": _service_notes_for(booking),
            "can_edit_policy": _can_edit_policy(request.user),
            "nav": "booking",
            "edit_extras": edit_extras,
            "chosen_extra_ids": chosen_extra_ids,
            **deal_card.card_context(
                request,
                "booking",
                booking,
                sections=_booking_sections(request),
                # VS-3: связь с якорной сделкой (запись может быть услугой к брони).
                links=deal_links.block_context("booking", booking.pk),
            ),
        },
    )


def _move_booking(request, booking):
    """KA-12 E4.2b: перенос записи (время и/или мастер/стол). Форма строки — сообщения
    и редирект (None); перетаскивание в Tagesplan (`X-Requested-With: fetch`) —
    204 / 409 JSON `{code, message}`. Хелпер стоит ВЫШЕ декораторов вьюхи
    (иначе «съел» бы `@login_required` — `test_orphan_decorators`)."""
    from django.http import HttpResponse, JsonResponse

    from apps.booking import availability

    is_fetch = request.headers.get("X-Requested-With") == "fetch"

    def fail(code, msg):
        if is_fetch:
            return JsonResponse({"code": code, "message": str(msg)}, status=409)
        messages.error(request, msg)
        return None

    target = None
    raw_resource = request.POST.get("resource", "").strip()
    if raw_resource and raw_resource != str(booking.resource_id):
        if not _is_uuid(raw_resource):
            raise Http404
        target = get_object_or_404(Resource, pk=raw_resource, is_active=True)
    tz = timezone.get_current_timezone()
    try:
        start = datetime.fromisoformat(request.POST.get("start", ""))
    except ValueError:
        return fail("invalid", _("Invalid date."))
    if timezone.is_naive(start):  # datetime-local приходит без TZ
        start = start.replace(tzinfo=tz)
    end = start + (booking.end - booking.start)  # длительность сохраняем
    try:
        services.move(
            booking,
            start=start,
            end=end,
            resource=target,
            override_hours=bool(request.POST.get("override_hours")),
        )
    except services.NotMovable:
        return fail("not_movable", _("This step is not possible in the current status."))
    except services.ResourceInactive:  # ресурс выключили между проверкой и блокировкой
        return fail("inactive_resource", _("Diese Ressource ist deaktiviert."))
    except services.SlotTaken:
        return fail("slot_taken", _("That time is already taken."))
    except services.ResourceClosed:
        return fail("closed", _("Closed on this date."))
    except services.OutsideHours:
        return fail("outside_hours", OUTSIDE_HOURS_MSG)
    except ValueError:
        return fail("invalid", _("Invalid date."))
    # Мастер без навыка — не отказ (стойка знает лучше, паритет ручной записи E4.2a).
    if (
        target is not None
        and booking.service_id
        and not availability.has_skill(booking.service, target)
    ):
        messages.warning(
            request,
            _("Hinweis: %(res)s bietet „%(svc)s“ laut Einstellungen nicht an.")
            % {"res": target.name, "svc": booking.service.name},
        )
    if is_fetch:
        return HttpResponse(status=204)
    messages.success(request, _("Booking moved."))
    return None


def _service_note_action(request, booking, action, back):
    """KA-12 E6.4b: заметка мастера к визиту (рецептура/техника) — только кабинет.
    Удалить может автор или owner/admin. Хелпер стоит ВЫШЕ декораторов вьюхи."""
    from apps.crm.models import CustomerNote

    if action == "service_note":
        text = (request.POST.get("text") or "").strip()
        if not text:
            messages.error(request, _("Bitte einen Text eingeben."))
        elif len(text) > CustomerNote.MAX_TEXT:
            messages.error(request, _("Höchstens %(n)s Zeichen.") % {"n": CustomerNote.MAX_TEXT})
        else:
            CustomerNote.objects.create(
                customer=booking.customer,
                kind=CustomerNote.KIND_SERVICE,
                booking=booking,
                service=booking.service,
                author=request.user if request.user.is_authenticated else None,
                text=text,
            )
            messages.success(request, _("Notiz gespeichert."))
        return redirect(back)
    note = get_object_or_404(
        CustomerNote,
        pk=request.POST.get("note"),
        customer=booking.customer,
        kind=CustomerNote.KIND_SERVICE,
    )
    if note.author_id != request.user.pk and not _can_edit_policy(request.user):
        raise PermissionDenied
    note.delete()
    messages.success(request, _("Notiz gelöscht."))
    return redirect(back)


@login_required
@require_POST
def booking_action(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    action = request.POST.get("action", "")
    back = f"{reverse('booking:calendar')}?tag={booking.start.date().isoformat()}"
    # Карточка брони шлёт next= — после действия остаёмся на ней (только
    # внутренние пути; чужие/абсолютные URL игнорируем).
    _next = request.POST.get("next", "")
    if (
        _next.startswith("/")
        and "\\" not in _next
        and url_has_allowed_host_and_scheme(_next, allowed_hosts={request.get_host()})
    ):
        back = _next
    if action in ("service_note", "service_note_delete"):
        return _service_note_action(request, booking, action, back)
    if action == "mark_paid":
        # KA-H6: остаток после онлайн-Anzahlung кассируется на месте (наличные/EC) —
        # зеркало stays.mark_paid; refunded не перетираем.
        if booking.payment_state == Booking.PAYMENT_REFUNDED:
            messages.error(request, _("This step is not possible in the current status."))
            return redirect(back)
        from apps.core import money_contract

        money_contract.settle_payment("booking", booking)  # KA-MC: единый путь
        messages.success(request, _("Marked as paid."))
        return redirect(back)
    if action == "move":
        resp = _move_booking(request, booking)
        return resp if resp is not None else redirect(back)
    if action == "extras":
        # MX-3: пересборка снимка допов записи; итог (total_cents) — свойство
        # модели (цена+допы−скидка), отдельного пересчёта не требует. Сентинел
        # не нужен: action=extras сам по себе явный. Оплаченная бронь с
        # изменившимся итогом получает подсказку о доплате/возврате.
        from apps.core import extras as extras_engine

        if booking.status not in (Booking.STATUS_PENDING, Booking.STATUS_CONFIRMED):
            messages.error(request, _("This step is not possible in the current status."))
            return redirect(back)
        old_total = booking.total_cents
        new_snap = extras_engine.snapshot(
            request.POST.getlist("extra"),
            "booking",
            entity_kind="service" if booking.service_id else "",
            entity_id=str(booking.service_id) if booking.service_id else "",
        )
        # MX-2e: трекеры при правке — вернуть убранное, провести добавленное.
        from apps.core import option_trackers

        try:
            option_trackers.sync_options(booking.extras, new_snap, kind="booking", deal=booking)
        except option_trackers.PoolFull as exc:
            messages.error(
                request,
                _("„%(label)s“ ist im gewählten Zeitraum leider ausgebucht.")
                % {"label": exc.label},
            )
            return redirect(back)
        except option_trackers.OptionOutOfStock as exc:
            messages.error(
                request,
                _("„%(label)s“ ist leider nicht mehr verfügbar.") % {"label": exc.label},
            )
            return redirect(back)
        booking.extras = new_snap
        booking.save(update_fields=["extras", "updated_at"])
        messages.success(request, _("Booking updated."))
        if (
            booking.payment_state in (Booking.PAYMENT_PAID, Booking.PAYMENT_DEPOSIT)
            and booking.total_cents != old_total
        ):
            diff = (booking.total_cents - old_total) / 100
            messages.warning(
                request,
                _(
                    "Der Betrag hat sich um %(diff)s € geändert — Nachzahlung oder "
                    "Erstattung mit dem Gast klären."
                )
                % {"diff": f"{diff:+.2f}"},
            )
        return redirect(back)
    if action in ("confirmed", "fulfilled", "no_show", "cancelled"):
        try:
            refund = core_transactions.apply_action(
                "booking",
                booking,
                action,
                actor=request.user,
                tenant=getattr(request, "tenant", None),
            )
        except IllegalTransition:
            messages.error(request, _("This step is not possible in the current status."))
            return redirect(back)
        except refunds.RefundNotAllowed:
            messages.error(request, str(refunds.NOT_ALLOWED_MSG))
            return redirect(back)
        messages.success(request, _("Booking updated."))
        # KA-H4: возврат депозита при отмене — в apply_action (одна точка).
        refunds.flash(request, refund, "booking")
    else:
        messages.error(request, _("Unknown action."))
    return redirect(back)


@login_required
@require_POST
def booking_create(request):
    """Ручное добавление (телефонная запись): сразу confirmed."""
    resource = get_object_or_404(Resource, pk=request.POST.get("resource"), is_active=True)
    tz = timezone.get_current_timezone()
    try:
        start = datetime.fromisoformat(request.POST.get("start", ""))
        if timezone.is_naive(start):
            start = start.replace(tzinfo=tz)
        raw_minutes = request.POST.get("minutes", "").strip()
        minutes = int(raw_minutes) if raw_minutes else None
    except (TypeError, ValueError):
        messages.error(request, _("Invalid date."))
        return redirect("booking:calendar")
    # KA-H7: услуга в ручной записи — цена/длительность из услуги (без неё запись
    # была на 0 € и 60 мин). Мусор/неактивная услуга → запись без услуги.
    service = None
    raw_service, _sep, raw_variant = request.POST.get("service", "").strip().partition(":")
    if raw_service:
        try:
            service = Service.objects.filter(pk=raw_service, is_active=True).first()
        except (ValueError, ValidationError):
            service = None
    if raw_service and service is None:
        messages.warning(request, _("Leistung nicht gefunden – Termin ohne Leistung angelegt."))
    # KA-12 E4.4b: вариант услуги — только активный вариант ЭТОЙ услуги; иначе запись
    # без варианта с предупреждением (стойку не блокируем — как с услугой выше).
    variant = None
    if service is not None and raw_variant:
        from apps.booking import pricing as _pricing

        variant, _ok = _pricing.resolve_variant(service, raw_variant)
        if not _ok:
            variant = None
            messages.warning(request, _("Variante nicht gefunden – Termin ohne Variante angelegt."))
    if minutes is None:
        if service is not None:
            from apps.booking import pricing as _pricing

            minutes = _pricing.effective_minutes(service, variant)
        else:
            minutes = 60
    minutes = max(5, min(minutes, 24 * 60))
    name = request.POST.get("name", "").strip() or _("Walk-in")
    # KA-H5: число гостей. Без него у пула мест (counts_party_size) компания из 8
    # занимала 1 место → овербукинг. Разбор как на витрине: 1..50, мусор → 1.
    try:
        party_size = max(1, min(int(request.POST.get("party_size", "1")), 50))
    except (TypeError, ValueError):
        party_size = 1
    end = start + timedelta(minutes=minutes)
    price_cents = 0
    if service is not None:
        from apps.booking import pricing

        price_cents = pricing.variant_price_cents(
            service, timezone.localtime(start).date(), variant
        )
        if service.pricing_mode == "per_person":
            price_cents *= party_size
    from apps.booking import availability

    if not request.POST.get("override_hours") and not availability.within_hours(
        resource, start, end
    ):
        # KA-12 E4.3 (О-4b): вне часов — только с подтверждением владельца.
        messages.error(request, OUTSIDE_HOURS_MSG)
        return redirect("booking:calendar")
    if resource.counts_party_size and party_size > resource.capacity:
        messages.error(
            request,
            _("Mehr Personen als Plätze (%(cap)s).") % {"cap": resource.capacity},
        )
        return redirect("booking:calendar")
    # KA-12 E4.2a: ручная запись к мастеру без этого навыка — разрешена (стойка знает
    # лучше), но с подсказкой; витрина такой выбор не предлагает вовсе.
    if service is not None and not availability.has_skill(service, resource):
        messages.warning(
            request,
            _("Hinweis: %(res)s bietet „%(svc)s“ laut Einstellungen nicht an.")
            % {"res": resource.name, "svc": service.name},
        )
    try:
        booking = services.book(
            resource,
            start=start,
            end=end,
            name=name,
            party_size=party_size,
            email=request.POST.get("email", "").strip(),
            phone=request.POST.get("phone", "").strip(),
            note=request.POST.get("note", "").strip()[:2000],
            source_channel="manual",
            auto_confirm=True,
            service=service,
            price_cents=price_cents,
            match_by_phone=True,  # KA-H7: доверенный путь (кабинет)
            variant=variant,
            variant_label=variant.name[:100] if variant is not None else "",
        )
    except services.SlotTaken:
        if resource.counts_party_size:
            from django.db.models import Sum

            taken = (
                services.overlapping(
                    resource, start, services.occupied_end(service, end) or end
                ).aggregate(s=Sum("party_size"))["s"]
                or 0
            )
            messages.error(
                request,
                _("Für %(n)s Personen sind zu dieser Zeit nur %(free)s Plätze frei.")
                % {"n": party_size, "free": max(0, resource.capacity - taken)},
            )
        else:
            messages.error(request, _("That time is already taken."))
        return redirect("booking:calendar")
    except services.ResourceClosed:
        messages.error(request, _("Closed on this date."))
        return redirect("booking:calendar")
    messages.success(request, _("Booking created."))
    return redirect(f"{reverse('booking:calendar')}?tag={booking.start.date().isoformat()}")


@login_required
def availability_calendar(request):
    """HF-4 (фидбэк владельца 2026-07-31, п. 1): визуальный календарь доступности.

    Движок закрытия дней (`ClosedDate`) и недельного расписания
    (`AvailabilityRule`) существовал давно, но управлялся списком дат в форме —
    владелец его попросту не находил и не видел картины месяца. Здесь месяц-сетка:
    клик по дню закрывает/открывает продажи на этот день (для всего бизнеса или
    выбранного ресурса), цветом видно, где расписания нет вовсе.
    """
    import calendar as _calendar
    from datetime import date as _date

    from .models import Service

    today = timezone.localdate()
    try:
        first = _date(int(request.GET.get("year") or today.year), int(request.GET["month"]), 1)
    except (TypeError, ValueError, KeyError):
        first = today.replace(day=1)
    resources_qs = list(Resource.objects.filter(is_active=True))
    chosen = next((r for r in resources_qs if str(r.pk) == request.GET.get("resource", "")), None)

    if request.method == "POST" and request.POST.get("action") == "range":
        # Фидбэк 2026-08-04: «зарезервировать даты решением владельца» — блок
        # ЦЕЛОГО диапазона (отпуск/санитарные дни) одной формой, не кликами по
        # дням. Идемпотентно; «wieder öffnen» снимает блок того же диапазона.
        from apps.core import closures

        von = _parse_day_or_none(request.POST.get("von"))
        bis = _parse_day_or_none(request.POST.get("bis"))
        if chosen is None and not _may_close_business(request):
            messages.error(request, CLOSE_BUSINESS_OWNER_ONLY)
        elif not closures.valid_range(von, bis):
            messages.error(request, _("Invalid date."))
        else:
            # KA-12 E4.1a: общий хелпер с экраном Betriebsferien (и сброс кэша витрины).
            if request.POST.get("mode") == "open":
                closures.clear_range(von, bis, resource=chosen)
                messages.success(request, _("Zeitraum wieder geöffnet."))
            else:
                closures.set_range(
                    von, bis, reason=request.POST.get("reason", "").strip(), resource=chosen
                )
                messages.success(
                    request, _("Zeitraum blockiert — diese Tage sind nicht mehr buchbar.")
                )
        return redirect(_calendar_url(first, chosen))
    if request.method == "POST":
        from apps.core import closures

        day = _parse_day_or_none(request.POST.get("date"))
        if day is None:
            messages.error(request, _("Invalid date."))
        elif chosen is None and not _may_close_business(request):
            messages.error(request, CLOSE_BUSINESS_OWNER_ONLY)
        elif ClosedDate.objects.filter(date=day, resource=chosen).exists():
            # KA-12 E4.1c: через общий хелпер — сброс кэша витрины и снимок для портала.
            closures.clear_range(day, day, resource=chosen)
            messages.success(request, _("Day reopened."))
        else:
            closures.set_range(
                day, day, reason=request.POST.get("reason", "").strip(), resource=chosen
            )
            messages.success(request, _("Sales closed for this day."))
        return redirect(_calendar_url(first, chosen))

    # Дни месяца: закрыт вручную / нет расписания на этот день недели / открыт.
    closed = {
        c.date: c
        for c in ClosedDate.objects.filter(
            date__gte=first, date__lt=first + timedelta(days=32)
        ).filter(Q(resource=chosen) | Q(resource__isnull=True))
    }
    pool = [chosen] if chosen else resources_qs
    weekdays_with_rules = set(
        AvailabilityRule.objects.filter(resource__in=pool).values_list("weekday", flat=True)
    )
    days = []
    for num in range(1, _calendar.monthrange(first.year, first.month)[1] + 1):
        day = _date(first.year, first.month, num)
        hit = closed.get(day)
        days.append(
            {
                "date": day,
                "in_past": day < today,
                "is_today": day == today,
                # Чужой ClosedDate (всего бизнеса при выбранном ресурсе) снять
                # с этой страницы нельзя — показываем, но не предлагаем клик.
                "closed": hit is not None,
                "closed_here": hit is not None
                and hit.resource_id == (chosen.pk if chosen else None),
                "reason": hit.reason if hit else "",
                "no_rules": day.weekday() not in weekdays_with_rules,
            }
        )
    prev_first = (first - timedelta(days=1)).replace(day=1)
    next_first = (first + timedelta(days=32)).replace(day=1)
    return render(
        request,
        "booking/availability.html",
        {
            "nav": "booking-availability",
            "cal_first": first,
            "cal_days": days,
            "cal_lead_blanks": range(first.weekday()),
            "prev_url": _calendar_url(prev_first, chosen),
            "next_url": _calendar_url(next_first, chosen),
            "resources": resources_qs,
            "chosen_resource": chosen,
            "has_rules": bool(weekdays_with_rules),
            "services": list(Service.objects.filter(is_active=True)[:50]),
        },
    )


def _calendar_url(first, resource=None) -> str:
    url = f"{reverse('booking:availability')}?year={first.year}&month={first.month}"
    return f"{url}&resource={resource.pk}" if resource else url


def _parse_day_or_none(raw):
    from datetime import date as _date

    try:
        return _date.fromisoformat(raw or "")
    except (TypeError, ValueError):
        return None


#: KA-12 E4.3: подсказка при записи/переносе вне часов работы.
OUTSIDE_HOURS_MSG = gettext_lazy(
    "Außerhalb der Öffnungszeiten. Zum Eintragen bitte „Trotzdem eintragen“ ankreuzen."
)


#: KA-12 (решение владельца): закрыть ВЕСЬ бизнес — только владелец; ресурс — любой.
CLOSE_BUSINESS_OWNER_ONLY = gettext_lazy(
    "Das ganze Geschäft schließen darf nur der Inhaber. Wählen Sie eine Ressource."
)


def _may_close_business(request) -> bool:
    from apps.core import roles

    return roles.is_owner(request.user)


def _business_hours_of(tenant) -> dict:
    from apps.tenants import openinghours

    return openinghours.normalize(getattr(tenant, "opening_hours_structured", None))


@login_required
def resources(request):
    """Ресурсы + недельные правила + выходные — простые POST-формы."""
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "resource":
            name = request.POST.get("name", "").strip()
            if name:
                Resource.objects.create(
                    name=name,
                    type=request.POST.get("type", Resource.TYPE_TABLE),
                    capacity=max(1, min(int(request.POST.get("capacity", "1") or 1), 100)),
                    counts_party_size=bool(request.POST.get("counts_party_size")),
                    deposit_cents=_eur_to_cents(request.POST.get("deposit_eur")),
                    require_manual_confirm=bool(request.POST.get("require_manual_confirm")),
                )
                messages.success(request, _("Resource created."))
        elif action == "rule":
            resource = get_object_or_404(Resource, pk=request.POST.get("resource"))
            try:
                AvailabilityRule.objects.create(
                    resource=resource,
                    weekday=int(request.POST.get("weekday", "0")),
                    start_time=request.POST.get("start_time") or "09:00",
                    end_time=request.POST.get("end_time") or "18:00",
                    slot_minutes=max(5, min(int(request.POST.get("slot_minutes", "30")), 480)),
                )
                messages.success(request, _("Opening hours added."))
            except (TypeError, ValueError):
                messages.error(request, _("Invalid input."))
        elif action == "rules_from_hours":
            # KA-12 E4.1b: «Aus Öffnungszeiten übernehmen» — правила дня из часов бизнеса
            # (дни, где у ресурса уже есть правило, не трогаем).
            from apps.tenants import openinghours

            hours = openinghours.normalize(
                getattr(getattr(request, "tenant", None), "opening_hours_structured", None)
            )
            created = 0
            with transaction.atomic():  # двойной клик не плодит дубли правил
                try:
                    resource = get_object_or_404(
                        Resource.objects.select_for_update(), pk=request.POST.get("resource")
                    )
                except (ValueError, ValidationError):  # кривой pk — 404, не 500
                    raise Http404 from None
                have = set(resource.rules.values_list("weekday", flat=True))
                for wd, (o, c) in hours.items():
                    if int(wd) not in have:
                        AvailabilityRule.objects.create(
                            resource=resource, weekday=int(wd), start_time=o, end_time=c
                        )
                        created += 1
            if created:
                messages.success(request, _("Opening hours added."))
            else:
                messages.info(request, _("Keine Öffnungszeiten zum Übernehmen."))
        elif action == "rule_delete":
            AvailabilityRule.objects.filter(pk=request.POST.get("rule")).delete()
        elif action == "closed":
            from apps.core import closures

            day = _parse_day_or_none(request.POST.get("date"))
            if not _may_close_business(request):
                messages.error(request, CLOSE_BUSINESS_OWNER_ONLY)
            elif day is None:
                messages.error(request, _("Invalid date."))
            else:
                closures.set_range(day, day, reason=request.POST.get("reason", "").strip())
                messages.success(request, _("Closed date added."))
        elif action == "toggle":
            resource = get_object_or_404(Resource, pk=request.POST.get("resource"))
            resource.is_active = not resource.is_active
            resource.save(update_fields=["is_active", "updated_at"])
        elif action == "resource_settings":
            resource = get_object_or_404(Resource, pk=request.POST.get("resource"))
            resource.deposit_cents = _eur_to_cents(request.POST.get("deposit_eur"))
            resource.require_manual_confirm = bool(request.POST.get("require_manual_confirm"))
            resource.counts_party_size = bool(request.POST.get("counts_party_size"))
            resource.save(
                update_fields=[
                    "deposit_cents",
                    "require_manual_confirm",
                    "counts_party_size",
                    "updated_at",
                ]
            )
            messages.success(request, _("Deposit settings saved."))
        elif action == "resource_profile":
            # A3: профиль мастера — должность, био, фото (загрузка/удаление).
            resource = get_object_or_404(Resource, pk=request.POST.get("resource"))
            resource.title = request.POST.get("title", "").strip()[:120]
            resource.bio = request.POST.get("bio", "").strip()[:2000]
            fields = ["title", "bio", "updated_at"]
            new_photo = _uploaded_image_ref(request, "photo", "staff")
            if new_photo or request.POST.get("remove_photo"):
                resource.photo = new_photo or {}
                fields.append("photo")
            resource.save(update_fields=fields)
            messages.success(request, _("Profile saved."))
        return redirect("booking:resources")

    from apps.core import status_labels, transition_rules

    return render(
        request,
        "booking/resources.html",
        {
            "nav": "booking-resources",
            "resources": Resource.objects.prefetch_related("rules").order_by("-is_active", "name"),
            "closed_dates": ClosedDate.objects.filter(date__gte=timezone.localdate()),
            "types": Resource.TYPES,
            "weekdays": AvailabilityRule.WEEKDAYS,
            "business_hours": _business_hours_of(getattr(request, "tenant", None)),
            # Фидбэк 2026-08-03: настройки уехали С календаря СЮДА («настройки —
            # в настройки»): embed-виджет + имена статусов + правила переходов.
            "embed_url": request.build_absolute_uri(reverse("storefront-termin")) + "?embed=1",
            "status_label_rows": status_labels.label_rows(
                getattr(request, "tenant", None), "booking", Booking.STATUSES
            ),
            "transition_rows": transition_rules.editor_rows(
                getattr(request, "tenant", None), "booking"
            ),
        },
    )


def _rich_lines(raw) -> list[str]:
    """Textarea «пункт на строку» → список строк (пустые выброшены).

    Нормализатор модели (`attributes_list`) всё равно режет длину и количество —
    здесь только разбор разметки формы."""
    return [line.strip() for line in (raw or "").splitlines() if line.strip()]


def _rich_lines_aligned(base_raw, tr_raw) -> list[str]:
    """Перевод-textarea → список, выровненный по ВЫЖИВШИМ строкам базовой.

    Пустые строки базы выбрасываются, поэтому перевод нельзя брать «как есть»:
    удалив пункт из середины, владелец сдвинул бы все переводы ниже него на
    чужие пункты. Берём перевод по НОМЕРУ ИСХОДНОЙ строки."""
    base_lines = (base_raw or "").splitlines()
    tr_lines = (tr_raw or "").splitlines()
    out = [
        tr_lines[i].strip() if i < len(tr_lines) else ""
        for i, line in enumerate(base_lines)
        if line.strip()
    ]
    while out and not out[-1]:
        out.pop()
    return out


def _rich_faq(post, locales) -> tuple[list[dict], dict]:
    """Пары `faq_q_<i>`/`faq_a_<i>` (+ `_<loc>` для переводов) → база и оверлеи.

    База и переводы разбираются ОДНИМ проходом: пара без вопроса отбрасывается
    (очистка вопроса = удаление пункта), и вместе с ней должен исчезнуть её
    перевод — иначе после удаления пункта из середины оставшиеся переводы
    съехали бы на соседние вопросы. Переводы пустых ключей не пишем: `overlay_seq`
    возьмёт на их месте базу.
    """
    base, per_locale = [], {loc: [] for loc in locales}
    i = 0
    while True:
        q = post.get(f"faq_q_{i}")
        a = post.get(f"faq_a_{i}")
        if q is None and a is None:
            break
        q, a = (q or "").strip(), (a or "").strip()
        if q:
            base.append({"q": q, "a": a})
            for loc in locales:
                tq = (post.get(f"faq_q_{i}_{loc}") or "").strip()
                ta = (post.get(f"faq_a_{i}_{loc}") or "").strip()
                per_locale[loc].append({k: v for k, v in (("q", tq), ("a", ta)) if v})
        i += 1
    for loc in locales:  # хвост пустых переводов не несёт информации
        while per_locale[loc] and not per_locale[loc][-1]:
            per_locale[loc].pop()
    return base, per_locale


def _rich_seq_lines(overlay, locale: str, length: int) -> list[str]:
    """Перевод списка строк на локаль, дополненный до длины базового списка.

    Ввод обязан быть выровнен по строкам базовой textarea — иначе после Save
    перевод «съедет» на соседний пункт."""
    items = (overlay or {}).get(locale) if isinstance(overlay, dict) else None
    items = list(items) if isinstance(items, (list, tuple)) else []
    items = [i if isinstance(i, str) else "" for i in items[:length]]
    return items + [""] * (length - len(items))


def _faq_rows(service, locales) -> list[dict]:
    """Строки редактора FAQ: существующие пары + одна пустая (слоты дорастают
    после Save — тот же приём, что в редакторе Finder, без JS)."""
    base = service.faq_list
    overlay = service.faq_i18n if isinstance(service.faq_i18n, dict) else {}
    rows = []
    for i, item in enumerate(base + [{"q": "", "a": ""}]):
        tr = []
        for loc in locales:
            items = overlay.get(loc)
            src = items[i] if isinstance(items, (list, tuple)) and i < len(items) else {}
            src = src if isinstance(src, dict) else {}
            tr.append(
                {
                    "locale": loc,
                    "q_name": f"faq_q_{i}_{loc}",
                    "a_name": f"faq_a_{i}_{loc}",
                    "q": src.get("q", ""),
                    "a": src.get("a", ""),
                }
            )
        rows.append(
            {
                "q_name": f"faq_q_{i}",
                "a_name": f"faq_a_{i}",
                "q": item.get("q", ""),
                "a": item.get("a", ""),
                "i18n": tr,
            }
        )
    return rows


def _clamp_int(raw, low, high) -> int:
    try:
        value = int(str(raw or "").strip() or 0)
    except ValueError:
        value = 0
    return max(low, min(high, value))


def _service_notes_for(booking, limit=3):
    """E6.4b «Beim letzten Besuch»: последние заметки мастера по ЭТОЙ услуге клиента,
    иначе — по любой (с подписью услуги)."""
    from apps.crm.models import CustomerNote

    base = CustomerNote.objects.filter(
        customer_id=booking.customer_id, kind=CustomerNote.KIND_SERVICE
    ).select_related("service", "author", "booking__resource")
    same = list(base.filter(service_id=booking.service_id)[:limit]) if booking.service_id else []
    return same or list(base[:limit])


def _can_edit_policy(user) -> bool:
    from apps.core import roles

    return roles.can_edit_policy(user)


def _is_uuid(value) -> bool:
    import uuid

    try:
        uuid.UUID(str(value))
    except ValueError:
        return False
    return True


def _clean_text(raw, limit=100) -> str:
    """Строка из формы без NUL-байтов (Postgres их отвергает) и не длиннее поля."""
    return str(raw or "").replace("\x00", "").strip()[:limit]


def _variant_action(request, action) -> None:
    """KA-12 E4.4b: мини-формы вариантов (отдельно от главного Save услуги — W0).

    Вариант ищется ВНУТРИ услуги из формы: чужой вариант → 404. Дельты — со знаком
    и потолком; вариант короче 5 минут или мусор вместо цены не сохраняются."""
    raw_service = request.POST.get("service", "")
    if not _is_uuid(raw_service):
        raise Http404
    with transaction.atomic():
        # Блокировка строки услуги сериализует правки её вариантов (лимит/уникальность).
        service = get_object_or_404(Service.objects.select_for_update(), pk=raw_service)
        _variant_action_locked(request, action, service)


def _variant_action_locked(request, action, service) -> None:
    from decimal import Decimal

    from django.db import IntegrityError

    from apps.core.money import parse_money

    from .models import (
        MAX_VARIANT_MINUTES_DELTA,
        MAX_VARIANT_PRICE_DELTA,
        MAX_VARIANTS_PER_SERVICE,
        ServiceVariant,
    )
    from .pricing import MIN_VARIANT_MINUTES

    variant = None
    if action != "variant_add":
        raw = request.POST.get("variant", "")
        if not _is_uuid(raw):
            raise Http404
        variant = get_object_or_404(ServiceVariant, pk=raw, service=service)
    if action == "variant_toggle":
        variant.is_active = not variant.is_active
        variant.save(update_fields=["is_active", "updated_at"])
        return
    if action == "variant_delete":
        variant.delete()  # брони: SET_NULL, снимок имени остаётся
        messages.success(request, _("Variant removed."))
        return
    name = _clean_text(request.POST.get("name"))
    try:
        price = parse_money(request.POST.get("price_delta_eur"))
        minutes = int((request.POST.get("duration_delta") or "0").strip() or 0)
    except ValueError:
        messages.error(request, _("Please check the surcharge and the extra minutes."))
        return
    price_cents = int(((price or Decimal(0)) * 100).quantize(Decimal(1)))
    if (
        not name
        or abs(price_cents) > MAX_VARIANT_PRICE_DELTA
        or abs(minutes) > MAX_VARIANT_MINUTES_DELTA
        or service.duration_minutes + minutes < MIN_VARIANT_MINUTES
        # Ревью S2: скидка варианта не уводит цену ниже нуля (бесплатную запись
        # владелец задаёт ценой услуги, а не «−100 €» у варианта).
        or service.price_cents + price_cents < 0
    ):
        messages.error(request, _("Please check the surcharge and the extra minutes."))
        return
    clash = ServiceVariant.objects.filter(service=service, name=name)
    if variant is not None:
        clash = clash.exclude(pk=variant.pk)
    if clash.exists():
        messages.error(request, _("A variant with this name already exists."))
        return
    tenant = getattr(request, "tenant", None)
    if variant is None:
        if service.variants.count() >= MAX_VARIANTS_PER_SERVICE:
            messages.error(request, _("Too many variants for this service."))
            return
        variant = ServiceVariant(service=service, sort_order=service.variants.count())
    variant.name = name
    variant.price_delta_cents = price_cents
    variant.duration_delta_minutes = minutes
    order = (request.POST.get("sort_order") or "").strip()
    if order.isascii() and order.isdecimal():
        variant.sort_order = min(int(order), 999)
    apply_i18n_overlay(variant, request.POST, tenant, fields=("name",))
    variant.name_i18n = {
        loc: _clean_text(val) for loc, val in (variant.name_i18n or {}).items() if _clean_text(val)
    }
    try:
        with transaction.atomic():
            variant.save()
    except IntegrityError:
        messages.error(request, _("A variant with this name already exists."))
        return
    messages.success(request, _("Variant saved."))


@login_required
def services_view(request, pk=None):
    """Услуги с ценой+длительностью (G10): CRUD простыми POST-формами.

    Фидбэк 2026-07-30: с `pk` — страница ОДНОЙ услуги (как stays:unit-edit),
    без pk — список; POST со страницы услуги возвращает на неё же."""
    from .models import Service

    def _apply_rich(service, tenant) -> list[str]:
        """Богатая карточка (UA4-3): пункты «Details» + FAQ и их переводы.

        Оба блока — под сентинелами: `action=update` шлётся и из компактной
        строки списка, где этих полей нет, а без guard'а такой Save стирал бы
        наполнение (инвариант W0)."""
        changed = []
        if request.POST.get("attributes_present"):
            base_raw = request.POST.get("attributes")
            service.attributes = _rich_lines(base_raw)
            changed.append("attributes")
            per_locale = {
                loc: _rich_lines_aligned(base_raw, request.POST[f"attributes_{loc}"])
                for loc in extra_locales(tenant)
                if f"attributes_{loc}" in request.POST
            }
            if apply_seq_overlay(service, "attributes_i18n", per_locale, tenant):
                changed.append("attributes_i18n")
        if request.POST.get("faq_present"):
            service.faq, per_locale = _rich_faq(request.POST, extra_locales(tenant))
            changed.append("faq")
            if apply_seq_overlay(service, "faq_i18n", per_locale, tenant):
                changed.append("faq_i18n")
        return changed

    def _int(raw, default, lo, hi):
        try:
            return max(lo, min(int(raw), hi))
        except (TypeError, ValueError):
            return default

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "create":
            name = request.POST.get("name", "").strip()
            if name:
                service = Service(
                    name=name,
                    description=request.POST.get("description", "").strip(),  # A3
                    image=_uploaded_image_ref(request, "image", "services")
                    or {},  # A3: фото услуги
                    duration_minutes=_int(request.POST.get("duration"), 30, 5, 1440),
                    price_cents=_eur_to_cents(request.POST.get("price_eur")),
                    # DC-8: ставка НДС услуги (DE — обычно 19 %).
                    vat_rate=vat.parse_rate(request.POST.get("vat_rate"), Decimal("19.00")),
                    deposit_cents=_eur_to_cents(request.POST.get("deposit_eur")),
                    is_video=bool(request.POST.get("is_video")),  # LS-1
                    # MX-5: режим цены (""=за бронь | per_person).
                    pricing_mode=(
                        "per_person" if request.POST.get("pricing_mode") == "per_person" else ""
                    ),
                )
                # L3d: переводы неосновных локалей (name_<loc>/description_<loc>)
                apply_i18n_overlay(service, request.POST, getattr(request, "tenant", None))
                _apply_rich(service, getattr(request, "tenant", None))
                service.save()
                messages.success(request, _("Service created."))
        elif action == "update":  # инлайн: длительность + цена + описание (депозит — при создании)
            service = get_object_or_404(Service, pk=request.POST.get("service"))
            service.duration_minutes = _int(request.POST.get("duration"), 30, 5, 1440)
            service.price_cents = _eur_to_cents(request.POST.get("price_eur"))
            # DC-8: ставка НДС — presence-guard (поле есть только в форме услуги).
            if request.POST.get("vat_rate") is not None:
                service.vat_rate = vat.parse_rate(request.POST.get("vat_rate"), service.vat_rate)
            service.description = request.POST.get("description", "").strip()  # A3
            fields = ["duration_minutes", "price_cents", "vat_rate", "description", "updated_at"]
            freshness.stamp(service)  # Г3: Save владельца = «услуга актуальна»
            fields.append("confirmed_at")
            # L3d: name правится тоже — но только если поле явно прислано
            # (presence-guard: старые клиенты формы без name не затронуты).
            new_name = request.POST.get("name")
            if new_name is not None and new_name.strip():
                service.name = new_name.strip()
                fields.append("name")
            # LS-1: чекбокс «видео» — только при сентинеле (unchecked не шлётся;
            # presence-guard спасает флаг от чужих клиентов формы без чекбокса).
            if request.POST.get("is_video_present"):
                service.is_video = bool(request.POST.get("is_video"))
                fields.append("is_video")
            if request.POST.get("hide_in_city_present"):  # T-8.11
                service.hide_in_city = bool(request.POST.get("hide_in_city"))
                fields.append("hide_in_city")
            # KA-12 E4.4a: буфер/минимальный срок/горизонт — по сентинелу (W0).
            buffer_changed = False
            if request.POST.get("booking_rules_present"):
                old_buffer = service.buffer_after_minutes
                service.buffer_after_minutes = _clamp_int(
                    request.POST.get("buffer_after_minutes"), 0, MAX_BUFFER_MINUTES
                )
                buffer_changed = service.buffer_after_minutes != old_buffer
                # Часы → минуты; те же часы, что показала форма, не округляют
                # значение, заданное в минутах другим путём.
                lead_hours = _clamp_int(request.POST.get("min_lead_hours"), 0, 720)
                if lead_hours != round(service.min_lead_minutes / 60):
                    service.min_lead_minutes = 60 * lead_hours
                horizon = (request.POST.get("max_days_ahead") or "").strip()
                if not horizon:
                    service.max_days_ahead = None
                elif horizon.isdigit() and int(horizon) > 0:
                    service.max_days_ahead = min(int(horizon), 365)
                else:  # мусор не превращаем молча в «1 день» — оставляем как было
                    messages.error(request, _("Bitte den Buchungszeitraum in Tagen angeben."))
                fields += ["buffer_after_minutes", "min_lead_minutes", "max_days_ahead"]
            # KA-12 B6: правила отмены — сентинел + роль owner/admin; поля от staff
            # молча игнорируются (новые записи берут снимок, старые не меняются).
            if request.POST.get("cancel_policy_present"):
                from .models import LATE_CANCEL_KEEP, LATE_CANCEL_REFUND, MAX_CANCEL_WINDOW_HOURS

                if _can_edit_policy(request.user):
                    service.cancel_window_hours = _clamp_int(
                        request.POST.get("cancel_window_hours"), 0, MAX_CANCEL_WINDOW_HOURS
                    )
                    late = request.POST.get("late_cancel")
                    if late in (LATE_CANCEL_KEEP, LATE_CANCEL_REFUND):
                        service.late_cancel = late
                    fields += ["cancel_window_hours", "late_cancel"]
            # MX-5: режим цены — по сентинелу (W0: чужая форма без селекта не трогает).
            if request.POST.get("pricing_mode_present"):
                service.pricing_mode = (
                    "per_person" if request.POST.get("pricing_mode") == "per_person" else ""
                )
                fields.append("pricing_mode")
            # KA-12 E4.2a: навыки (какие мастера оказывают услугу) — по сентинелу,
            # иначе компактная строка без чекбоксов стёрла бы связи (W0).
            if request.POST.get("resources_present"):
                picked = [p for p in request.POST.getlist("resources") if _is_uuid(p)]
                service.resources.set(Resource.objects.filter(pk__in=picked))
            fields += apply_i18n_overlay(service, request.POST, getattr(request, "tenant", None))
            fields += _apply_rich(service, getattr(request, "tenant", None))
            # A3: новое фото заменяет старое; чекбокс «удалить» очищает.
            new_image = _uploaded_image_ref(request, "image", "services")
            if new_image or request.POST.get("remove_image"):
                service.image = new_image or {}
                fields.append("image")
            service.save(update_fields=fields)
            if request.POST.get("booking_rules_present") and buffer_changed:
                overlaps = resync_occupancy(service)
                if overlaps:
                    messages.warning(
                        request,
                        _("Termine mit Überschneidung nach dem neuen Puffer: %(n)s")
                        % {"n": overlaps},
                    )
            messages.success(request, _("Service saved."))
        elif action == "toggle":
            service = get_object_or_404(Service, pk=request.POST.get("service"))
            service.is_active = not service.is_active
            fields = ["is_active", "updated_at"]
            if service.is_active:  # Г3: включение — тоже подтверждение
                freshness.stamp(service)
                fields.append("confirmed_at")
            service.save(update_fields=fields)
        elif action == "season_add":  # HF-5: цена услуги на диапазон дат
            service = get_object_or_404(Service, pk=request.POST.get("service"))
            start = _parse_day_or_none(request.POST.get("start_date"))
            end = _parse_day_or_none(request.POST.get("end_date"))
            price_cents = _eur_to_cents(request.POST.get("price_eur"))
            if start is None or end is None or end < start:
                messages.error(request, _("Invalid date."))
            elif price_cents <= 0:
                # Ревью HF-5: пустое/нулевое поле цены молча делало услугу в эти
                # даты БЕСПЛАТНОЙ — ноль доезжал до брони. Хочет бесплатно —
                # ставит 0 в базовой цене услуги, а не в сезонном окне.
                messages.error(request, _("Please enter a price for these dates."))
            else:
                ServiceSeasonRate.objects.create(
                    service=service,
                    label=request.POST.get("label", "").strip()[:120],
                    start_date=start,
                    end_date=end,
                    price_cents=price_cents,
                )
                messages.success(request, _("Seasonal price saved."))
        elif action == "season_delete":
            ServiceSeasonRate.objects.filter(pk=request.POST.get("season")).delete()
            messages.success(request, _("Seasonal price removed."))
        elif action in ("variant_add", "variant_update", "variant_toggle", "variant_delete"):
            _variant_action(request, action)  # KA-12 E4.4b: варианты услуги
        if pk:
            return redirect("booking:service-edit", pk=pk)
        return redirect("booking:services")

    if pk:
        service_page = get_object_or_404(Service, pk=pk)
        services = [service_page]
    else:
        service_page = None
        services = list(
            Service.objects.prefetch_related("resources", "variants").order_by("-is_active", "name")
        )
    locales = extra_locales(getattr(request, "tenant", None))
    for svc in services:  # L3d: данные per-locale инпутов готовим в Python
        svc.i18n_inputs = i18n_inputs_for(svc, getattr(request, "tenant", None))
        svc.seasons = list(svc.season_rates.all())  # HF-5: цены на диапазоны дат
        svc.variant_rows = list(svc.variants.all())  # KA-12 E4.4b
        for v in svc.variant_rows:
            v.i18n_inputs = i18n_inputs_for(v, getattr(request, "tenant", None), fields=("name",))
        # UA4-3-ввод: пункты «Details» — textarea (строка = пункт), переводы —
        # textarea на локаль, выровненная по строкам базовой.
        attrs = svc.attributes_list
        svc.attributes_text = "\n".join(attrs)
        svc.attributes_i18n_inputs = [
            {
                "locale": loc,
                "input_name": f"attributes_{loc}",
                "value": "\n".join(
                    _rich_seq_lines(svc.attributes_i18n, loc, len(attrs)),
                ),
            }
            for loc in locales
        ]
        # FAQ — пары полей: разделитель внутри свободного текста ломался бы на
        # первом же ответе с переносом строки. Одна пустая пара — чтобы добавить.
        svc.faq_rows = _faq_rows(svc, locales)
    return render(
        request,
        "booking/services.html",
        {
            "service_page": service_page,
            # X4: услуга — ПРОДАВАЕМАЯ СУЩНОСТЬ (раздел «Sortiment»), а не
            # операция дня; свой nav-ключ, иначе сайдбар подсвечивал «Verkäufe».
            "nav": "services",
            # X6-1: «＋ Neu» из «Sortiment» раскрывает форму создания.
            "open_new": request.GET.get("neu") == "1",
            "services": services,
            # KA-12 E4.2a: чекбоксы «wer bietet die Leistung an» (навыки).
            "skill_resources": list(Resource.objects.filter(is_active=True).order_by("name")),
            # KA-12 B6: блок правил отмены — только owner/admin.
            "can_edit_policy": _can_edit_policy(request.user),
            # Фидбэк 2026-07-30 («на сайте пишет: нет доступных»): без рабочих часов
            # слоты не генерируются вообще. Показываем причину ЗДЕСЬ, где владелец
            # правит услугу, — иначе он ищет «календарь услуги», которого нет.
            "has_hours": AvailabilityRule.objects.exists()
            or bool(
                _business_hours_of(getattr(request, "tenant", None))
            ),  # E4.1b: часы бизнеса — тоже окно записи
            "extra_locales": extra_locales(getattr(request, "tenant", None)),
        },
    )


@login_required
def passes_view(request):
    """Mehrfachkarten / 10er-Karten (G9): выпуск, баланс, ручное погашение."""
    from datetime import date as _date

    from .models import Pass, PassPlan, Service

    def _int(raw, default, lo, hi):
        try:
            return max(lo, min(int(raw), hi))
        except (TypeError, ValueError):
            return default

    def _cents(raw):
        try:
            return max(0, round(float(str(raw or "0").replace(",", ".")) * 100))
        except (TypeError, ValueError):
            return 0

    def _vu(raw):  # valid_until: пусто/кривое → бессрочно (None)
        try:
            return _date.fromisoformat(raw or "")
        except (TypeError, ValueError):
            return None

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "issue":
            name = request.POST.get("name", "").strip()
            if name:
                services.issue_pass(
                    name=name,
                    email=request.POST.get("email", "").strip(),
                    phone=request.POST.get("phone", "").strip(),
                    label=request.POST.get("label", "").strip() or "Mehrfachkarte",
                    credits=_int(request.POST.get("credits"), 10, 1, 100),
                    valid_until=_vu(request.POST.get("valid_until")),
                )
                messages.success(request, _("Pass issued."))
            else:
                messages.error(request, _("Please enter the customer's name."))
        elif action == "redeem":  # ручное погашение (walk-in / при визите)
            card = get_object_or_404(Pass, pk=request.POST.get("pass"))
            try:
                services.redeem_pass(card)
                messages.success(request, _("One visit redeemed."))
            except services.PassInvalid:
                messages.error(request, _("This pass has no visits left or has expired."))
        elif action == "toggle":
            card = get_object_or_404(Pass, pk=request.POST.get("pass"))
            card.is_active = not card.is_active
            card.save(update_fields=["is_active", "updated_at"])
        elif action == "plan_add":  # A3: тариф для онлайн-продажи
            label = request.POST.get("label", "").strip() or "Mehrfachkarte"
            svc = Service.objects.filter(pk=request.POST.get("service") or None).first()
            PassPlan.objects.create(
                label=label[:120],
                credits=_int(request.POST.get("credits"), 10, 1, 100),
                price_cents=_cents(request.POST.get("price")),
                valid_days=_int(request.POST.get("valid_days"), 0, 0, 3650),
                service=svc,
            )
            messages.success(request, _("Card plan added."))
        elif action == "plan_toggle":
            plan = get_object_or_404(PassPlan, pk=request.POST.get("plan"))
            plan.is_active = not plan.is_active
            plan.save(update_fields=["is_active", "updated_at"])
        return redirect("booking:passes")

    return render(
        request,
        "booking/passes.html",
        {
            "nav": "passes",  # X4: 10er-Karten/Abos — сущность раздела «Sortiment»
            "passes": Pass.objects.select_related("customer")[:300],
            "plans": PassPlan.objects.select_related("service"),
            "services": Service.objects.filter(is_active=True),
        },
    )


# --- A3: инлайн-правка услуги на канве витрины (?preview=1) ---
def _bump_storefront(request):
    """SE-5a: правка данных (не site_config) кэш не бампит — сбрасываем явно."""
    schema = getattr(getattr(request, "tenant", None), "schema_name", None)
    if schema:
        from apps.core.pagecache import bump_storefront_cache

        bump_storefront_cache(schema)


@login_required
@require_POST
def service_inline_edit(request):
    """Инлайн-правка услуги на канве — тонкий алиас единого диспетчера (UC2-4).

    Контракт/URL прежние: JSON {pk, field, value}; семантика — декларация
    INLINE_REGISTRY["service"]: name (плоско, кламп 120, пустым нельзя)/
    description; price_eur → центы; bump на всех ветках."""
    from apps.core.inline_edit import dispatch

    return dispatch(request, "service")


@login_required
@require_POST
def service_photo_edit(request):
    """UC4-3: галерея услуги на канве витрины (multipart: pk, op ∈ {replace, add,
    remove}, image_id, image). Хранение — тот же JSONField `image`: легаси-dict
    читается шимом Service.images, ЗАПИСЬ — всегда списком (без миграции). Реюз
    catalog.images.apply_gallery_op (Pillow + storage + primary-логика). 204/400."""
    from django.core.exceptions import ValidationError
    from django.db import transaction
    from django.http import HttpResponse, HttpResponseBadRequest

    from apps.catalog.images import apply_gallery_op

    from .models import Service

    pk = request.POST.get("pk")
    op = request.POST.get("op", "replace")
    image_id = request.POST.get("image_id", "")
    uploaded = request.FILES.get("image")
    if not pk:
        return HttpResponseBadRequest()
    try:
        # Блокируем строку на время read-modify-write JSON-поля (lost update).
        with transaction.atomic():
            service = Service.objects.select_for_update().get(pk=pk)
            service.image = apply_gallery_op(
                service.images, op=op, image_id=image_id, uploaded=uploaded, folder="services"
            )
            service.save(update_fields=["image", "updated_at"])
    except (Service.DoesNotExist, ValueError):
        return HttpResponseBadRequest()
    except ValidationError as exc:
        return HttpResponseBadRequest("; ".join(exc.messages))
    _bump_storefront(request)
    return HttpResponse(status=204)


def _booking_sections(request):
    """DF-1c: секция «Документы» — только при активном модуле Finanzen.

    Стенд поймал пустую рамку: у демо Finanzen выключен, счёта нет, а рамка
    рисовалась. Скелет обещает «секции по данным» — соблюдаем.
    """
    tenant = getattr(request, "tenant", None)
    try:
        finance = bool(tenant and tenant.is_module_active("finance"))
    except Exception:  # noqa: BLE001 — гейт fail-closed
        finance = False
    return (
        ("items", "discount", "totals", "payment")
        + (("documents",) if finance else ())
        + ("thread",)
    )
