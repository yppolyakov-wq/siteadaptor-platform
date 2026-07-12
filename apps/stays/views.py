"""Кабинет date-range-броней (Track E / E2): /dashboard/stays/.

Календарь загрузки (юниты × ночи: свободно/занято/блок), действия по FSM
(confirm/fulfilled/no_show/cancelled) + перенос дат, ручная бронь (сразу
confirmed), управление юнитами (тип/цена/min_nights/max_guests/депозит) и
блокировками дат. Гейтинг — модуль «stays» из реестра (ModuleGatingMiddleware).
"""

from datetime import date, timedelta

import stripe
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.billing import connect
from apps.core.fsm import IllegalTransition
from apps.core.i18n_input import apply_i18n_overlay, extra_locales, i18n_inputs_for

from . import availability, services
from .models import (
    _AMENITY_KEYS,
    AMENITIES,
    ICalSource,
    RatePlan,
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


def _status_rows(request):
    """FB-4b: [(status, дефолт, своё-имя)] для панели переименования статусов брони."""
    from apps.core import status_labels

    return status_labels.label_rows(getattr(request, "tenant", None), "stay", StayBooking.STATUSES)


def _transition_rows(request):
    """FB-3: строки панели правил переходов статусов брони."""
    from apps.core import transition_rules

    return transition_rules.editor_rows(getattr(request, "tenant", None), "stay")


@login_required
def calendar(request):
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
        .select_related("unit", "customer")
        .order_by("arrival")
    )
    return render(
        request,
        "stays/calendar.html",
        {
            "nav": "stays",
            "start": start,
            "prev": start - timedelta(days=HORIZON_DAYS),
            "next": start + timedelta(days=HORIZON_DAYS),
            "today": timezone.localdate(),
            "days": days,
            "rows": rows,
            "bookings": bookings,
            "units": units,
            "finance_active": _finance_active(request),
            # FB-4b: строки панели «Status-Namen» брони (status, дефолт, своё имя).
            "status_label_rows": _status_rows(request),
            # FB-3: строки панели «Statusübergänge» (правила переходов).
            "transition_rows": _transition_rows(request),
        },
    )


@login_required
@require_POST
def stay_action(request, pk):
    booking = get_object_or_404(StayBooking, pk=pk)
    action = request.POST.get("action", "")
    back = f"{reverse('stays:calendar')}?von={booking.arrival.isoformat()}"
    if action == "invoice":  # A5: черновик Rechnung из брони (модуль finance)
        if not _finance_active(request):
            messages.error(request, _("Enable the Finance module first."))
            return redirect(back)
        small_business = getattr(request.tenant, "small_business", False)
        invoice = services.stay_to_invoice(booking, small_business=small_business)
        return redirect(reverse("finance:invoice-detail", args=[invoice.pk]))
    if action == "move":
        try:
            arrival = date.fromisoformat(request.POST.get("arrival", ""))
            departure = date.fromisoformat(request.POST.get("departure", ""))
            services.move_stay(booking, arrival=arrival, departure=departure)
            messages.success(request, _("Stay moved."))
        except ValueError:
            messages.error(request, _("Invalid dates."))
        except services.MinStay:
            messages.error(request, _("Below the minimum number of nights."))
        except services.StayUnavailable:
            messages.error(request, _("Those dates are no longer available."))
        return redirect(back)
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
    """Ручное добавление (телефонная/личная бронь): сразу confirmed."""
    unit = get_object_or_404(StayUnit, pk=request.POST.get("unit"), is_active=True)
    try:
        arrival = date.fromisoformat(request.POST.get("arrival", ""))
        departure = date.fromisoformat(request.POST.get("departure", ""))
    except ValueError:
        messages.error(request, _("Invalid dates."))
        return redirect("stays:calendar")
    name = request.POST.get("name", "").strip() or _("Walk-in")
    try:
        booking = services.book_stay(
            unit,
            arrival=arrival,
            departure=departure,
            name=name,
            email=request.POST.get("email", "").strip(),
            phone=request.POST.get("phone", "").strip(),
            guests=_int(request.POST.get("guests", "1"), 1, 1, 50),
            note=request.POST.get("note", "").strip()[:2000],
            source_channel="manual",
            auto_confirm=True,
        )
    except services.MinStay:
        messages.error(request, _("Below the minimum number of nights."))
        return redirect("stays:calendar")
    except services.MaxGuests:
        messages.error(request, _("Too many guests for this unit."))
        return redirect("stays:calendar")
    except services.StayUnavailable:
        messages.error(request, _("Those dates are no longer available."))
        return redirect("stays:calendar")
    except ValueError:
        messages.error(request, _("Invalid dates."))
        return redirect("stays:calendar")
    messages.success(request, _("Stay created."))
    return redirect(f"{reverse('stays:calendar')}?von={booking.arrival.isoformat()}")


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
        {"b": booking, "registration": registration, "nav": "stays"},
    )


@login_required
def units(request):
    """Юниты (тип/цена/вместимость/депозит) + блокировки дат — POST-формы."""
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
        elif action == "unit_settings":
            unit = get_object_or_404(StayUnit, pk=request.POST.get("unit"))
            unit.description = request.POST.get("description", "").strip()[:5000]
            # L3d: name правится при явно присланном поле (presence-guard).
            _new_name = request.POST.get("name")
            if _new_name is not None and _new_name.strip():
                unit.name = _new_name.strip()[:120]
            unit.price_cents = _eur_to_cents(request.POST.get("price_eur"))
            unit.weekend_price_cents = _eur_to_cents(request.POST.get("weekend_price_eur"))
            unit.quantity = _int(request.POST.get("quantity", "1"), 1, 1, 999)
            unit.min_nights = _int(request.POST.get("min_nights", "1"), 1, 1, 365)
            unit.max_guests = _int(request.POST.get("max_guests", "2"), 2, 1, 99)
            unit.deposit_cents = _eur_to_cents(request.POST.get("deposit_eur"))
            unit.require_manual_confirm = bool(request.POST.get("require_manual_confirm"))
            unit.area_sqm = _int(request.POST.get("area_sqm", "0"), 0, 0, 9999)
            unit.bed_type = request.POST.get("bed_type", "").strip()[:80]
            unit.amenities = [a for a in request.POST.getlist("amenities") if a in _AMENITY_KEYS]
            _uf = [
                "name",
                "description",
                "price_cents",
                "weekend_price_cents",
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
        elif action == "rateplan_delete":
            RatePlan.objects.filter(pk=request.POST.get("rateplan")).delete()
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
        return redirect("stays:units")

    units = list(
        StayUnit.objects.prefetch_related("blocks", "season_rates", "ical_sources").order_by(
            "-is_active", "name"
        )
    )
    for u in units:
        u.ical_export_url = request.build_absolute_uri(
            reverse("storefront-stay-ical", args=[ical_token(u)])
        )
        u.i18n_inputs = i18n_inputs_for(u, getattr(request, "tenant", None))  # L3d
    stay_settings = StaySettings.load()
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
            "nav": "stays",
            "units": units,
            "extra_locales": extra_locales(getattr(request, "tenant", None)),
            "types": StayUnit.TYPES,
            "today": timezone.localdate(),
            "rate_plans": list(RatePlan.objects.all()),  # H1
            "meals": RatePlan.MEALS,
            "cancellations": RatePlan.CANCELLATIONS,
            "amenities": AMENITIES,  # H3 чек-лист удобств
            "stay_settings": stay_settings,  # H9 Kurtaxe
            "auto_rules": auto_rules,  # G4 правила авто-скидок
            "auto_kinds": StaySettings.AUTO_DISCOUNT_KINDS,
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
        },
    )


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
        not_listed_hint=(
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
        not_listable_msg="Nur aktive Unterkünfte können beworben werden.",
        sync=sync_stay_listing,
        feature_page_url=reverse("stays:unit-feature", args=[unit.pk]),
    )
