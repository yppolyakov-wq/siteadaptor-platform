"""Кабинет date-range-броней (Track E / E2): /dashboard/stays/.

Календарь загрузки (юниты × ночи: свободно/занято/блок), действия по FSM
(confirm/fulfilled/no_show/cancelled) + перенос дат, ручная бронь (сразу
confirmed), управление юнитами (тип/цена/min_nights/max_guests/депозит) и
блокировками дат. Гейтинг — модуль «stays» из реестра (ModuleGatingMiddleware).
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import stripe
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.billing import connect
from apps.core import deal_card, deal_links, vat
from apps.core.fsm import IllegalTransition
from apps.core.i18n_input import apply_i18n_overlay, extra_locales, i18n_inputs_for

from . import availability, pricing, services
from .models import (
    _AMENITY_KEYS,
    AMENITIES,
    ICalSource,
    RatePlan,
    Room,
    SeasonRate,
    StayBooking,
    StaySettings,
    StayUnit,
    UnitBlock,
)
from .public_views import ical_token
from .state_machine import StayBookingSM

HORIZON_DAYS = 30  # ширина окна календаря загрузки


def _int(raw, default, lo, hi) -> int:
    try:
        return max(lo, min(int(raw), hi))
    except (TypeError, ValueError):
        return default


def _eur_to_cents(raw) -> int:
    """«80» / «79,50» → центы (анти-кривой ввод → 0)."""
    try:
        return max(0, round(float(str(raw or "0").replace(",", ".")) * 100))
    except (TypeError, ValueError):
        return 0


@login_required
def stay_new(request):
    """Фидбэк 2026-07-28: «＋ Buchung» — отдельная вкладка раздела «Verkäufe»,
    ТОЛЬКО форма добавления брони/блокировки (та же walk-in форма партиалом;
    POST идёт в stay-create, бронь появляется на календаре)."""
    return render(
        request,
        "stays/stay_new.html",
        {
            "nav": "stays",
            "units": list(StayUnit.objects.filter(is_active=True).order_by("name")),
            "rate_plans": list(RatePlan.objects.filter(is_active=True)),
            "walkin_extras": _extras_for_walkin(),
        },
    )


def _extras_for_walkin():
    """PMS-A1: активные доп-услуги stays для walk-in формы (как на витрине)."""
    from apps.core import extras as extras_engine

    return extras_engine.active_for("stays")


def _has_short_gaps(units, *, max_nights=3, horizon=60) -> bool:
    """Lücken-Deal: есть ли впереди короткие свободные промежутки между
    занятыми ночами (кандидаты на скидку) — для автопредложения владельцу."""
    today = timezone.localdate()
    start, end = today + timedelta(days=1), today + timedelta(days=1 + horizon)
    for unit in units:
        occ = availability.occupancy_by_day(unit, start, end)
        run = 0
        bounded_left = False
        day = start
        while day < end:
            if occ.get(day, 0) < 100:
                run += 1
            else:
                if bounded_left and 0 < run <= max_nights:
                    return True
                bounded_left = True
                run = 0
            day += timedelta(days=1)
    return False


def _finance_active(request) -> bool:
    tenant = getattr(request, "tenant", None)
    return bool(tenant is not None and tenant.is_module_active("finance"))


def _add_unit_photos(unit, uploaded) -> None:
    """Сохранить загруженные фото номера (до 8 на юнит). Первое фото — обложка,
    если у юнита ещё нет фото. Переиспускаем catalog.images (Pillow + storage)."""
    from apps.catalog.images import save_product_image

    if not uploaded:
        return
    images = list(unit.images or [])
    for f in uploaded[:8]:
        try:
            ref = save_product_image(
                f, is_primary=not images, sort_order=len(images), folder="stays"
            )
        except Exception:
            continue
        images.append(ref)
    if images != list(unit.images or []):
        unit.images = images[:24]
        unit.save(update_fields=["images", "updated_at"])


def _parse_day(raw) -> date:
    try:
        return date.fromisoformat(raw or "")
    except ValueError:
        return timezone.localdate()


def _is_uuid(raw) -> bool:
    try:
        uuid.UUID(str(raw))
        return True
    except (TypeError, ValueError, AttributeError):
        return False


def _refund_deposit(request, booking):
    """Анти-фрод: вернуть депозит при отмене оплаченной брони (Stripe Connect)."""
    try:
        connect.refund(
            connect_id=request.tenant.stripe_connect_id,
            payment_intent=booking.stripe_payment_intent,
        )
        booking.payment_state = StayBooking.PAYMENT_REFUNDED
        booking.save(update_fields=["payment_state", "updated_at"])
        messages.success(request, _("Deposit refunded."))
    except stripe.error.StripeError:
        messages.error(request, _("Refund failed — please check Stripe."))


@login_required
def calendar(request):
    """W10-6: легаси-вход Belegungsplan — 302 на вкладку stay единой страницы
    (GET сохраняется: ?von/?q/?buchung/?box живут на Verkäufe; тело по-прежнему
    собирает `calendar_context` — его зовёт вкладка stay)."""
    from apps.core.sales_page import legacy_redirect

    return legacy_redirect(request, tab="stay", view="kalender")


def calendar_context(request):
    """Контекст Belegungsplan (или HttpResponse-фрагмент при `?box=1`)."""
    start = _parse_day(request.GET.get("von"))
    units = list(StayUnit.objects.filter(is_active=True))
    days, rows = availability.occupancy_grid(units, start, HORIZON_DAYS)
    window_end = start + timedelta(days=HORIZON_DAYS)
    from apps.core import status_registry

    bookings = (
        StayBooking.objects.filter(
            status__in=status_registry.active_statuses_for("stay"),
            arrival__lt=window_end,
            departure__gt=start,
        )
        .select_related("unit", "customer", "room")
        .order_by("arrival")
    )
    # Батч C (Belegungsplan): плашки броней/блокировок по дорожкам поверх сетки.
    blocks = UnitBlock.objects.filter(
        unit__in=units, start_date__lt=window_end, end_date__gte=start
    ).select_related("unit")
    # PMS-аудит 2026-07-27: цвет/drag плашки — по РОЛИ статуса из реестра
    # (кастом-статус «Anzahlung erhalten» был серым и терял drag). Встроенные
    # цвета байт-в-байт прежние; кастом-active — индиго и draggable.
    # Фидбэк 2026-07-28: сплошные цвета (полупрозрачные /80-классы не попадали
    # в собранный CSS → плашки выглядели бесцветным текстом под сеткой).
    _builtin_colors = {
        "confirmed": "bg-green-200 text-green-900",
        "pending": "bg-amber-200 text-amber-900",
    }
    for b in bookings:
        d = status_registry.resolve("stay", b.status)
        # Двигать можно бронь, занимающую ёмкость (pending/confirmed/кастом-active);
        # done/cancelled — статичные плашки.
        b.bar_draggable = bool(d and d.blocks_capacity)
        b.bar_color = _builtin_colors.get(
            b.status,
            "bg-indigo-200 text-indigo-900" if b.bar_draggable else "bg-gray-200 text-gray-600",
        )
    bars = availability.booking_bars(units, start, HORIZON_DAYS, bookings, blocks)
    # PMS-R3: у категорий с комнатами шахматка построчная — дорожка на КАЖДУЮ
    # комнату (🚪label, data-room = drop-цель назначения) + безымянные «ohne
    # Zimmer»; без комнат — прежние жадные лейны (адаптер к общему виду).
    rooms_by_unit = {}
    for _r in Room.objects.filter(unit__in=units, is_active=True):
        rooms_by_unit.setdefault(_r.unit_id, []).append(_r)
    grid = []
    for unit, cells in rows:
        unit_rooms = rooms_by_unit.get(unit.id)
        if unit_rooms:
            lane_rows = availability.room_lane_rows(
                unit, unit_rooms, start, HORIZON_DAYS, bookings, blocks
            )
        else:
            lane_rows = [
                {"label": "", "room_id": None, "cells": c} for c in (bars.get(unit.id) or [])
            ]
        grid.append((unit, cells, lane_rows))
    # PMS-R2: брони «ohne Zimmer» (категория с комнатами, номер не назначен).
    _units_with_rooms = set(rooms_by_unit)
    ohne_zimmer = sum(1 for b in bookings if b.room_id is None and b.unit_id in _units_with_rooms)
    # Фидбэк 2026-07-28: поиск по гостю/почте/номеру брони (?q=) — панель
    # результатов над сеткой, любая дата/статус; ссылка открывает карточку.
    search_q = request.GET.get("q", "").strip()
    search_results = []
    if search_q:
        from django.db.models import Q as _Q

        search_results = list(
            StayBooking.objects.filter(
                _Q(customer__name__icontains=search_q)
                | _Q(customer__email__icontains=search_q)
                | _Q(reference_code__icontains=search_q)
            )
            .select_related("unit", "customer", "room")
            .order_by("-arrival")[:20]
        )
    # Фидбэк 2026-07-27: клик по плашке открывает карточку брони СРАЗУ ПОД
    # календарём (?buchung=<pk>; &box=1 — fetch-фрагмент без перезагрузки).
    selected = None
    sel_registration = None
    sel_pk = request.GET.get("buchung", "")
    if sel_pk:
        selected = (
            StayBooking.objects.select_related("unit", "customer", "rate_plan")
            .filter(pk__in=[sel_pk] if _is_uuid(sel_pk) else [])
            .first()
        )
        if selected is not None:
            try:
                sel_registration = selected.registration
            except Exception:  # noqa: BLE001 — OneToOne может отсутствовать
                sel_registration = None
    # MX-3: правка состава допов из карточки — список опций ЦЕЛЕВОГО юнита
    # (scope-wide + адресные) и уже выбранные id из снимка.
    edit_extras, chosen_extra_ids = [], set()
    if selected is not None:
        from apps.core import extras as extras_engine

        edit_extras = extras_engine.active_for(
            "stays", entity_kind="stay", entity_id=str(selected.unit_id)
        )
        chosen_extra_ids = {
            str(e.get("id")) for e in (selected.extras or []) if isinstance(e, dict) and e.get("id")
        }
    panel_ctx = {
        "b": selected,
        "registration": sel_registration,
        "can_delete": _can_delete_booking(selected) if selected else False,
        "units": units,
        # PMS-R2: селект физического номера (пусто = у категории нет комнат).
        "free_rooms": services.free_rooms_for(selected) if selected else [],
        "edit_extras": edit_extras,
        "chosen_extra_ids": chosen_extra_ids,
        # Ревью 2026-08-25: тот же партиал рендерится страницей брони, фрагментом
        # ?box=1 и телом Belegungsplan — без этих гейтов входы «Kundenkarte» и
        # «Nachricht an den Kunden» молча пропадали на шахматке (основной рабочей
        # поверхности отеля). fail-closed, как в booking_detail.
        "crm_active": bool(
            getattr(request, "tenant", None) and request.tenant.is_module_active("crm")
        ),
        "inbox_active": bool(
            getattr(request, "tenant", None) and request.tenant.is_module_active("inbox")
        ),
    }
    if request.GET.get("box") == "1":
        if selected is None:
            return HttpResponse(status=404)
        return render(request, "stays/_booking_card.html", panel_ctx)
    return {
        **{
            **panel_ctx,
            "selected_booking": selected,
            "ohne_zimmer": ohne_zimmer,
            # PMS-R4: комнаты к уборке (выезды пометили dirty).
            "dirty_rooms": Room.objects.filter(
                unit__in=units, is_active=True, housekeeping=Room.HK_DIRTY
            ).select_related("unit"),
            "nav": "stays",
            "start": start,
            "prev": start - timedelta(days=HORIZON_DAYS),
            "next": start + timedelta(days=HORIZON_DAYS),
            "today": timezone.localdate(),
            "days": days,
            "rows": rows,
            "grid": grid,
            "bookings": bookings,
            "units": units,
            "finance_active": _finance_active(request),
            # Фидбэк 2026-07-28: поиск броней.
            "search_q": search_q,
            "search_results": search_results,
            # Lücken-Deal: автопредложение, когда фича выключена, а люки есть.
            "gap_hint": (
                StaySettings.load().gap_max_nights == 0
                and bool(bookings)
                and _has_short_gaps(units)
            ),
            # PMS-A1: паритет walk-in формы с витриной — тарифы и доп-услуги.
            "rate_plans": list(RatePlan.objects.filter(is_active=True)),
            "walkin_extras": _extras_for_walkin(),
            # W9-8: мёртвые status_label_rows/transition_rows убраны (шаблон их не
            # рендерил — аудит 2026-08-05); настройки статусов — экран «Abläufe».
        },
    }


@login_required
@require_POST
def stay_action(request, pk):
    booking = get_object_or_404(StayBooking, pk=pk)
    action = request.POST.get("action", "")
    back = f"{reverse('stays:calendar')}?von={booking.arrival.isoformat()}"
    # W7c: Belegungsplan/карточка встроены в Verkäufe — форма шлёт next=, после
    # действия остаёмся на той же поверхности (только внутренние пути; зеркало
    # booking_action).
    _next = request.POST.get("next", "")
    if _next.startswith("/") and not _next.startswith("//"):
        back = _next
    if action == "invoice":  # A5: черновик Rechnung из брони (модуль finance)
        if not _finance_active(request):
            messages.error(request, _("Enable the Finance module first."))
            return redirect(back)
        small_business = getattr(request.tenant, "small_business", False)
        invoice = services.stay_to_invoice(booking, small_business=small_business)
        return redirect(reverse("finance:invoice-detail", args=[invoice.pk]))
    if action == "move":
        # Батч C: drag на Belegungsplan шлёт fetch (X-Requested-With) + опц. целевой
        # юнит; цена при drag СОХРАНЯЕТСЯ (reprice=0 — решение владельца). Кнопки
        # «Move» из списка работают как раньше (без unit, с перерасчётом).
        is_fetch = request.headers.get("X-Requested-With") == "fetch"
        target_unit = None
        unit_pk = request.POST.get("unit", "")
        if unit_pk:
            target_unit = get_object_or_404(StayUnit, pk=unit_pk, is_active=True)
        reprice = request.POST.get("reprice", "1") != "0"
        try:
            arrival = date.fromisoformat(request.POST.get("arrival", ""))
            departure = date.fromisoformat(request.POST.get("departure", ""))
            # PMS-R3: drop на строку комнаты — назначение; конфликт проверяем
            # ДО переноса (иначе drag «отскочил», а даты уже переехали).
            room_obj = None
            room_param = request.POST.get("room", "")
            if room_param:
                from apps.core import status_registry

                dest = target_unit or booking.unit
                room_obj = Room.objects.filter(
                    pk=room_param, unit_id=dest.pk, is_active=True
                ).first()
                if room_obj is not None and (
                    StayBooking.objects.filter(
                        room=room_obj,
                        status__in=status_registry.active_statuses_for("stay"),
                        arrival__lt=departure,
                        departure__gt=arrival,
                    )
                    .exclude(pk=booking.pk)
                    .exists()
                ):
                    if is_fetch:
                        return HttpResponse(_("This room is taken for those dates."), status=409)
                    messages.error(request, _("This room is taken for those dates."))
                    return redirect(back)
            services.move_stay(
                booking, arrival=arrival, departure=departure, unit=target_unit, reprice=reprice
            )
            if room_obj is not None:
                try:
                    services.assign_room(booking, room_obj)
                except services.RoomConflict:  # гонка — перенос состоялся, номер нет
                    pass
            elif booking.room_id and booking.room_id not in {
                r.id for r in services.free_rooms_for(booking)
            }:
                services.assign_room(booking, None)  # даты переехали в конфликт
            if is_fetch:
                return HttpResponse(status=204)
            messages.success(request, _("Stay moved."))
        except ValueError:
            if is_fetch:
                return HttpResponse(_("Invalid dates."), status=409)
            messages.error(request, _("Invalid dates."))
        except services.MinStay:
            if is_fetch:
                return HttpResponse(_("Below the minimum number of nights."), status=409)
            messages.error(request, _("Below the minimum number of nights."))
        except services.MaxGuests:
            if is_fetch:
                return HttpResponse(_("Too many guests for this unit."), status=409)
            messages.error(request, _("Too many guests for this unit."))
        except services.StayUnavailable:
            if is_fetch:
                return HttpResponse(_("Those dates are no longer available."), status=409)
            messages.error(request, _("Those dates are no longer available."))
        return redirect(back)
    if action == "update":
        # Фидбэк 2026-07-27: форма «Buchung bearbeiten» — даты/номер/гости/заметка
        # одним сохранением. Даты/номер — через move_stay (те же локи и
        # anti-oversell); гости валидируются вместимостью; walk-in-правки
        # владельца Verkaufsregeln НЕ гейтят (как и создание).
        if booking.status not in (StayBooking.STATUS_PENDING, StayBooking.STATUS_CONFIRMED):
            messages.error(request, _("This step is not possible in the current status."))
            return redirect(back)
        target_unit = booking.unit
        unit_pk = request.POST.get("unit", "")
        if unit_pk and str(booking.unit_id) != unit_pk:
            target_unit = get_object_or_404(StayUnit, pk=unit_pk, is_active=True)
        adults = _int(request.POST.get("adults", str(booking.adults)), booking.adults, 1, 50)
        children = _int(
            request.POST.get("children", str(booking.children)), booking.children, 0, 50
        )
        if adults + children > target_unit.max_guests * booking.rooms:
            messages.error(request, _("Too many guests for this unit."))
            return redirect(back)
        reprice = bool(request.POST.get("reprice"))
        try:
            arrival = date.fromisoformat(request.POST.get("arrival", ""))
            departure = date.fromisoformat(request.POST.get("departure", ""))
        except ValueError:
            messages.error(request, _("Invalid dates."))
            return redirect(back)
        # Гости/заметка — ДО move_stay: перерасчёт (Kurtaxe по adults) увидит
        # свежие значения.
        booking.adults = adults
        booking.children = children
        booking.guests = adults + children
        booking.note = request.POST.get("note", "").strip()[:2000]
        booking.save(update_fields=["adults", "children", "guests", "note", "updated_at"])
        # MX-3: правка состава допов — только при сентинеле (форма без блока допов
        # ничего не стирает, инвариант W0). Изменённый состав ТРЕБУЕТ пересчёта:
        # менять допы с «ценой как была» значило бы рассинхронизировать итог.
        old_total = booking.total_cents
        if request.POST.get("extras_present"):
            from apps.core import extras as extras_engine

            new_snap = extras_engine.snapshot(
                request.POST.getlist("extra"),
                "stays",
                nights=max((departure - arrival).days, 1),
                entity_kind="stay",
                entity_id=str(target_unit.pk),
            )
            old_ids = [str(e.get("id", "")) for e in (booking.extras or []) if isinstance(e, dict)]
            if sorted(e["id"] for e in new_snap) != sorted(old_ids):
                # MX-2e: убранные трекер-опции вернуть, добавленные — провести
                # (пул/склад); отказ оставляет бронь без изменений.
                from apps.core import option_trackers

                try:
                    option_trackers.sync_options(
                        booking.extras, new_snap, kind="stay", deal=booking
                    )
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
                reprice = True
        try:
            services.move_stay(
                booking,
                arrival=arrival,
                departure=departure,
                unit=target_unit,
                reprice=reprice,
            )
            # PMS-R2: назначение физического номера (после переноса — даты
            # финальные). Селект другой категории (unit сменился) — устарел,
            # игнорируем: комнату уже сбросил move_stay.
            room_obj = None
            room_pk = request.POST.get("room", "")
            if room_pk:
                room_obj = Room.objects.filter(pk=room_pk, unit_id=booking.unit_id).first()
            if room_obj is not None or not room_pk:
                try:
                    services.assign_room(booking, room_obj)
                except services.RoomConflict:
                    messages.error(request, _("This room is taken for those dates."))
            messages.success(request, _("Stay updated."))
            # MX-3: оплаченная бронь + изменившийся итог — владельцу нужна
            # дельта (доплата/возврат вручную; авто-чарджа нет осознанно).
            booking.refresh_from_db()
            if booking.payment_state == StayBooking.PAYMENT_PAID and (
                booking.total_cents != old_total
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
        except services.MinStay:
            messages.error(request, _("Below the minimum number of nights."))
        except services.MaxGuests:
            messages.error(request, _("Too many guests for this unit."))
        except services.StayUnavailable:
            messages.error(request, _("Those dates are no longer available."))
        except ValueError:
            messages.error(request, _("Invalid dates."))
        # von — по АКТУАЛЬНОМУ заезду (move_stay мог его изменить); панель брони
        # остаётся открытой под календарём (?buchung=).
        return redirect(
            f"{reverse('stays:calendar')}?von={booking.arrival.isoformat()}&buchung={booking.pk}"
        )
    if action == "mark_paid":
        # PMS-A3: оплата на стойке (наличные/карта) — образец orders.mark_paid.
        # refunded не перетираем; Stripe-пути (вебхук/refund) не трогаются.
        if booking.payment_state == StayBooking.PAYMENT_REFUNDED:
            messages.error(request, _("This step is not possible in the current status."))
            return redirect(back)
        booking.payment_state = StayBooking.PAYMENT_PAID
        booking.save(update_fields=["payment_state", "updated_at"])
        messages.success(request, _("Marked as paid."))
        # Панель брони остаётся открытой (как у action=update).
        return redirect(f"{back}&buchung={booking.pk}")
    if action in ("confirmed", "fulfilled", "no_show", "cancelled"):
        try:
            StayBookingSM().apply(booking, action, actor=request.user)
        except IllegalTransition:
            messages.error(request, _("This step is not possible in the current status."))
            return redirect(back)
        messages.success(request, _("Stay updated."))
        # анти-фрод: отмена оплаченной брони возвращает депозит (E4 wires Stripe)
        if (
            action == "cancelled"
            and booking.payment_state == StayBooking.PAYMENT_PAID
            and booking.stripe_payment_intent
        ):
            _refund_deposit(request, booking)
    else:
        messages.error(request, _("Unknown action."))
    return redirect(back)


@login_required
@require_POST
def stay_create(request):
    """Ручное добавление (телефонная/личная бронь): сразу confirmed.

    Батч C: та же форма умеет «Blockieren» (mode=block) — вместо брони создаёт
    UnitBlock на выбранный диапазон (ремонт/своё проживание); поле имени служит
    причиной. departure эксклюзивен → end_date = departure − 1 (включителен)."""
    unit = get_object_or_404(StayUnit, pk=request.POST.get("unit"), is_active=True)
    # W7c: walk-in-форма встроена и в Verkäufe — next= возвращает туда же
    # (только внутренние пути); без next — прежний stays:calendar.
    _next = request.POST.get("next", "")
    back = _next if (_next.startswith("/") and not _next.startswith("//")) else None
    try:
        arrival = date.fromisoformat(request.POST.get("arrival", ""))
        departure = date.fromisoformat(request.POST.get("departure", ""))
    except ValueError:
        messages.error(request, _("Invalid dates."))
        return redirect(back or "stays:calendar")
    if request.POST.get("mode") == "block":
        if departure <= arrival:
            messages.error(request, _("Invalid dates."))
            return redirect(back or "stays:calendar")
        UnitBlock.objects.create(
            unit=unit,
            start_date=arrival,
            end_date=departure - timedelta(days=1),
            reason=request.POST.get("name", "").strip()[:120],
        )
        messages.success(request, _("Dates blocked."))
        return redirect(back or f"{reverse('stays:calendar')}?von={arrival.isoformat()}")
    name = request.POST.get("name", "").strip() or _("Walk-in")
    # PMS-A1: паритет со витриной — взрослые/дети (Kurtaxe по взрослым!), тариф,
    # extras, несколько номеров, промокод. Легаси-поле guests остаётся фолбэком
    # (= взрослые). G12-ограничения на стойку осознанно НЕ действуют.
    adults = _int(request.POST.get("erw", "") or request.POST.get("guests", "1"), 1, 1, 50)
    children = _int(request.POST.get("kinder", "0"), 0, 0, 50)
    rate_plan = None
    active_rates = list(RatePlan.objects.filter(is_active=True))
    if active_rates:
        rate_pk = request.POST.get("rate_plan")
        rate_plan = next((r for r in active_rates if str(r.pk) == str(rate_pk)), active_rates[0])
    from apps.core import extras as extras_engine

    extras_snap = extras_engine.snapshot(
        request.POST.getlist("extra"),
        "stays",
        nights=max((departure - arrival).days, 1),
        entity_kind="stay",
        entity_id=str(unit.pk),
    )
    try:
        booking = services.book_stay(
            unit,
            arrival=arrival,
            departure=departure,
            name=name,
            email=request.POST.get("email", "").strip(),
            phone=request.POST.get("phone", "").strip(),
            adults=adults,
            children=children,
            note=request.POST.get("note", "").strip()[:2000],
            source_channel="manual",
            auto_confirm=True,
            extras=extras_snap,
            rate_plan=rate_plan,
            voucher_code=request.POST.get("voucher_code", "").strip(),
            rooms=_int(request.POST.get("rooms", "1"), 1, 1, 20),
        )
    except services.MinStay:
        messages.error(request, _("Below the minimum number of nights."))
        return redirect(back or "stays:calendar")
    except services.MaxGuests:
        messages.error(request, _("Too many guests for this unit."))
        return redirect(back or "stays:calendar")
    except services.StayUnavailable:
        messages.error(request, _("Those dates are no longer available."))
        return redirect(back or "stays:calendar")
    except services.PromoInvalid:
        # Раньше неверный промокод на стойке ронял 500 — теперь честная ошибка.
        messages.error(request, _("This promo code is not valid for this booking."))
        return redirect(back or "stays:calendar")
    except ValueError:
        messages.error(request, _("Invalid dates."))
        return redirect(back or "stays:calendar")
    messages.success(request, _("Stay created."))
    return redirect(back or f"{reverse('stays:calendar')}?von={booking.arrival.isoformat()}")


@login_required
def today_view(request):
    """W10-6: PMS-A2 «Heute» поглощён kind-агностичным видом единой страницы
    (verkaeufe?view=heute — Anreisen/Abreisen/Im Haus там же, W10-4/W10-6)."""
    from apps.core.sales_page import legacy_redirect

    return legacy_redirect(request, view="heute")


@login_required
def booking_detail(request, pk):
    """FB-11: карточка брони — кто/когда/сколько (гость, даты, суммы, оплата,
    тариф, источник, Meldeschein) + действия статуса. Ссылки: календарь, доска."""
    booking = get_object_or_404(
        StayBooking.objects.select_related("unit", "customer", "rate_plan"), pk=pk
    )
    try:
        registration = booking.registration
    except Exception:  # noqa: BLE001 — OneToOne может отсутствовать
        registration = None
    return render(
        request,
        "stays/booking_detail.html",
        {
            "b": booking,
            "registration": registration,
            # Фидбэк 2026-07-30: разбивка цены ПО НОЧАМ (сезоны/выходные) —
            # владелец видит, из чего сложился итог мультисезонной брони.
            "price_rows": pricing.price_breakdown(
                booking.unit, booking.arrival, booking.departure, rate_plan=booking.rate_plan
            )
            if booking.unit_id
            else [],
            "nav": "stays",
            "can_delete": _can_delete_booking(booking),
            # Фидбэк 2026-07-27: селект номера в форме «Buchung bearbeiten».
            "units": list(StayUnit.objects.filter(is_active=True).order_by("name")),
            # PMS-R2: селект физического номера (пусто = у категории нет комнат).
            "free_rooms": services.free_rooms_for(booking),
            # DC-1: общий скелет карточки сделки — голова, статус, клиент, связи
            # и Belegungsplan под сеткой приходят из одного источника.
            **deal_card.card_context(
                request,
                "stay",
                booking,
                sections=_stay_sections(request),
                # VS-3: прикреплённые услуги (велопрокат/трансфер к брони номера).
                links=deal_links.block_context("stay", booking.pk),
            ),
        },
    )


def _can_delete_booking(booking) -> bool:
    """Батч C (решение владельца): hard-delete ТОЛЬКО для ручных броней без денег —
    manual-канал, не оплачена, без Stripe-интента и без счёта (GoBD: брони с
    деньгами/документами не удаляются — только отмена, запись остаётся)."""
    return (
        booking.source_channel == "manual"
        and booking.payment_state != StayBooking.PAYMENT_PAID
        and not booking.stripe_payment_intent
        and booking.invoice_id is None
    )


@login_required
@require_POST
def room_clean(request, pk):
    """PMS-R4 (хаускипинг-lite): отметить комнату убранной (→ clean)."""
    room = get_object_or_404(Room, pk=pk)
    room.housekeeping = Room.HK_CLEAN
    room.save(update_fields=["housekeeping", "updated_at"])
    messages.success(request, _("Room marked clean."))
    return redirect("stays:calendar")


@login_required
@require_POST
def booking_delete(request, pk):
    """Батч C: удалить ручную бронь без денег (гейт _can_delete_booking)."""
    booking = get_object_or_404(StayBooking, pk=pk)
    if not _can_delete_booking(booking):
        messages.error(request, _("Only manual, unpaid bookings can be deleted."))
        return redirect("stays:booking-detail", pk=pk)
    back = f"{reverse('stays:calendar')}?von={booking.arrival.isoformat()}"
    booking.delete()
    messages.success(request, _("Booking deleted."))
    return redirect(back)


@login_required
def units(request, pk=None):
    """Юниты + блокировки дат — POST-формы. Фидбэк 2026-07-28: с pk —
    страница редактирования ОДНОГО номера (формы постят на неё же и
    возвращаются на неё); без pk — компактный список + глобальные настройки."""
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "unit":
            name = request.POST.get("name", "").strip()
            if name:
                unit = StayUnit.objects.create(
                    name=name,
                    type=request.POST.get("type", StayUnit.TYPE_ROOM),
                    description=request.POST.get("description", "").strip()[:5000],
                    quantity=_int(request.POST.get("quantity", "1"), 1, 1, 999),
                    price_cents=_eur_to_cents(request.POST.get("price_eur")),
                    weekend_price_cents=_eur_to_cents(request.POST.get("weekend_price_eur")),
                    # DC-8: ставка НДС номера (DE — проживание 7 %).
                    vat_rate=vat.parse_rate(request.POST.get("vat_rate"), Decimal("7.00")),
                    min_nights=_int(request.POST.get("min_nights", "1"), 1, 1, 365),
                    max_guests=_int(request.POST.get("max_guests", "2"), 2, 1, 99),
                    deposit_cents=_eur_to_cents(request.POST.get("deposit_eur")),
                    require_manual_confirm=bool(request.POST.get("require_manual_confirm")),
                    area_sqm=_int(request.POST.get("area_sqm", "0"), 0, 0, 9999),
                    bed_type=request.POST.get("bed_type", "").strip()[:80],
                    amenities=[a for a in request.POST.getlist("amenities") if a in _AMENITY_KEYS],
                )
                # L3d: переводы неосновных локалей (после create — поля JSON)
                if apply_i18n_overlay(unit, request.POST, getattr(request, "tenant", None)):
                    unit.save(update_fields=["name_i18n", "description_i18n", "updated_at"])
                _add_unit_photos(unit, request.FILES.getlist("photos"))
                messages.success(request, _("Unit created."))
                # Новый номер — сразу на его страницу редактирования.
                return redirect("stays:unit-edit", pk=unit.pk)
        elif action == "unit_settings":
            unit = get_object_or_404(StayUnit, pk=request.POST.get("unit"))
            unit.description = request.POST.get("description", "").strip()[:5000]
            # L3d: name правится при явно присланном поле (presence-guard).
            _new_name = request.POST.get("name")
            if _new_name is not None and _new_name.strip():
                unit.name = _new_name.strip()[:120]
            unit.price_cents = _eur_to_cents(request.POST.get("price_eur"))
            unit.weekend_price_cents = _eur_to_cents(request.POST.get("weekend_price_eur"))
            # DC-8: ставка НДС — presence-guard (поле только на странице номера).
            if request.POST.get("vat_rate") is not None:
                unit.vat_rate = vat.parse_rate(request.POST.get("vat_rate"), unit.vat_rate)
            unit.quantity = _int(request.POST.get("quantity", "1"), 1, 1, 999)
            # PMS-R1: при заведённых комнатах ёмкость считается по ним —
            # ручной ввод quantity игнорируется (поле в форме read-only).
            if unit.rooms.exists():
                unit.quantity = unit.rooms.filter(is_active=True).count()
            unit.min_nights = _int(request.POST.get("min_nights", "1"), 1, 1, 365)
            unit.max_guests = _int(request.POST.get("max_guests", "2"), 2, 1, 99)
            unit.deposit_cents = _eur_to_cents(request.POST.get("deposit_eur"))
            # Фидбэк 2026-07-30: Lücken-Deal для КОНКРЕТНОГО номера (0 = как в
            # общих настройках). Presence-guard: поля приходят только со страницы
            # номера — на списке значения не затираются.
            if request.POST.get("gap_present"):
                unit.gap_max_nights = _int(request.POST.get("gap_max_nights", "0"), 0, 0, 14)
                unit.gap_discount_percent = _int(
                    request.POST.get("gap_discount_percent", "0"), 0, 0, 70
                )
            unit.require_manual_confirm = bool(request.POST.get("require_manual_confirm"))
            unit.area_sqm = _int(request.POST.get("area_sqm", "0"), 0, 0, 9999)
            unit.bed_type = request.POST.get("bed_type", "").strip()[:80]
            unit.amenities = [a for a in request.POST.getlist("amenities") if a in _AMENITY_KEYS]
            _uf = [
                "name",
                "description",
                "price_cents",
                "weekend_price_cents",
                "vat_rate",
                "quantity",
                "min_nights",
                "max_guests",
                "deposit_cents",
                "require_manual_confirm",
                "area_sqm",
                "bed_type",
                "amenities",
                "updated_at",
            ]
            _uf += apply_i18n_overlay(unit, request.POST, getattr(request, "tenant", None))  # L3d
            unit.save(update_fields=_uf)
            _add_unit_photos(unit, request.FILES.getlist("photos"))
            messages.success(request, _("Unit saved."))
        elif action == "photo_delete":
            unit = get_object_or_404(StayUnit, pk=request.POST.get("unit"))
            from apps.catalog.images import delete_stored_image

            ref_id = request.POST.get("image")
            keep = [i for i in unit.images if str(i.get("id")) != str(ref_id)]
            for i in unit.images:
                if str(i.get("id")) == str(ref_id):
                    delete_stored_image(i)
            if keep and not any(i.get("is_primary") for i in keep):
                keep[0]["is_primary"] = True  # обложка не должна потеряться
            unit.images = keep
            unit.save(update_fields=["images", "updated_at"])
        elif action == "rate":  # A5a: сезонный тариф
            unit = get_object_or_404(StayUnit, pk=request.POST.get("unit"))
            try:
                start_date = date.fromisoformat(request.POST.get("start_date", ""))
                end_date = date.fromisoformat(request.POST.get("end_date", ""))
                if end_date < start_date:
                    raise ValueError
                SeasonRate.objects.create(
                    unit=unit,
                    label=request.POST.get("label", "").strip()[:120],
                    start_date=start_date,
                    end_date=end_date,
                    price_cents=_eur_to_cents(request.POST.get("price_eur")),
                )
                messages.success(request, _("Season rate added."))
            except (TypeError, ValueError):
                messages.error(request, _("Invalid dates."))
        elif action == "rate_delete":
            SeasonRate.objects.filter(pk=request.POST.get("rate")).delete()
        elif action == "toggle":
            unit = get_object_or_404(StayUnit, pk=request.POST.get("unit"))
            unit.is_active = not unit.is_active
            unit.save(update_fields=["is_active", "updated_at"])
        elif action == "block":
            unit = get_object_or_404(StayUnit, pk=request.POST.get("unit"))
            try:
                start_date = date.fromisoformat(request.POST.get("start_date", ""))
                end_date = date.fromisoformat(request.POST.get("end_date", ""))
                if end_date < start_date:
                    raise ValueError
                UnitBlock.objects.create(
                    unit=unit,
                    start_date=start_date,
                    end_date=end_date,
                    reason=request.POST.get("reason", "").strip()[:120],
                )
                messages.success(request, _("Dates blocked."))
            except (TypeError, ValueError):
                messages.error(request, _("Invalid dates."))
        elif action == "block_delete":
            UnitBlock.objects.filter(pk=request.POST.get("block")).delete()
        elif action == "room_add":  # PMS-R1: физический номер категории («101»)
            unit = get_object_or_404(StayUnit, pk=request.POST.get("unit"))
            number = request.POST.get("number", "").strip()[:40]
            if number:
                Room.objects.get_or_create(unit=unit, number=number)
                services.sync_room_quantity(unit)
                messages.success(request, _("Room added."))
        elif action == "room_delete":  # PMS-R1: удалить комнату + синк ёмкости
            room = get_object_or_404(Room, pk=request.POST.get("room"))
            room_unit = room.unit
            room.delete()
            services.sync_room_quantity(room_unit)
        elif action == "ical_add":  # A5b: подписка на внешний iCal-фид
            unit = get_object_or_404(StayUnit, pk=request.POST.get("unit"))
            url = request.POST.get("url", "").strip()
            if url:
                ICalSource.objects.create(
                    unit=unit,
                    label=request.POST.get("label", "").strip()[:80],
                    url=url[:500],
                )
                messages.success(request, _("Calendar source added — will sync shortly."))
            else:
                messages.error(request, _("Please enter the calendar URL."))
        elif action == "ical_delete":
            src = ICalSource.objects.filter(pk=request.POST.get("source")).first()
            if src is not None:
                # убрать заведённые им блоки вместе с источником
                UnitBlock.objects.filter(unit=src.unit, source_id_ref=str(src.pk)).delete()
                src.delete()
        elif action == "ical_sync":
            src = get_object_or_404(ICalSource, pk=request.POST.get("source"))
            n = services.sync_ical_source(src)
            messages.success(request, _("Synced: %(n)d blocked range(s).") % {"n": n})
        elif action == "rateplan":  # H1: тариф (на тенанта, для всех номеров)
            name = request.POST.get("name", "").strip()
            if name:
                RatePlan.objects.create(
                    name=name[:120],
                    description=request.POST.get("description", "").strip()[:300],
                    percent_adjust=_int(request.POST.get("percent_adjust", "0"), 0, -90, 200),
                    surcharge_cents=_eur_to_cents(request.POST.get("surcharge_eur")),
                    meal_plan=request.POST.get("meal_plan", RatePlan.MEAL_NONE),
                    cancellation=request.POST.get("cancellation", RatePlan.CANCEL_FLEXIBLE),
                    free_cancel_days=_int(request.POST.get("free_cancel_days", "0"), 0, 0, 365),
                    prepayment_percent=_int(request.POST.get("prepayment_percent", "0"), 0, 0, 100),
                    sort_order=_int(request.POST.get("sort_order", "0"), 0, 0, 999),
                )
                messages.success(request, _("Rate plan added."))
            else:
                messages.error(request, _("Please enter a rate plan name."))
        elif action == "rateplan_toggle":
            rp = get_object_or_404(RatePlan, pk=request.POST.get("rateplan"))
            rp.is_active = not rp.is_active
            rp.save(update_fields=["is_active", "updated_at"])
            messages.success(request, _("Settings saved."))
        elif action == "rateplan_delete":
            RatePlan.objects.filter(pk=request.POST.get("rateplan")).delete()
            messages.success(request, _("Settings saved."))
        elif action == "card_amenities":  # HF-2: пиктограммы удобств на карточке номера
            from apps.tenants import siteconfig

            tenant = request.tenant
            keys = siteconfig.normalize_card_amenities(request.POST.getlist("card_amenity"))
            # Targeted-write (как board_settings): прочие ключи site_config целы.
            cfg = dict(tenant.site_config) if isinstance(tenant.site_config, dict) else {}
            if keys:
                cfg["stay_card_amenities"] = keys
            else:
                cfg.pop("stay_card_amenities", None)  # пусто = дефолт, ключ не храним
            tenant.site_config = cfg
            tenant.save(update_fields=["site_config", "updated_at"])
            messages.success(request, _("Settings saved."))
        elif action == "kurtaxe":  # H9 Kurtaxe + H6 Hausordnung
            settings_obj = StaySettings.load()
            settings_obj.kurtaxe_cents = _eur_to_cents(request.POST.get("kurtaxe_eur"))
            settings_obj.kurtaxe_label = (
                request.POST.get("kurtaxe_label", "").strip()[:80] or "Kurtaxe"
            )
            settings_obj.house_rules = request.POST.get("house_rules", "").strip()[:8000]
            settings_obj.save(
                update_fields=["kurtaxe_cents", "kurtaxe_label", "house_rules", "updated_at"]
            )
            messages.success(request, _("Settings saved."))
        elif action == "autodiscount_add":  # G4: добавить правило авто-скидки
            settings_obj = StaySettings.load()
            kind = request.POST.get("kind", "")
            valid_kinds = {k for k, _ in StaySettings.AUTO_DISCOUNT_KINDS}
            threshold = _int(request.POST.get("threshold", "0"), 0, 1, 365)
            percent = _int(request.POST.get("percent", "0"), 0, 1, 90)
            if kind in valid_kinds and threshold and percent:
                rules = settings_obj.clean_auto_rules()
                rules.append({"kind": kind, "threshold": threshold, "percent": percent})
                settings_obj.auto_discount_rules = rules
                settings_obj.save(update_fields=["auto_discount_rules", "updated_at"])
                messages.success(request, _("Discount rule added."))
            else:
                messages.error(request, _("Please fill in the discount rule."))
        elif action == "autodiscount_delete":  # G4: удалить правило по индексу
            settings_obj = StaySettings.load()
            rules = settings_obj.clean_auto_rules()
            idx = _int(request.POST.get("index", "-1"), -1, 0, len(rules) - 1)
            if 0 <= idx < len(rules):
                rules.pop(idx)
                settings_obj.auto_discount_rules = rules
                settings_obj.save(update_fields=["auto_discount_rules", "updated_at"])
                messages.success(request, _("Settings saved."))
        elif action == "booking_window":  # G12: окно бронирования (глубина + мин. срок)
            settings_obj = StaySettings.load()
            settings_obj.max_advance_days = _int(
                request.POST.get("max_advance_days", "0"), 0, 0, 365
            )
            settings_obj.min_advance_days = _int(
                request.POST.get("min_advance_days", "0"), 0, 0, 90
            )
            settings_obj.save(update_fields=["max_advance_days", "min_advance_days", "updated_at"])
            messages.success(request, _("Settings saved."))
        elif action == "restriction_add":  # G12: правило продаж (Verkaufsregel)
            settings_obj = StaySettings.load()
            rule = {
                "start": request.POST.get("start", "").strip()[:10],
                "end": request.POST.get("end", "").strip()[:10],
                "unit": request.POST.get("unit", "").strip()[:40],
                "min_nights": _int(request.POST.get("min_nights", "0"), 0, 0, 365),
                "max_nights": _int(request.POST.get("max_nights", "0"), 0, 0, 365),
                "no_checkin": request.POST.getlist("no_checkin"),
                "no_checkout": request.POST.getlist("no_checkout"),
            }
            rules = settings_obj.clean_restriction_rules()
            rules.append(rule)
            settings_obj.restriction_rules = rules
            cleaned = settings_obj.clean_restriction_rules()
            if len(cleaned) > len(rules) - 1:  # правило не пустое → сохранилось
                settings_obj.restriction_rules = cleaned
                settings_obj.save(update_fields=["restriction_rules", "updated_at"])
                messages.success(request, _("Sales rule added."))
            else:
                messages.error(request, _("Please fill in at least one restriction."))
        elif action == "restriction_delete":  # G12: удалить правило по индексу
            settings_obj = StaySettings.load()
            rules = settings_obj.clean_restriction_rules()
            idx = _int(request.POST.get("index", "-1"), -1, 0, len(rules) - 1)
            if 0 <= idx < len(rules):
                rules.pop(idx)
                settings_obj.restriction_rules = rules
                settings_obj.save(update_fields=["restriction_rules", "updated_at"])
                messages.success(request, _("Settings saved."))
        elif action == "occupancy_add":  # PMS-D: правило «занятость ≥ X % → ±Y %»
            settings_obj = StaySettings.load()
            rules = settings_obj.clean_occupancy_rules()
            rules.append(
                {
                    "occupancy": _int(request.POST.get("occupancy", "0"), 0, 0, 100),
                    "percent": _int(request.POST.get("percent", "0"), 0, -50, 50),
                }
            )
            settings_obj.occupancy_rules = rules
            cleaned = settings_obj.clean_occupancy_rules()
            if len(cleaned) > len(rules) - 1:  # правило валидное → сохранилось
                settings_obj.occupancy_rules = cleaned
                settings_obj.save(update_fields=["occupancy_rules", "updated_at"])
                messages.success(request, _("Settings saved."))
            else:
                messages.error(request, _("Please fill in at least one restriction."))
        elif action == "occupancy_delete":  # PMS-D: удалить правило по индексу
            settings_obj = StaySettings.load()
            rules = settings_obj.clean_occupancy_rules()
            idx = _int(request.POST.get("index", "-1"), -1, 0, len(rules) - 1)
            if 0 <= idx < len(rules):
                rules.pop(idx)
                settings_obj.occupancy_rules = rules
                settings_obj.save(update_fields=["occupancy_rules", "updated_at"])
                messages.success(request, _("Settings saved."))
        elif action == "gap_deal":  # Lücken-Deal: скидка на короткие промежутки
            settings_obj = StaySettings.load()
            enabled = bool(request.POST.get("enabled"))
            settings_obj.gap_max_nights = (
                _int(request.POST.get("gap_max_nights", "3"), 3, 1, 14) if enabled else 0
            )
            settings_obj.gap_discount_percent = _int(
                request.POST.get("gap_discount_percent", "25"), 25, 1, 70
            )
            settings_obj.save(
                update_fields=["gap_max_nights", "gap_discount_percent", "updated_at"]
            )
            messages.success(request, _("Settings saved."))
        if pk:
            return redirect("stays:unit-edit", pk=pk)
        # Ревью 2026-07-28: кросс-страничные постеры (баннер Lücken-Deal на
        # Belegungsplan) возвращают владельца туда, откуда он пришёл. Только
        # относительный путь — guard от open-redirect (в т.ч. protocol-relative).
        nxt = request.POST.get("next", "")
        if nxt.startswith("/") and not nxt.startswith("//"):
            return redirect(nxt)
        # Фидбэк 2026-07-28 (№2/№3): Save глобальной настройки возвращает на её
        # таб И на её ПОД-ТАБ (секцию), чтобы владелец не искал место заново.
        _settings_sections = {
            "rateplan": "preise",
            "rateplan_toggle": "preise",
            "rateplan_delete": "preise",
            "autodiscount_add": "preise",
            "autodiscount_delete": "preise",
            "occupancy_add": "preise",
            "occupancy_delete": "preise",
            "gap_deal": "preise",
            "booking_window": "regeln",
            "restriction_add": "regeln",
            "restriction_delete": "regeln",
            "kurtaxe": "kurtaxe",
            "card_amenities": "kurtaxe",  # HF-2: живёт рядом с прочей «подачей» номеров
        }
        sec = _settings_sections.get(action)
        if sec:
            return redirect(reverse("stays:units") + f"?tab=einstellungen&sec={sec}")
        return redirect("stays:units")

    unit_qs = StayUnit.objects.prefetch_related("blocks", "season_rates", "ical_sources", "rooms")
    if pk:
        unit_page = get_object_or_404(unit_qs, pk=pk)
        units = [unit_page]
    else:
        unit_page = None
        units = list(unit_qs.order_by("-is_active", "name"))
    for u in units:
        u.ical_export_url = request.build_absolute_uri(
            reverse("storefront-stay-ical", args=[ical_token(u)])
        )
        u.i18n_inputs = i18n_inputs_for(u, getattr(request, "tenant", None))  # L3d
    stay_settings = StaySettings.load()
    # G12: правила продаж (Verkaufsregeln) — индекс для удаления + имя номера.
    _unit_names = {str(u.pk): u.name for u in units}
    restriction_rules = [
        {**r, "index": i, "unit_name": _unit_names.get(r["unit"], "")}
        for i, r in enumerate(stay_settings.clean_restriction_rules())
    ]
    # G4: правила авто-скидок с человекочитаемым описанием для кабинета.
    _kind_labels = dict(StaySettings.AUTO_DISCOUNT_KINDS)
    auto_rules = [
        {
            "index": i,
            "kind": r["kind"],
            "kind_label": _kind_labels.get(r["kind"], r["kind"]),
            "threshold": r["threshold"],
            "percent": r["percent"],
        }
        for i, r in enumerate(stay_settings.clean_auto_rules())
    ]
    return render(
        request,
        "stays/units.html",
        {
            "nav": "units",  # X4: номер — сущность раздела «Sortiment» (не операция дня)
            "open_new": request.GET.get("neu") == "1",  # X6-1: ＋ раскрывает форму
            "units": units,
            "unit_page": unit_page,  # 2026-07-28: страница одного номера
            # Фидбэк №2: активный таб списка (einheiten | einstellungen)
            "tab": request.GET.get("tab", ""),
            # Фидбэк №3: активная секция настроек (preise | regeln | kurtaxe | kanaele)
            "sec": request.GET.get("sec", ""),
            "extra_locales": extra_locales(getattr(request, "tenant", None)),
            "types": StayUnit.TYPES,
            "today": timezone.localdate(),
            "rate_plans": list(RatePlan.objects.all()),  # H1
            "meals": RatePlan.MEALS,
            "cancellations": RatePlan.CANCELLATIONS,
            "amenities": AMENITIES,  # H3 чек-лист удобств
            # HF-2: выбор удобств, показываемых на карточке номера (пусто = дефолт).
            "card_amenities": set(
                (getattr(getattr(request, "tenant", None), "site_config", None) or {}).get(
                    "stay_card_amenities", []
                )
            ),
            "stay_settings": stay_settings,  # H9 Kurtaxe
            "auto_rules": auto_rules,  # G4 правила авто-скидок
            "auto_kinds": StaySettings.AUTO_DISCOUNT_KINDS,
            # G12: правила продаж + дни недели для чекбоксов CTA/CTD.
            "restriction_rules": restriction_rules,
            # PMS-D: occupancy-правила цены (ручной revenue-management).
            "occupancy_rules": [
                {**r, "index": i} for i, r in enumerate(stay_settings.clean_occupancy_rules())
            ],
            "weekdays": [
                (0, _("Mo")),
                (1, _("Tu")),
                (2, _("We")),
                (3, _("Th")),
                (4, _("Fr")),
                (5, _("Sa")),
                (6, _("Su")),
            ],
            "embed_url": request.build_absolute_uri(reverse("storefront-unterkunft")) + "?embed=1",
            "feed_url": request.build_absolute_uri(reverse("storefront-stay-feed")),  # G8 метапоиск
        },
    )


def _month_bounds(raw):
    """(start, end, label) месяца из 'YYYY-MM' (или текущий при кривом вводе)."""
    today = timezone.localdate()
    try:
        y, m = (int(x) for x in (raw or "").split("-", 1))
        start = date(y, m, 1)
    except (TypeError, ValueError):
        start = today.replace(day=1)
    end = date(start.year + (start.month == 12), (start.month % 12) + 1, 1)
    return start, end


def _market_position(tenant):
    """CP-1 «Marktposition» (одобрено владельцем): базовые цены «ab €» отелей
    платформы в том же городе (публичные данные листингов агрегатора).
    Схлопывание: отель = min(new_price) его KIND_STAY-листингов. Показываем
    только при ≥3 отелях (включая свой); рекомендаций цены НЕ даём (только
    факт позиции — картельный риск). Нет города/агрегатор пуст → None."""
    from statistics import median

    from apps.aggregator.models import AggregatorListing

    city = (getattr(tenant, "city", "") or "").strip()
    schema = getattr(tenant, "schema_name", "")
    if not city:
        return None
    listings = AggregatorListing.objects.filter(
        listing_kind=AggregatorListing.KIND_STAY,
        is_active=True,
        city__iexact=city,
        new_price__isnull=False,
    ).values("tenant_schema", "business_name", "new_price")
    per_hotel = {}
    for row in listings:
        cur = per_hotel.get(row["tenant_schema"])
        if cur is None or row["new_price"] < cur["price"]:
            per_hotel[row["tenant_schema"]] = {
                "name": row["business_name"],
                "price": row["new_price"],
                "own": row["tenant_schema"] == schema,
            }
    hotels = sorted(per_hotel.values(), key=lambda h: h["price"])
    if len(hotels) < 3 or not any(h["own"] for h in hotels):
        return None
    prices = [h["price"] for h in hotels]
    return {
        "city": city,
        "hotels": hotels,
        "position": next(i for i, h in enumerate(hotels, start=1) if h["own"]),
        "total": len(hotels),
        "min": min(prices),
        "median": median(prices),
        "max": max(prices),
    }


@login_required
def reports(request):
    """G9: отчёт загрузки/выручки за месяц (Belegung %, ADR, RevPAR, Umsatz)."""
    from . import reports as reports_mod

    start, end = _month_bounds(request.GET.get("month"))
    data = reports_mod.occupancy_report(start, end)
    prev_m = (start - timedelta(days=1)).replace(day=1)
    nxt = end  # первое число следующего месяца
    return render(
        request,
        "stays/reports.html",
        {
            "nav": "stays",
            "start": start,
            "report": data,
            "occupancy_pct": round(data["occupancy"] * 100, 1),
            "prev_month": prev_m.strftime("%Y-%m"),
            "next_month": nxt.strftime("%Y-%m"),
            "is_current": start == timezone.localdate().replace(day=1),
            # PMS-C: разрезы канал/тариф/категория + Ø длина проживания.
            "breakdowns": reports_mod.breakdowns(start, end),
            "month_param": start.strftime("%Y-%m"),
            # CP-1: позиция цены среди отелей города (None → карточка скрыта).
            "market": _market_position(getattr(request, "tenant", None)),
        },
    )


@login_required
def reports_export_csv(request):
    """PMS-C: CSV броней месяца (utf-8-sig для Excel) — считаемые статусы,
    те же выборки, что отчёт; персональные данные — файл владельца (DSGVO)."""
    import csv

    from apps.core.csv_safe import csv_safe

    from . import reports as reports_mod

    start, end = _month_bounds(request.GET.get("month"))
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="uebernachtungen_{start.strftime("%Y-%m")}.csv"'
    )
    response.write("\ufeff")  # BOM: Excel понимает умляуты
    writer = csv.writer(response)
    writer.writerow(
        [
            "reference",
            "guest",
            "unit",
            "room",
            "arrival",
            "departure",
            "nights",
            "adults",
            "children",
            "rooms",
            "channel",
            "rate",
            "total_eur",
            "payment",
            "status",
        ]
    )
    qs = (
        reports_mod._window_bookings(start, end)
        .select_related("unit", "room", "customer")
        .order_by("arrival")
    )
    for b in qs.iterator():
        writer.writerow(
            [
                b.reference_code,
                csv_safe(str(b.customer)),
                csv_safe(b.unit.name),
                csv_safe(b.room.number) if b.room else "",
                b.arrival.isoformat(),
                b.departure.isoformat(),
                b.nights,
                b.adults,
                b.children,
                b.rooms,
                csv_safe(b.source_channel or "direct"),
                csv_safe((b.rate_snapshot or {}).get("name") or ""),
                f"{b.total_cents / 100:.2f}",
                b.payment_state,
                b.status,
            ]
        )
    return response


@login_required
def checkins(request):
    """G6: список цифровых Meldescheine (Online-Checkins). Read-only обзор для
    стойки — кто заполнил данные регистрации. Гейтинг — модуль stays."""
    from .models import GuestRegistration

    regs = list(
        GuestRegistration.objects.select_related("booking", "booking__unit")
        .filter(signed_at__isnull=False)
        .order_by("-signed_at")[:200]
    )
    return render(request, "stays/checkins.html", {"nav": "stays", "registrations": regs})


@login_required
def channels(request):
    """G11: каналы продаж (Booking/Airbnb/Expedia) + ручной импорт брони из канала.

    iCal-импорт занятости (A5b) живёт на странице юнитов; здесь — учёт каналов и
    нормализованный занос брони из OTA (идемпотентно). Реальный API-синк — позже."""
    from .models import Channel

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "channel_add":
            kind = request.POST.get("kind", Channel.KIND_OTHER)
            valid = {k for k, _ in Channel.KINDS}
            Channel.objects.create(
                kind=kind if kind in valid else Channel.KIND_OTHER,
                name=request.POST.get("name", "").strip()[:120],
            )
            messages.success(request, _("Channel added."))
        elif action == "channel_toggle":
            ch = get_object_or_404(Channel, pk=request.POST.get("channel"))
            ch.is_active = not ch.is_active
            ch.save(update_fields=["is_active", "updated_at"])
        elif action == "channel_delete":
            Channel.objects.filter(pk=request.POST.get("channel")).delete()
        elif action == "import_booking":
            unit = get_object_or_404(StayUnit, pk=request.POST.get("unit"), is_active=True)
            try:
                arrival = date.fromisoformat(request.POST.get("arrival", ""))
                departure = date.fromisoformat(request.POST.get("departure", ""))
            except ValueError:
                messages.error(request, _("Invalid dates."))
                return redirect("stays:channels")
            booking = services.import_external_booking(
                kind=request.POST.get("kind", Channel.KIND_OTHER),
                unit=unit,
                arrival=arrival,
                departure=departure,
                name=request.POST.get("name", "").strip(),
                external_ref=request.POST.get("external_ref", "").strip(),
                email=request.POST.get("email", "").strip(),
                guests=_int(request.POST.get("guests", "1"), 1, 1, 50),
            )
            if booking is None:
                messages.warning(
                    request,
                    _("Conflict — dates were blocked instead. Please resolve manually."),
                )
            else:
                messages.success(request, _("Reservation imported."))
        return redirect("stays:channels")

    return render(
        request,
        "stays/channels.html",
        {
            "nav": "stays",
            "channels": list(Channel.objects.all()),
            "kinds": Channel.KINDS,
            "units": list(StayUnit.objects.filter(is_active=True).order_by("name")),
            "imported": list(
                StayBooking.objects.exclude(external_ref="")
                .select_related("unit")
                .order_by("-created_at")[:50]
            ),
        },
    )


@login_required
@require_POST
def stay_inline_edit(request):
    """Инлайн-правка номера на канве — тонкий алиас единого диспетчера (UC2-4).

    Контракт/URL прежние: JSON {pk, field, value}; семантика — декларация
    INLINE_REGISTRY["stay"]: name (плоско, кламп 120, пустым нельзя)/
    description; price_eur → центы; bump на всех ветках."""
    from apps.core.inline_edit import dispatch

    return dispatch(request, "stay")


@login_required
@require_POST
def stay_photo_edit(request):
    """Пер-слайд правка галереи номера на канве (multipart: pk, op, image_id, image).
    op ∈ {replace, add, remove}. Зеркало catalog.product_photo_edit — StayUnit.images
    тот же FileRef-список, общий диспетчер apply_gallery_op. 204/400."""
    from django.core.exceptions import ValidationError
    from django.db import transaction
    from django.http import HttpResponse, HttpResponseBadRequest

    from apps.catalog.images import apply_gallery_op

    pk = request.POST.get("pk")
    op = request.POST.get("op", "replace")
    image_id = request.POST.get("image_id", "")
    uploaded = request.FILES.get("image")
    if not pk:
        return HttpResponseBadRequest()
    try:
        # Лок строки на read-modify-write images (анти-lost-update при параллельных правках).
        with transaction.atomic():
            unit = StayUnit.objects.select_for_update().get(pk=pk)
            unit.images = apply_gallery_op(
                unit.images, op=op, image_id=image_id, uploaded=uploaded, folder="stays"
            )
            unit.save(update_fields=["images", "updated_at"])
    except (StayUnit.DoesNotExist, ValueError):
        return HttpResponseBadRequest()
    except ValidationError as exc:
        return HttpResponseBadRequest("; ".join(exc.messages))
    schema = getattr(getattr(request, "tenant", None), "schema_name", None)
    if schema:
        from apps.core.pagecache import bump_storefront_cache

        bump_storefront_cache(schema)
    return HttpResponse(status=204)


@login_required
def unit_feature(request, pk):
    """D2.4: продвижение типа размещения в агрегаторе (self-serve featured,
    generic-зеркало promotion_feature — apps.aggregator.featuring)."""
    from apps.aggregator import featuring
    from apps.aggregator.models import AggregatorListing

    unit = get_object_or_404(StayUnit, pk=pk)
    return featuring.render_feature_page(
        request,
        obj_title=unit.name,
        kind=AggregatorListing.KIND_STAY,
        source_ref=str(unit.pk),
        listable=unit.is_active,
        not_listed_hint=_(
            "Nur aktive Unterkünfte erscheinen im Verzeichnis und können "
            "beworben werden. Aktivieren Sie die Unterkunft zuerst."
        ),
        back_url=reverse("stays:units"),
        checkout_url=reverse("stays:unit-feature-checkout", args=[unit.pk]),
        nav="stays",
    )


@login_required
@require_POST
def unit_feature_checkout(request, pk):
    """D2.4: разовый Stripe-Checkout за продвижение юнита → редирект на оплату."""
    from apps.aggregator import featuring
    from apps.aggregator.models import AggregatorListing
    from apps.aggregator.tasks import sync_stay_listing

    unit = get_object_or_404(StayUnit, pk=pk)
    return featuring.start_feature_checkout(
        request,
        kind=AggregatorListing.KIND_STAY,
        source_ref=str(unit.pk),
        title=unit.name,
        listable=unit.is_active,
        not_listable_msg=_("Nur aktive Unterkünfte können beworben werden."),
        sync=sync_stay_listing,
        feature_page_url=reverse("stays:unit-feature", args=[unit.pk]),
    )


def _stay_sections(request):
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
