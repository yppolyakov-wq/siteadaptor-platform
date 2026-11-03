"""Кабинет записи по времени (Track D / D3c): /dashboard/booking/.

Календарь-день (записи по ресурсам, навигация ±), действия по FSM
(confirm/fulfill/no_show/cancel) и перенос (services.move с anti-double-book),
ручное добавление записи (сразу confirmed), управление ресурсами: создание,
недельные правила, выходные. Гейтинг — модуль «booking» из реестра.
"""

from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

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

from apps.core import deal_links, freshness, refunds, setup_assistant, vat
from apps.core import drawer as drawer_mod
from apps.core import transactions as core_transactions
from apps.core.fsm import IllegalTransition
from apps.core.i18n_input import (
    apply_i18n_overlay,
    apply_seq_overlay,
    extra_locales,
    i18n_inputs_for,
    save_row_translations,
)
from apps.core.owner_login import local_next

from . import services, table_rules
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

# PositiveIntegerField (int32) — потолок суммы в центах; «1e999»/«1e10» не роняют
# сохранение (ECC security-review D2.2).
MAX_CENTS = 10_000_000  # 100 000 €


def _eur_to_cents(raw) -> int:
    """«5» / «5,50» → центы (анти-кривой ввод → 0, потолок MAX_CENTS)."""
    try:
        return min(MAX_CENTS, max(0, round(float(str(raw or "0").replace(",", ".")) * 100)))
    except (TypeError, ValueError, OverflowError):
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


def _can_create_booking(request) -> bool:
    from apps.core import permissions, view_perms

    user = getattr(request, "user", None)
    if user is None or not permissions.is_member(user):
        return True  # не член команды — кабинет его не пускает (прецедент can_open)
    return view_perms.allowed_quiet(user, "booking:booking-new", "POST")


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

    from apps.core import status_registry

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
        # KA-12 GA-6: вход в «Tischplan» — только где есть столы.
        "has_tables": any(r.type == Resource.TYPE_TABLE for r in resources),
        # UX-D D5.3: «＋ Neuer Termin» — только тем, кто может создать запись
        "can_create_booking": _can_create_booking(request),
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
        # UX-D D3.4: виджет, имена статусов и правила переходов отсюда не читал ни один
        # шаблон — виджет на «Buchungsregeln», статусы — на «Abläufe».
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
    # KA-12 GA-3: стол меньше компании — предупреждение, не отказ (перенос со стойки).
    from apps.booking.table_rules import seats_exceeded

    guests = booking.party_size or 1
    seats = seats_exceeded(booking.resource, guests)
    if seats:
        messages.warning(
            request,
            _("Hinweis: %(table)s hat nur %(n)s Plätze (%(guests)s Gäste).")
            % {"table": booking.resource.name, "n": seats, "guests": guests},
        )
    if is_fetch:
        return HttpResponse(status=204)
    messages.success(request, _("Booking moved."))
    return None


def _safe_next(request, default):
    """Внутренний путь из POST `next` (иначе `default`): чужие/абсолютные URL, `//host`
    и обратные слэши игнорируются. Хелпер ВЫШЕ декораторов (test_orphan_decorators)."""
    raw = request.POST.get("next", "")
    if (
        raw.startswith("/")
        and not raw.startswith("//")
        and "\\" not in raw
        and url_has_allowed_host_and_scheme(raw, allowed_hosts={request.get_host()})
    ):
        return raw
    return default


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
    raw_pk = request.POST.get("note", "")
    if not _is_uuid(raw_pk):  # ревью: мусорный pk — 404, а не 500
        raise Http404
    note = get_object_or_404(
        CustomerNote,
        pk=raw_pk,
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
    # Карточка брони/Tischplan шлют next= — после действия остаёмся на них (только
    # внутренние пути; чужие/абсолютные URL игнорируем).
    back = _safe_next(
        request, f"{reverse('booking:calendar')}?tag={booking.start.date().isoformat()}"
    )
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
    raw_resource = request.POST.get("resource", "")
    if not _is_uuid(raw_resource):  # мусорный pk — 404, а не 500
        raise Http404
    resource = get_object_or_404(Resource, pk=raw_resource, is_active=True)
    # KA-12 GA-6: walk-in с Tischplan возвращается туда же (next — только внутренний путь).
    back = _safe_next(request, reverse("booking:calendar"))
    tz = timezone.get_current_timezone()
    try:
        start = datetime.fromisoformat(request.POST.get("start", ""))
        if timezone.is_naive(start):
            start = start.replace(tzinfo=tz)
        raw_minutes = request.POST.get("minutes", "").strip()
        minutes = int(raw_minutes) if raw_minutes else None
    except (TypeError, ValueError):
        messages.error(request, _("Invalid date."))
        return redirect(back)
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
    # KA-H5: число гостей. Без него у пула мест (counts_party_size) компания из 8
    # занимала 1 место → овербукинг. Разбор как на витрине: 1..50, мусор → 1.
    try:
        party_size = max(1, min(int(request.POST.get("party_size", "1")), 50))
    except (TypeError, ValueError):
        party_size = 1
    # KA-12 A-4: ядро ручной записи — общее с «Termin anlegen» в заявке.
    try:
        booking, warnings = services.create_manual(
            resource,
            start=start,
            minutes=minutes,
            service=service,
            variant=variant,
            party_size=party_size,
            name=request.POST.get("name", "").strip(),
            email=request.POST.get("email", "").strip(),
            phone=request.POST.get("phone", "").strip(),
            note=request.POST.get("note", "").strip(),
            override_hours=bool(request.POST.get("override_hours")),
            # KA-12 GA-3: тот же флажок «Trotzdem eintragen» снимает и проверку мест.
            override_seats=bool(request.POST.get("override_hours")),
        )
    except services.ManualBookingRefused as exc:
        # Паритет: подсказка о навыке видна и при отказе (как до выноса ядра).
        for text in exc.warnings:
            messages.warning(request, text)
        messages.error(request, str(exc))
        return redirect(back)
    for text in warnings:
        messages.warning(request, text)
    messages.success(request, _("Booking created."))
    return redirect(
        _safe_next(request, f"{reverse('booking:calendar')}?tag={booking.start.date().isoformat()}")
    )


@login_required
def tischplan(request):
    """KA-12 GA-6: «Tischplan» — столы по зонам на момент времени (свободен / скоро /
    занят, «frei bis», занят через комбинацию). Только чтение: walk-in и «Tisch
    zuweisen» постят в штатные `booking-create` / `booking-action` с next=сюда."""
    from apps.core import status_registry

    from . import tischplan as plan

    day = _parse_day_any(request.GET.get("tag"))
    at = plan.default_moment(day, request.GET.get("zeit"))
    tz = timezone.get_current_timezone()
    day_start = datetime.combine(day, time.min, tzinfo=tz)
    day_end = day_start + timedelta(days=1)
    tables = list(
        Resource.objects.filter(is_active=True, type=Resource.TYPE_TABLE)
        .prefetch_related("parts")
        .order_by("zone", "sort_order", "name")
    )
    # Связи ВСЕХ комбинаций (вкл. выключенные — их брони держат столы, как в scope_ids);
    # окно — сутки + «скоро» за полночь, буфер `occupied_until` учитывается.
    links = list(Resource.parts.through.objects.values_list("from_resource_id", "to_resource_id"))
    bookings = list(
        Booking.objects.filter(
            Q(end__gt=day_start) | Q(occupied_until__gt=day_start),
            resource_id__in=plan.scope_union(tables, links),
            status__in=status_registry.active_statuses_for("booking"),
            start__lt=day_end + timedelta(minutes=plan.SOON_MINUTES),
        ).select_related("resource", "customer")
    )
    zones = plan.build(tables, bookings, at, links)
    step = timedelta(minutes=30)

    def _q(moment):
        local = timezone.localtime(moment)
        return f"?tag={local.date().isoformat()}&zeit={local:%H:%M}"

    return render(
        request,
        "booking/tischplan.html",
        {
            "nav": "tischplan",
            "zones": zones,
            "tables": tables,
            "day": day,
            "at": at,
            "prev_q": _q(at - step),
            "next_q": _q(at + step),
            "free_count": sum(1 for _z, tiles in zones for t in tiles if t.state == "free"),
            "here": request.get_full_path(),
        },
    )


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
    from apps.core.permissions import has_perm

    return has_perm(request.user, "betriebsferien.ganz")


def _business_hours_of(tenant) -> dict:
    from apps.tenants import openinghours

    return openinghours.normalize(getattr(tenant, "opening_hours_structured", None))


def _bounded_int(raw, default, lo, hi):
    """KA-12 GA-3 (фикс G9): число из формы с клампом; мусор → default, не 500."""
    try:
        return max(lo, min(int(str(raw).strip()), hi))
    except (TypeError, ValueError):
        return default


def _seats_or_none(raw, current=None):
    """Места стола: пусто/0 → None (места не проверяются); мусор — прежнее значение
    (опечатка не должна молча снимать лимит)."""
    if not str(raw or "").strip():
        return None
    value = _bounded_int(raw, -1, 0, 99)
    if value < 0:
        return current
    return value or None


def _back_to_resource(request):
    """SP-3: после сохранения — обратно к ТОЙ ЖЕ раскрытой карточке ресурса (карточки
    свёрнуты по умолчанию; без этого сохранение «закрывало» то, что правили)."""
    url = reverse("booking:resources")
    pk = request.POST.get("resource", "")
    try:
        # Канонический pk из БД, а не сырая строка POST: UUID-парсер терпит скобки,
        # "urn:uuid:", пробелы и перевод строки — в Location им не место.
        found = Resource.objects.filter(pk=pk).values_list("pk", flat=True).first() if pk else None
    except (ValueError, ValidationError):
        found = None
    if found:
        # UX-D D3.2: всё о ресурсе — на его странице; обратно на вкладку действия.
        from . import views_resources

        resource = Resource.objects.get(pk=found)
        tab = views_resources.ACTION_TAB.get(request.POST.get("action", ""))
        return redirect(views_resources.page_url(resource, tab))
    return redirect(url)


@login_required
def resources(request):
    """Ресурсы + недельные правила + выходные — простые POST-формы."""
    if request.method == "POST":
        from . import views_resources

        # UX-D D3.0: действия — модуль views_resources (1:1, + строгая предоплата)
        response = views_resources.dispatch(request, request.POST.get("action", ""))
        if response is not None:
            return response
        return _back_to_resource(request)

    from . import hours_summary

    # UX-D D3.2: старые ссылки «?open=<pk>» (закладки) → страница ресурса; мусор — список.
    wanted = request.GET.get("open", "")
    if wanted:
        try:
            found = Resource.objects.filter(pk=wanted).first()
        except (ValueError, ValidationError):
            found = None
        if found is not None:
            from . import views_resources

            return redirect(views_resources.page_url(found))
    resource_list = list(
        Resource.objects.prefetch_related("rules").order_by(
            "type", "-is_active", "sort_order", "name"
        )
    )
    for r in resource_list:
        # SP-3: сводка часов в заголовке свёрнутой карточки + группы правил.
        r.rule_groups = hours_summary.rule_groups(r.rules.all())
        r.hours_summary = hours_summary.summary(r.rule_groups)

    return render(
        request,
        "booking/resources.html",
        {
            "nav": "booking-resources",
            "resources": resource_list,
            # UX-D D3.2: при двух и более типах — группы с подзаголовками
            "resource_types_n": len({r.type for r in resource_list}),
            "closed_dates": ClosedDate.objects.filter(date__gte=timezone.localdate()).order_by(
                "date"
            )[:5],
            "business_hours": _business_hours_of(getattr(request, "tenant", None)),
            # UX-D D3.3/D3.4: правило столов и виджет — на «Buchungsregeln», статусы — на
            # «Abläufe»; закрытые дни — только чтение со ссылкой на «Tage blockieren».
            "has_tables": any(r.type == Resource.TYPE_TABLE for r in resource_list),
        },
    )


@login_required
@require_POST
def table_rules_save(request):
    """KA-12 GA-1: «Online-Tischreservierung» — до N гостей сразу, до M — Anfrage,
    больше — «bitte anrufen». Точечная запись ключа `booking.tables` под блокировкой
    строки тенанта (как no_show_rule_save: соседние правила записи целы). Выключено —
    ключа нет, поведение прежнее (всё — запрос)."""
    from apps.audit.services import audit_event
    from apps.tenants.models import Tenant
    from apps.tenants.siteconfig import normalize_booking

    # Ревью GA-1: политика приёма броней — как правило неявок, только owner/admin.
    if not _can_edit_policy(request.user):
        raise PermissionDenied
    enabled = request.POST.get("enabled") == "1"
    rule = normalize_booking(
        {
            "tables": {
                "instant_max": request.POST.get("instant_max"),
                "online_max": request.POST.get("online_max"),
            }
        }
    )["tables"]
    with transaction.atomic():
        tenant = Tenant.objects.select_for_update().get(pk=request.tenant.pk)
        tenant.auto_create_schema = False
        cfg = dict(tenant.site_config) if isinstance(tenant.site_config, dict) else {}
        section = dict(cfg.get("booking") or {})
        if enabled:
            section["tables"] = rule
        else:
            section.pop("tables", None)
        if section:
            cfg["booking"] = section
        else:
            cfg.pop("booking", None)
        tenant.site_config = cfg
        tenant.save(update_fields=["site_config", "updated_at"])
        audit_event(
            action="booking.table_rules",
            resource_type="tenant",
            resource_id=tenant.pk,
            actor=request.user,
            context={"enabled": enabled, **(rule if enabled else {})},
        )
    request.tenant.site_config = cfg
    messages.success(request, _("Gespeichert."))
    return redirect("booking:booking-rules")  # UX-D D3.3: правило живёт там


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


def _no_show_rule_ctx(tenant) -> dict:
    """Текущее правило для панели (выключено — дефолты формы 2/365)."""
    from .no_show_rule import rule, stripe_ready

    current = rule(tenant)
    return {
        "enabled": bool(current),
        "after": (current or {}).get("after", 2),
        "days": (current or {}).get("days", 365),
        "amount": ((current or {}).get("cents", 0) or 0) / 100,
        "stripe": stripe_ready(tenant),
    }


def _can_edit_policy(user) -> bool:
    from apps.core.permissions import has_perm

    return has_perm(user, "preise.edit")


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


def _service_from_post(request):
    """Новая услуга из POST (без сохранения): общий код списка (`action=create`) и
    шторки «＋ Leistung» (UX-D D2.2). Пустое имя → None."""
    from .models import Service

    name = request.POST.get("name", "").strip()[:120]  # Service.name max_length
    if not name:
        return None
    service = Service(
        name=name,
        description=request.POST.get("description", "").strip(),  # A3
        image=_uploaded_image_ref(request, "image", "services") or {},  # A3: фото услуги
        duration_minutes=_int_clamped(request.POST.get("duration"), 30, 5, 1440),
        price_cents=_eur_to_cents(request.POST.get("price_eur")),
        # DC-8: ставка НДС услуги (DE — обычно 19 %).
        vat_rate=vat.parse_rate(request.POST.get("vat_rate"), Decimal("19.00")),
        deposit_cents=_eur_to_cents(request.POST.get("deposit_eur")),
        is_video=bool(request.POST.get("is_video")),  # LS-1
        # MX-5: режим цены (""=за бронь | per_person).
        pricing_mode="per_person" if request.POST.get("pricing_mode") == "per_person" else "",
    )
    # L3d: переводы неосновных локалей (name_<loc>/description_<loc>)
    apply_i18n_overlay(service, request.POST, getattr(request, "tenant", None))
    return service


def _int_clamped(raw, default, lo, hi) -> int:
    try:
        return max(lo, min(int(raw), hi))
    except (TypeError, ValueError):
        return default


@login_required
@drawer_mod.drawer_aware
def service_new(request):
    """UX-D D2.2: «＋ Leistung» — короткая форма (имя, длительность, цена, НДС,
    предоплата); в кабинете открывается шторкой, без JS — обычная страница. После
    создания — страница услуги (фото, описание, правила — там). Пустое имя: форма
    возвращается с введённым и ошибкой у поля."""

    def render_form(values, errors=None):
        ctx = {
            "nav": "services",
            "sv": values,
            "sv_errors": errors or {},
            "next_url": drawer_mod.drawer_next(request, reverse("booking:services")),
        }
        if request.method == "POST":
            ctx["next_url"] = local_next(request) or ctx["next_url"]
        if drawer_mod.is_drawer(request) or request.GET.get("box") == "1":
            return drawer_mod.fragment(render(request, "booking/_service_new_drawer.html", ctx))
        return render(request, "booking/service_new.html", ctx)

    if request.method == "POST":
        errors = _service_new_errors(request.POST)
        service = None if errors else _service_from_post(request)
        if service is None:
            errors = errors or {"name": _("Bitte einen Namen angeben.")}
            if drawer_mod.is_drawer(request):  # шторка показывает его в role=alert
                messages.error(request, next(iter(errors.values())))
            return render_form(_service_values(request.POST), errors)
        service.save()
        messages.success(request, _("Service created."))
        return redirect(reverse("booking:service-edit", args=[service.pk]))
    return render_form(
        _service_values(setup_assistant.prefill(request, setup_assistant.ENTITY_SERVICE))
    )


def _service_new_errors(data) -> dict:
    """Ошибки у полей короткой формы: имя, цена/предоплата — числом и в разумных
    пределах, предоплата не больше цены (иначе бронь считалась бы полной оплатой).
    Старый `action=create` списка остаётся прежним (кривой ввод → 0)."""
    from apps.core.money import parse_money

    errors = {}
    if not (data.get("name") or "").strip():
        errors["name"] = _("Bitte einen Namen angeben.")
    amounts = {}
    for field in ("price_eur", "deposit_eur"):
        try:
            value = parse_money(data.get(field, ""))
        except ValueError:
            errors[field] = _("Bitte einen Betrag wie 25,00 angeben.")
            continue
        if value is not None and not (0 <= value <= MAX_CENTS / 100):
            errors[field] = _("Bitte einen Betrag zwischen 0 und 100.000 € angeben.")
            continue
        amounts[field] = value or 0
    if (
        "price_eur" in amounts
        and "deposit_eur" in amounts
        and amounts["deposit_eur"] > amounts["price_eur"]
    ):
        errors["deposit_eur"] = _("Die Anzahlung darf nicht höher als der Preis sein.")
    return errors


# UX-D D2.4: вкладки страницы услуги (первая — по умолчанию)
SERVICE_TABS = ("grund", "preise", "regeln", "text")


def _deposit_cents_or_none(raw) -> int | None:
    """Сумма формы (цена/предоплата) в центах; пусто → 0, мусор/отрицательное/сверх
    кэпа → None (вызывающий показывает ошибку и оставляет прежнее значение)."""
    from apps.core.money import parse_money

    try:
        value = parse_money(raw or "")
    except ValueError:
        return None
    if value is None:
        return 0
    if not (0 <= value <= MAX_CENTS / 100):
        return None
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _service_values(data) -> dict:
    """Значения формы «＋ Leistung» (префилл помощника или повтор после ошибки)."""
    return {
        "name": (data.get("name") or "")[:120],
        "price_eur": (data.get("price_eur") or "")[:20],
        "duration": (data.get("duration") or "")[:5],
        "deposit_eur": (data.get("deposit_eur") or "")[:20],
        "vat_rate": (data.get("vat_rate") or "")[:6],
        "pricing_mode": "per_person" if data.get("pricing_mode") == "per_person" else "",
    }


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

    if request.method == "GET" and pk is None and request.GET.get("neu") == "1":
        # UX-D D2.2: старые ссылки «＋» (?neu=1) — на форму создания, с префиллом
        params = request.GET.copy()
        params.pop("neu", None)
        query = params.urlencode()
        return redirect(reverse("booking:service-new") + (f"?{query}" if query else ""))
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "create":
            service = _service_from_post(request)
            if service is not None:
                _apply_rich(service, getattr(request, "tenant", None))
                service.save()
                messages.success(request, _("Service created."))
        elif action == "update":  # длительность + цена + описание (+ предоплата — D2.4)
            service = get_object_or_404(Service, pk=request.POST.get("service"))
            save_error = False  # ошибка поля — без зелёного «gespeichert» рядом
            service.duration_minutes = _int(request.POST.get("duration"), 30, 5, 1440)
            # Ревью D2.4: кривая цена («12,50 €», «abc») раньше молча делала услугу
            # бесплатной — теперь ошибка у владельца и прежняя цена (пусто = 0, как было).
            price = _deposit_cents_or_none(request.POST.get("price_eur"))
            if price is None:
                save_error = True
                messages.error(request, _("Bitte einen Betrag wie 25,00 angeben."))
            else:
                service.price_cents = price
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
                    save_error = True
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
            # UX-D D2.4: предоплата правится на вкладке «Buchungsregeln» — та же
            # роль (решение владельца: `preise.edit`), не выше цены; снимок на
            # уже сделанных записях не меняется (Booking.deposit_cents свой).
            if request.POST.get("deposit_present") and _can_edit_policy(request.user):
                deposit = _deposit_cents_or_none(request.POST.get("deposit_eur"))
                if deposit is None:
                    save_error = True
                    messages.error(request, _("Bitte einen Betrag wie 25,00 angeben."))
                else:
                    service.deposit_cents = deposit
                    fields.append("deposit_cents")
            # Предоплата не выше цены — и когда цену снизили (в т.ч. сотрудник без права
            # на предоплату): иначе карточка услуги показывала бы предоплату > цены.
            if service.deposit_cents > service.price_cents:
                service.deposit_cents = service.price_cents
                if "deposit_cents" not in fields:
                    fields.append("deposit_cents")
                messages.warning(request, _("Die Anzahlung wurde auf den Preis begrenzt."))
            # MX-5: режим цены — по сентинелу (W0: чужая форма без селекта не трогает).
            if request.POST.get("pricing_mode_present"):
                service.pricing_mode = (
                    "per_person" if request.POST.get("pricing_mode") == "per_person" else ""
                )
                fields.append("pricing_mode")
            # KA-12 E4.2a: навыки (какие мастера оказывают услугу) — по сентинелу,
            # иначе компактная строка без чекбоксов стёрла бы связи (W0).
            picked_resources = None
            if request.POST.get("resources_present"):
                picked = [p for p in request.POST.getlist("resources") if _is_uuid(p)]
                # чекбоксы — только у активных мастеров; связь с выключенным мастером
                # формой не видна и не должна теряться при Save (вернётся с ним)
                picked_resources = Resource.objects.filter(pk__in=picked) | (
                    service.resources.filter(is_active=False)
                )
            fields += apply_i18n_overlay(service, request.POST, getattr(request, "tenant", None))
            fields += _apply_rich(service, getattr(request, "tenant", None))
            # A3: новое фото заменяет старое; чекбокс «удалить» очищает.
            new_image = _uploaded_image_ref(request, "image", "services")
            if new_image or request.POST.get("remove_image"):
                service.image = new_image or {}
                fields.append("image")
            with transaction.atomic():
                service.save(update_fields=fields)
                if picked_resources is not None:  # M2M — после save, в одной транзакции
                    service.resources.set(picked_resources.distinct())
            if request.POST.get("booking_rules_present") and buffer_changed:
                overlaps = resync_occupancy(service)
                if overlaps:
                    messages.warning(
                        request,
                        _("Termine mit Überschneidung nach dem neuen Puffer: %(n)s")
                        % {"n": overlaps},
                    )
            if not save_error:
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
            # UX-D D2.4: обратно на ту же вкладку (белый список — мусор не в адрес)
            url = reverse("booking:service-edit", args=[pk])
            tab = request.POST.get("tab")
            if tab in SERVICE_TABS and tab != SERVICE_TABS[0]:
                url += f"?tab={tab}"
            return redirect(url)
        return redirect("booking:services")

    if not pk:
        # UX-D D2.3: список — обзор строками; per-locale инпуты/FAQ/сезоны не строим
        services = list(
            Service.objects.prefetch_related("resources", "variants").order_by("-is_active", "name")
        )
        from .pricing import variant_price_cents

        for svc in services:
            active_variants = [v for v in svc.variants.all() if v.is_active]  # prefetch
            svc.has_variants = bool(active_variants)
            # «ab» — та же функция, что витрина (apps/core/sellable._service)
            svc.list_price_eur = (
                Decimal(min(variant_price_cents(svc, None, v) for v in [None, *active_variants]))
                / 100
            )
        return render(
            request,
            "booking/services.html",
            {
                "nav": "services",
                "services": services,
                "has_hours": AvailabilityRule.objects.exists()
                or bool(_business_hours_of(getattr(request, "tenant", None))),
            },
        )
    service_page = get_object_or_404(Service.objects.prefetch_related("resources"), pk=pk)
    # навыки — множеством id: `r in s.resources.all` в цикле давал запрос на мастера
    service_page.selected_resource_ids = {r.pk for r in service_page.resources.all()}
    services = [service_page]
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
    tab = request.GET.get("tab")
    return render(
        request,
        "booking/service_page.html",
        {
            "s": service_page,
            "active_tab": tab if tab in SERVICE_TABS else SERVICE_TABS[0],
            "price_rows_n": len(service_page.seasons) + len(service_page.variant_rows),
            # значение поля предоплаты: формат цены ("12.50"), пусто = без предоплаты
            "deposit_input": (
                f"{service_page.deposit_cents / 100:.2f}" if service_page.deposit_cents else ""
            ),
            "deposit_amount": Decimal(service_page.deposit_cents) / 100,
            # X4: услуга — ПРОДАВАЕМАЯ СУЩНОСТЬ (раздел «Sortiment»), а не
            # операция дня; свой nav-ключ, иначе сайдбар подсвечивал «Verkäufe».
            "nav": "services",
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
@require_POST
def no_show_rule_save(request):
    """KA-12 E6.4c: «Anzahlung nach Nichterscheinen» — только owner/admin.

    Точечная запись ТОЛЬКО ключа `booking` под блокировкой строки тенанта (класс W6:
    чужие ключи site_config не теряются, параллельная правка не затирается).
    Выключено — ключа нет (presence-minimal)."""
    from apps.audit.services import audit_event
    from apps.core.money import parse_money
    from apps.tenants.models import Tenant
    from apps.tenants.siteconfig import normalize_booking

    if not _can_edit_policy(request.user):
        raise PermissionDenied
    enabled = request.POST.get("enabled") == "1"
    try:
        amount = parse_money(request.POST.get("amount", ""))
    except ValueError:
        amount = Decimal("-1")
    if amount is not None and not (Decimal("0") <= amount <= Decimal("1000")):
        messages.error(request, _("Bitte einen Betrag zwischen 0 und 1000 € angeben."))
        return redirect("booking:booking-rules")
    cents = int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) if amount else 0
    rule = normalize_booking(
        {
            "no_show_deposit": {
                "after": request.POST.get("after"),
                "days": request.POST.get("days"),
                "cents": cents,
            }
        }
    )
    with transaction.atomic():
        tenant = Tenant.objects.select_for_update().get(pk=request.tenant.pk)
        # Свежий экземпляр из БД: схема уже есть (по ней пришёл запрос) — без проверки
        # и создания схемы на save() (django-tenants делает это при auto_create_schema).
        tenant.auto_create_schema = False
        cfg = dict(tenant.site_config) if isinstance(tenant.site_config, dict) else {}
        section = dict(cfg.get("booking") or {})
        if enabled:
            section.update(rule)
        else:  # только своё правило: соседние правила записи (будущие) целы
            section.pop("no_show_deposit", None)
        if section:
            cfg["booking"] = section
        else:
            cfg.pop("booking", None)
        tenant.site_config = cfg
        tenant.save(update_fields=["site_config", "updated_at"])
        audit_event(
            action="booking.no_show_rule",
            resource_type="tenant",
            resource_id=tenant.pk,
            actor=request.user,
            context={"enabled": enabled, **(rule.get("no_show_deposit", {}) if enabled else {})},
        )
    request.tenant.site_config = cfg
    messages.success(request, _("Gespeichert."))
    # UX-D D2.1: правило живёт на экране «Buchungsregeln» (Einstellungen)
    return redirect("booking:booking-rules")


@login_required
def booking_rules_view(request):
    """UX-D D2.1: «Buchungsregeln» — правила записи для всех услуг в одном месте
    (раньше — свёрнутый блок над списком услуг): правило неявок и сроки бесплатной
    отмены каждой услуги (только чтение, правка — на вкладке услуги). Сотрудник
    видит правила без формы (правят owner/admin, `preise.edit`)."""
    from .models import Service

    tenant = getattr(request, "tenant", None)
    return render(
        request,
        "booking/booking_rules.html",
        {
            "nav": "booking-rules",
            "no_show_rule": _no_show_rule_ctx(tenant),
            "can_edit_policy": _can_edit_policy(request.user),
            "services": Service.objects.order_by("-is_active", "name").only(
                "pk", "name", "is_active", "cancel_window_hours", "late_cancel"
            ),
            # UX-D D3.3: правило онлайн-брони столов и виджет записи — сюда со списка
            # ресурсов (правило задаётся один раз — место в настройках, П4).
            **_table_rule_ctx(tenant),
            "embed_url": request.build_absolute_uri(reverse("storefront-termin")) + "?embed=1",
        },
    )


def _table_rule_ctx(tenant) -> dict:
    """KA-12 GA-1: правило онлайн-брони столов (карточка — когда есть хоть один стол)."""
    has_tables = Resource.objects.filter(type=Resource.TYPE_TABLE).exists()
    if not has_tables:
        return {"has_tables": False}
    return {
        "has_tables": True,
        "table_rule": table_rules.rules(tenant),
        # Ревью GA-1: «sofort» не действует при депозите стола или правиле неявок
        # (их путь подтверждает оплатой) — владелец видит это в карточке.
        "table_rule_caveat": Resource.objects.filter(
            type=Resource.TYPE_TABLE, deposit_cents__gt=0
        ).exists()
        or bool(
            (getattr(tenant, "site_config", None) or {}).get("booking", {}).get("no_show_deposit")
        ),
    }


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
            plan = PassPlan(
                label=label[:120],
                credits=_int(request.POST.get("credits"), 10, 1, 100),
                price_cents=_cents(request.POST.get("price")),
                valid_days=_int(request.POST.get("valid_days"), 0, 0, 3650),
                service=svc,
            )
            # E9.10: переводы названия тарифа (выпадашка языка у заголовка).
            apply_i18n_overlay(plan, request.POST, getattr(request, "tenant", None), ("label",))
            plan.save()
            messages.success(request, _("Card plan added."))
        elif action == "plan_i18n":  # E9.10: переводы названия тарифа под строкой
            plan = get_object_or_404(PassPlan, pk=request.POST.get("plan"))
            save_row_translations(plan, request.POST, getattr(request, "tenant", None), ("label",))
            messages.success(request, _("Saved."))
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
