"""KA-12 Zimmer Z-3 (E4.6b): кабинет «Preise & Verfügbarkeit».

Сетка категория × день (14/31) с ценой ночи без тарифа, источником цены,
ограничениями дня и свободными номерами; массовая правка (Vorschau — GET без
записи, «Übernehmen» — POST) и диалог одного дня. Смотрят все роли кабинета,
правят owner/admin (О-4). Запись — только через ``night_rates.apply_plan``.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core import ratelimit, roles

from . import availability, night_rates, pricing
from .models import StayUnit

WINDOWS = (14, 31)
PREVIEW_ROWS = 50
_WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


def _can_edit(user) -> bool:
    """О-4: массовая правка цен — владелец и admin (обёртка для тестов)."""
    return roles.can_edit_policy(user)


def _ident(request) -> str:
    return f"{getattr(request.tenant, 'schema_name', '')}:{request.user.pk}"


def _window(params, today):
    """(von, tage) из GET/POST: tage ∈ WINDOWS, von не раньше сегодня и не за горизонтом."""
    tage = int(params.get("tage")) if str(params.get("tage", "")).isdigit() else 14
    if tage not in WINDOWS:
        tage = 14
    von = night_rates.parse_day(params.get("von")) or today
    last = today + timedelta(days=night_rates.MAX_HORIZON_DAYS - tage)
    return min(max(von, today), last), tage


def _grid_url(von: date, tage: int, kat=None) -> str:
    query = {"von": von.isoformat(), "tage": tage}
    if kat:
        query["kat"] = str(kat)
    return reverse("stays:price-calendar") + "?" + urlencode(query)


def _units(kat=None):
    qs = StayUnit.objects.filter(is_active=True).prefetch_related("season_rates").order_by("name")
    if kat is not None:
        qs = qs.filter(pk=kat)
    return list(qs)


def _cell(unit, day, seasons, night, free):
    mark = pricing.price_source_mark(unit, day, seasons, night)
    cents = pricing.nightly_price_cents(unit, day, seasons, {day: night} if night else None)
    return {
        "day": day,
        "cents": cents,
        "eur": Decimal(cents) / 100,
        "source": pricing.source_label(mark),
        "own": mark == "@night",
        "stop": bool(night and night.stop_sell),
        "min": night.min_nights if night else 0,
        "no_in": bool(night and night.no_checkin),
        "no_out": bool(night and night.no_checkout),
        "free": free,
        "weekend": day.weekday() in pricing.WEEKEND_WEEKDAYS,
    }


def grid_context(units, start: date, n_days: int) -> dict:
    """Строки сетки. Запросов — фиксированно (юниты, сезоны, окно NightRate,
    брони и блоки окна), не по ячейке."""
    end = start + timedelta(days=n_days - 1)
    window = pricing.night_rates_window([u.pk for u in units], start, end)
    days, occupancy = availability.occupancy_grid(units, start, n_days)
    rows = []
    for unit, occ_cells in occupancy:
        seasons = list(unit.season_rates.all())
        nights = window.get(unit.pk, {})
        cells = [
            _cell(unit, oc["day"], seasons, nights.get(oc["day"]), oc["free"]) for oc in occ_cells
        ]
        rows.append({"unit": unit, "cells": cells})
    return {"days": days, "rows": rows}


def _parse_scope(params, today):
    """(units, days, errors) из формы массовой правки (GET Vorschau или POST)."""
    ids, garbage = night_rates.parse_unit_ids(params.getlist("unit"))
    found = []
    if ids and len(ids) <= night_rates.MAX_UNITS and not garbage:
        found = list(
            StayUnit.objects.filter(pk__in=ids, is_active=True)
            .prefetch_related("season_rates")
            .order_by("name")
        )
    von = night_rates.parse_day(params.get("from"))
    bis = night_rates.parse_day(params.get("bis"))
    weekdays = night_rates.parse_weekdays(params.getlist("wd"))
    errors = night_rates.validate_scope(
        n_units=len(found),
        n_requested=len(ids) + (1 if garbage else 0),
        garbage=garbage,
        von=von,
        bis=bis,
        weekdays=weekdays,
        today=today,
    )
    days = night_rates.select_days(von, bis, weekdays) if not errors else []
    return found, days, errors


def _bulk_defaults(params, von, tage, units):
    """Значения формы массовой правки (предзаполнение из GET)."""
    chosen = set(params.getlist("unit")) or {str(u.pk) for u in units}
    return {
        "units": chosen,
        "from": params.get("from") or von.isoformat(),
        "bis": params.get("bis") or (von + timedelta(days=tage - 1)).isoformat(),
        "wd": set(params.getlist("wd")) or {str(i) for i in range(7)},
        "price_mode": params.get("price_mode", "keep"),
        "price": params.get("price", ""),
        "percent": params.get("percent", ""),
        "min_mode": params.get("min_mode", "keep"),
        "min_nights": params.get("min_nights", ""),
        "stop_sell": params.get("stop_sell", ""),
        "no_checkin": params.get("no_checkin", ""),
        "no_checkout": params.get("no_checkout", ""),
    }


def _preview(request, today):
    """Vorschau: план без записи. None — запрос без vorschau=1 или без прав."""
    params = request.GET
    if params.get("vorschau") != "1" or not _can_edit(request.user):
        return None
    if ratelimit.hit("price-preview", _ident(request), limit=30, window=60):
        return {"errors": [_("Zu viele Anfragen. Bitte kurz warten.")]}
    units, days, errors = _parse_scope(params, today)
    action, action_errors = night_rates.parse_action(params)
    errors += action_errors
    if errors:
        return {"errors": errors}
    plan = night_rates.build_plan(units, days, action)
    names = {u.pk: u.name for u in units}
    booked = _booked_nights(units, days)
    return {
        "errors": [],
        "plan": plan,
        "counts": plan.counts(),
        "fingerprint": plan.fingerprint(action),
        "rows": [_preview_row(names[c.unit_id], c) for c in plan.changes[:PREVIEW_ROWS]],
        "more": max(0, len(plan.changes) - PREVIEW_ROWS),
        "rejected": len(plan.rejected),
        "booked": booked,
    }


def _eur(cents):
    return Decimal(cents) / 100 if cents is not None else None


def _preview_row(unit_name, change) -> dict:
    return {
        "unit": unit_name,
        "day": change.day,
        "kind": change.kind,
        "before": change.before,
        "after": change.after,
        "before_eur": _eur(change.before.price_cents),
        "after_eur": _eur(change.after.price_cents),
    }


def _booked_nights(units, days) -> int:
    """Сколько выбранных ночей уже продано хотя бы частично (информативно)."""
    if not days:
        return 0
    wanted = set(days)
    start, n = min(days), (max(days) - min(days)).days + 1
    _days, rows = availability.occupancy_grid(units, start, n)
    return sum(
        1
        for unit, cells in rows
        for cell in cells
        if cell["day"] in wanted and cell["free"] < unit.quantity
    )


@login_required
def price_calendar(request):
    today = timezone.localdate()
    von, tage = _window(request.GET, today)
    kat_ids, _garbage = night_rates.parse_unit_ids([request.GET.get("kat", "")])
    kat = kat_ids[0] if kat_ids else None
    units = _units(kat)
    if kat is not None and not units:
        kat, units = None, _units()
    can_edit = _can_edit(request.user)
    context = {
        "nav": "price-calendar",
        "von": von,
        "tage": tage,
        "windows": WINDOWS,
        "kat": kat,
        "today": today,
        "prev": max(today, von - timedelta(days=tage)),
        "next": min(
            von + timedelta(days=tage),
            today + timedelta(days=night_rates.MAX_HORIZON_DAYS - tage),
        ),
        "can_edit": can_edit,
        "all_units": _units() if can_edit else [],
        "weekday_choices": [(str(i), _(name)) for i, name in enumerate(_WEEKDAYS)],
        "preview": _preview(request, today),
        **grid_context(units, von, tage),
    }
    if can_edit:
        context["bulk"] = _bulk_defaults(request.GET, von, tage, context["all_units"])
    response = render(request, "stays/price_calendar.html", context)
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
@require_POST
def price_calendar_apply(request):
    if not _can_edit(request.user):
        raise PermissionDenied(_("Nur für Inhaber und Administratoren."))
    today = timezone.localdate()
    von, tage = _window(request.POST, today)
    back = _grid_url(von, tage)
    if ratelimit.hit("price-apply", _ident(request), limit=10, window=60):
        messages.error(request, _("Zu viele Anfragen. Bitte kurz warten."))
        return redirect(back)
    units, days, errors = _parse_scope(request.POST, today)
    action, action_errors = night_rates.parse_action(request.POST)
    errors += action_errors
    if errors:
        for err in errors:
            messages.error(request, err)
        return redirect(back)
    try:
        result = night_rates.apply_plan(
            [u.pk for u in units],
            days,
            action,
            expected_fingerprint=request.POST.get("fingerprint", ""),
            actor=request.user,
        )
    except night_rates.StalePlan:
        messages.error(
            request,
            _("Die Daten haben sich inzwischen geändert. Bitte prüfen Sie die Vorschau erneut."),
        )
        return redirect(back)
    except night_rates.PlanRejected:
        messages.error(request, _("Der Preis würde auf 0 € oder darunter fallen."))
        return redirect(back)
    changed = result.created + result.updated + result.deleted
    if changed:
        messages.success(request, _("Aktualisierte Nächte: %(n)s") % {"n": changed})
    else:
        messages.info(request, _("Keine Änderungen — alles ist bereits so eingestellt."))
    return redirect(back)


def _day_action(post) -> night_rates.Action:
    """Поля дня ЗАДАЮТСЯ (не «nicht ändern»): пустая цена — сброс к сезону/базе."""
    raw_price = str(post.get("price") or "").strip()
    flags = post.get("day_present") == "1"
    raw_min = str(post.get("min_nights") or "").strip()
    return night_rates.Action(
        price_mode="set" if raw_price else "reset",
        price_cents=night_rates._money_cents(raw_price) if raw_price else None,
        stop_sell=bool(post.get("stop_sell")) if flags else None,
        min_nights=(int(raw_min) if raw_min.isdigit() else 0) if flags else None,
        no_checkin=bool(post.get("no_checkin")) if flags else None,
        no_checkout=bool(post.get("no_checkout")) if flags else None,
    )


@login_required
def price_day(request, pk, day):
    the_day = night_rates.parse_day(day)
    today = timezone.localdate()
    if the_day is None or not (
        today <= the_day <= today + timedelta(days=night_rates.MAX_HORIZON_DAYS)
    ):
        raise Http404
    unit = get_object_or_404(StayUnit.objects.prefetch_related("season_rates"), pk=pk)
    von, tage = _window(request.POST if request.method == "POST" else request.GET, today)
    if request.method == "POST":
        if not _can_edit(request.user):
            raise PermissionDenied(_("Nur für Inhaber und Administratoren."))
        raw_min = str(request.POST.get("min_nights") or "").strip()
        if raw_min and not (raw_min.isdigit() and int(raw_min) <= 365):
            messages.error(request, _("Mindestaufenthalt: 1 bis 365 Nächte."))
            return redirect(_grid_url(von, tage))
        try:
            action = _day_action(request.POST)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect(_grid_url(von, tage))
        if action.is_noop:
            action = night_rates.Action(price_mode="reset")
        try:
            night_rates.apply_plan(
                [unit.pk],
                [the_day],
                action,
                expected_state=request.POST.get("state", "") or "-",
                actor=request.user,
                kind="day",
            )
        except night_rates.StalePlan:
            messages.error(
                request,
                _(
                    "Die Daten haben sich inzwischen geändert. Bitte prüfen Sie die Vorschau erneut."
                ),
            )
        except night_rates.PlanRejected:
            messages.error(request, _("Der Preis würde auf 0 € oder darunter fallen."))
        else:
            messages.success(request, _("Gespeichert."))
        return redirect(_grid_url(von, tage))
    seasons = list(unit.season_rates.all())
    window = pricing.night_rates_window([unit.pk], the_day, the_day)
    night = window[unit.pk].get(the_day)
    _days, occ = availability.occupancy_grid([unit], the_day, 1)
    cell = _cell(unit, the_day, seasons, night, occ[0][1][0]["free"])
    context = {
        "unit": unit,
        "cell": cell,
        "night": night,
        "chain_eur": Decimal(pricing.nightly_price_cents(unit, the_day, seasons, None)) / 100,
        "own_eur": Decimal(night.price_cents) / 100 if night and night.price_cents else None,
        "von": von,
        "tage": tage,
        "can_edit": _can_edit(request.user),
        "state": night_rates.state_fingerprint(unit.pk, the_day, night_rates.DayState.of(night)),
        "nav": "price-calendar",
    }
    template = "stays/_price_day.html" if request.GET.get("box") == "1" else "stays/price_day.html"
    response = render(request, template, context)
    response["Cache-Control"] = "private, no-store"
    return response
