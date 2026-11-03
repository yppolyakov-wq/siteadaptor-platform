"""UX-D D5.0: «＋ Neuer Termin» — форма ручной записи шторкой (контракт
`docs/references/patterns/drawer.md`). Раньше — постоянно раскрытая форма под Tagesplan.

Ядро записи — общее (`services.create_manual`: часы, места стола, пул, навык, занятость).
Здесь разбор строгий: ошибка у поля, введённое сохраняется, ничего не создаётся (старый
`booking_create` с мягким разбором остаётся для Tischplan и POST без JS). «Trotzdem
eintragen» — вторая кнопка формы после отказа, который можно обойти (вне часов, мало мест).
"""

from __future__ import annotations

import re
from datetime import date, datetime, time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Prefetch
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import drawer as drawer_mod
from apps.core.owner_login import local_next

from . import services
from .models import Resource, Service, ServiceVariant

FIELDS = (
    "resource",
    "start_date",
    "start_time",
    "minutes",
    "service",
    "name",
    "phone",
    "email",
    "party_size",
    "note",
)
_MORE_FIELDS = {"minutes", "note"}


def _int_or_none(raw, lo, hi):
    raw = (raw or "").strip()
    # pitfalls §3: str.isdigit() пускает «²»/«٣», а int("²") падает 500 — только ASCII-цифры
    if not re.fullmatch(r"[0-9]{1,5}", raw):
        return None
    value = int(raw)
    return value if lo <= value <= hi else None


def _values(data) -> dict:
    """Значения формы (префилл GET или повтор после ошибки) — только строки, с обрезкой."""
    out = {f: (data.get(f) or "").strip()[: 2000 if f == "note" else 200] for f in FIELDS}
    legacy = (data.get("start") or "").strip()  # «2026-11-04T10:30» — свободное время сетки
    if legacy and not (out["start_date"] or out["start_time"]):
        day, _sep, clock = legacy.partition("T")
        out["start_date"], out["start_time"] = day[:10], clock[:5]
    if not out["start_date"] and data.get("tag"):
        out["start_date"] = (data.get("tag") or "")[:10]
    return out


def parse(post) -> tuple[dict, dict]:
    """Строгий разбор → (значения для create_manual, ошибки {поле: текст})."""
    from apps.booking import pricing

    errors, out = {}, {}
    raw = (post.get("resource") or "").strip()
    try:
        out["resource"] = Resource.objects.filter(pk=raw, is_active=True).first() if raw else None
    except (ValueError, ValidationError):
        out["resource"] = None
    if out["resource"] is None:
        errors["resource"] = _("Bitte eine Ressource wählen.")
    vals = _values(post)
    try:
        day = date.fromisoformat(vals["start_date"])
        clock = time.fromisoformat(vals["start_time"])
        out["start"] = timezone.make_aware(
            datetime.combine(day, clock), timezone.get_current_timezone()
        )
    except ValueError:
        errors["start_time"] = _("Bitte Datum und Uhrzeit angeben.")
    if vals["minutes"]:
        out["minutes"] = _int_or_none(vals["minutes"], 5, 1440)
        if out["minutes"] is None:
            errors["minutes"] = _("Bitte eine Zahl von %(lo)s bis %(hi)s angeben.") % {
                "lo": 5,
                "hi": 1440,
            }
    else:
        out["minutes"] = None
    if vals["party_size"]:
        out["party_size"] = _int_or_none(vals["party_size"], 1, 50)
        if out["party_size"] is None:
            errors["party_size"] = _("Bitte eine Zahl von %(lo)s bis %(hi)s angeben.") % {
                "lo": 1,
                "hi": 50,
            }
    else:
        out["party_size"] = 1
    out["service"] = out["variant"] = None
    raw_service, _sep, raw_variant = vals["service"].partition(":")
    if raw_service:
        try:
            out["service"] = Service.objects.filter(pk=raw_service, is_active=True).first()
        except (ValueError, ValidationError):
            out["service"] = None
        if out["service"] is None:
            errors["service"] = _("Leistung nicht gefunden – bitte neu wählen.")
        elif raw_variant:
            variant, ok = pricing.resolve_variant(out["service"], raw_variant)
            if not ok:
                errors["service"] = _("Leistung nicht gefunden – bitte neu wählen.")
            out["variant"] = variant if ok else None
    for f in ("name", "phone", "email", "note"):
        out[f] = vals[f]
    # Ревью D5.0: длина полей клиента = длина модели (телефон 41+ символов давал 500),
    # e-mail проверяется на сервере (иначе письма молча не доходят).
    raw_post = {f: (post.get(f) or "").strip() for f in ("name", "phone", "email")}
    for f, limit in (("name", 200), ("phone", 40), ("email", 254)):
        if len(raw_post[f]) > limit:
            errors[f] = _("Höchstens %(n)s Zeichen.") % {"n": limit}
    if raw_post["email"] and "email" not in errors:
        from django.core.validators import validate_email

        try:
            validate_email(raw_post["email"])
        except ValidationError:
            errors["email"] = _("Bitte eine gültige E-Mail angeben.")
    return out, errors


def _form_ctx(request, values, errors=None, refused=None):
    resources = list(Resource.objects.filter(is_active=True).order_by("type", "sort_order", "name"))
    services_qs = (
        Service.objects.filter(is_active=True)
        .order_by("name")
        .prefetch_related(
            Prefetch(
                "variants",
                queryset=ServiceVariant.objects.filter(is_active=True).order_by("sort_order", "id"),
                to_attr="active_variants",
            )
        )
    )
    services_list = list(services_qs)
    for svc in services_list:
        svc.opt_value = str(svc.pk)
        for v in svc.active_variants:  # значение опции — «<услуга>:<вариант>» (E4.4b)
            v.opt_value = f"{svc.pk}:{v.pk}"
    if values.get("resource") and values["resource"] not in {str(r.pk) for r in resources}:
        values["resource"] = ""  # чужой/выключенный ресурс не выбираем молча (урок D1.3)
    errors = errors or {}
    return {
        "nav": "booking",
        "bv": values,
        "bv_errors": errors,
        "bv_more_open": bool(values.get("minutes") or values.get("note"))
        or bool(set(errors) & _MORE_FIELDS),
        "resources": resources,
        "manual_services": services_list,
        "show_party": any(r.type == Resource.TYPE_TABLE or r.counts_party_size for r in resources)
        or Service.objects.filter(is_active=True, pricing_mode="per_person").exists(),
        "refused": refused,
        "next_url": drawer_mod.drawer_next(request, reverse("verkaeufe") + "?tab=booking"),
    }


@login_required
@drawer_mod.drawer_aware
def booking_new(request):
    def render_form(values, errors=None, refused=None):
        ctx = _form_ctx(request, values, errors, refused)
        if request.method == "POST":
            ctx["next_url"] = local_next(request) or ctx["next_url"]
        if drawer_mod.is_drawer(request) or request.GET.get("box") == "1":
            return drawer_mod.fragment(render(request, "booking/_booking_new_drawer.html", ctx))
        return render(request, "booking/booking_new.html", ctx)

    if request.method != "POST":
        return render_form(_values(request.GET))

    values, errors = parse(request.POST)
    if errors:
        if drawer_mod.is_drawer(request):  # шторка показывает его в role=alert
            messages.error(request, next(iter(errors.values())))
        return render_form(_values(request.POST), errors)
    override = bool(request.POST.get("override_hours"))
    try:
        booking, warnings = services.create_manual(
            values["resource"],
            start=values["start"],
            minutes=values["minutes"],
            service=values["service"],
            variant=values["variant"],
            party_size=values["party_size"],
            name=values["name"],
            email=values["email"],
            phone=values["phone"],
            note=values["note"],
            override_hours=override,
            # KA-12 GA-3: тот же «Trotzdem eintragen» снимает и проверку мест.
            override_seats=override,
        )
    except services.ManualBookingRefused as exc:
        for text in exc.warnings:
            messages.warning(request, text)
        messages.error(request, str(exc))
        field = "party_size" if exc.code in ("seats", "capacity") else "start_time"
        refused = exc.code if exc.code in exc.OVERRIDABLE else None
        return render_form(_values(request.POST), {field: str(exc)}, refused)
    for text in warnings:
        messages.warning(request, text)
    messages.success(request, _("Booking created."))
    day = timezone.localtime(booking.start).date()
    if drawer_mod.is_drawer(request):
        drawer_mod.open_after(request, reverse("booking:booking-detail", args=[booking.pk]))
        nxt = local_next(request) or reverse("verkaeufe") + "?tab=booking"
        return redirect(drawer_mod.with_param(nxt, "tag", day.isoformat()))
    return redirect(reverse("booking:booking-detail", args=[booking.pk]))
