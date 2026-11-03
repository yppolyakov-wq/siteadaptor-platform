"""UX-D D6.2a: «Buchen» — приход / корректировка / инвентура / перемещение шторкой.

Раньше над таблицей склада всегда висели три раскрытые формы (каждая — с селектом ВСЕХ
сущностей), а Umlagerung — ещё одна в «Standorte». Теперь у строки таблицы, у найденного
сканером и в Bestellvorschläge — кнопка «Buchen»: шторка с выбранной сущностью и видом
операции (вкладки-ссылки). Без JS — обычная страница, POST → редирект на склад.

Разбор строгий (класс D6.0): мусор/«²»/вне границ — ошибка у поля, движения нет (старый
`_int` молча делал из «abc» 0 → «Keine Änderung»). Запись — тем же сервисным путём, что и
прежние формы (`apply_manual_movement` / `receive_lot` / `locations.transfer`)."""

from __future__ import annotations

import re
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.core import drawer as drawer_mod
from apps.core.owner_login import local_next

from . import locations, services
from .models import StockLocation, StockMovement

ARTS = ("receipt", "adjustment", "stocktake", "transfer")
MAX_QTY = 99999
FIELDS = (
    "entity",
    "qty",
    "delta",
    "counted",
    "reason",
    "note",
    "lot_code",
    "lot_mhd",
    "location",
)


def _number(raw, *, lo: int, hi: int, signed: bool = False):
    """Целое из формы: только ASCII-цифры (pitfalls §3), знак — по флагу; вне границ → None."""
    raw = (raw or "").strip().replace(" ", "")
    pattern = r"[-+]?[0-9]{1,5}" if signed else r"[0-9]{1,5}"
    if not re.fullmatch(pattern, raw):
        return None
    value = int(raw)
    return value if lo <= value <= hi else None


def _range_error(lo: int, hi: int) -> str:
    return _("Bitte eine Zahl von %(lo)s bis %(hi)s angeben.") % {"lo": lo, "hi": hi}


def _arts(locs_on: bool) -> tuple[str, ...]:
    return ARTS if locs_on else tuple(a for a in ARTS if a != "transfer")


def parse(post, art: str, *, lots_on: bool) -> tuple[dict, dict]:
    """Строгий разбор формы вида `art` → (значения, ошибки {поле: текст})."""
    from .views import ADJUST_REASONS, _resolve_entity

    errors, out = {}, {}
    out["product"], out["variant"] = _resolve_entity(post.get("entity"))
    if out["product"] is None:
        errors["entity"] = _("Bitte einen Artikel wählen.")
    if art in ("receipt", "transfer"):
        out["qty"] = _number(post.get("qty"), lo=1, hi=MAX_QTY)
        if out["qty"] is None:
            errors["qty"] = _range_error(1, MAX_QTY)
    elif art == "adjustment":
        out["delta"] = _number(post.get("delta"), lo=-MAX_QTY, hi=MAX_QTY, signed=True)
        if not out["delta"]:  # None или 0: «0» — это не корректировка
            errors["delta"] = _("Bitte eine Menge wie -2 oder 3 angeben.")
        reason = post.get("reason") or ""
        out["reason"] = reason if reason in dict(ADJUST_REASONS) else ""
    elif art == "stocktake":
        out["counted"] = _number(post.get("counted"), lo=0, hi=MAX_QTY)
        if out["counted"] is None:
            errors["counted"] = _range_error(0, MAX_QTY)
    if art == "receipt" and lots_on:
        out["lot_code"] = (post.get("lot_code") or "").strip()[:64]
        raw = (post.get("lot_mhd") or "").strip()
        out["lot_mhd"] = None
        if raw:
            try:
                out["lot_mhd"] = date.fromisoformat(raw)
            except ValueError:
                errors["lot_mhd"] = _("Invalid date.")
    if art == "receipt":
        # Ревью D6.2a: неизвестный/неактивный Standort — ошибка, а не тихий «Hauptlager».
        out["location"] = None
        raw = post.get("location") or ""
        if raw:
            active = {str(loc.pk): loc for loc in StockLocation.objects.filter(is_active=True)}
            out["location"] = active.get(raw)
            if out["location"] is None:
                errors["location"] = _("Umlagerung nicht möglich (Bestand/Standorte prüfen).")
    if art == "transfer":
        ids = {str(loc.pk): loc for loc in StockLocation.objects.filter(is_active=True)}
        out["src"], out["dst"] = ids.get(post.get("src") or ""), ids.get(post.get("dst") or "")
        if out["src"] is None or out["dst"] is None or out["src"] == out["dst"]:
            errors["dst"] = _("Umlagerung nicht möglich (Bestand/Standorte prüfen).")
    out["note"] = (post.get("note") or "").strip()[:200]
    return out, errors


def _book(request, art: str, v: dict, *, lots_on: bool) -> tuple[bool, str]:
    """Провести операцию тем же путём, что прежние формы. → (успех, текст для человека)."""
    actor = getattr(request.user, "username", "") or ""
    product, variant = v["product"], v["variant"]
    if art == "receipt":
        location = v["location"]
        if lots_on:
            services.receive_lot(
                product=product,
                variant=variant,
                qty=v["qty"],
                mhd=v["lot_mhd"],
                lot_code=v["lot_code"],
                actor=actor,
                note=v["note"],
                location=location,
            )
            return True, _("Wareneingang (Charge) gebucht.")
        services.apply_manual_movement(
            product=product,
            variant=variant,
            kind=StockMovement.KIND_RECEIPT,
            delta=v["qty"],
            actor=actor,
            note=v["note"],
            location=location,
        )
        return True, _("Wareneingang gebucht.")
    if art == "adjustment":
        from .views import _adjust_note

        note = _adjust_note(request)  # тот же формат «Grund: Text», что у прежней формы
        mv = services.apply_manual_movement(
            product=product,
            variant=variant,
            kind=StockMovement.KIND_ADJUSTMENT,
            delta=v["delta"],
            actor=actor,
            note=note,
        )
        return True, (_("Korrektur gebucht.") if mv else _("Keine Änderung."))
    if art == "stocktake":
        mv = services.apply_manual_movement(
            product=product,
            variant=variant,
            kind=StockMovement.KIND_STOCKTAKE,
            set_absolute=v["counted"],
            actor=actor,
            note=_("Inventur"),
        )
        return True, (_("Inventur gebucht.") if mv else _("Bestand stimmt bereits."))
    moved = locations.transfer(
        product=product,
        variant=variant,
        src=v["src"],
        dst=v["dst"],
        qty=v["qty"],
        actor=actor,
    )
    if moved:
        return True, _("Umlagerung gebucht: %(n)s Stück.") % {"n": moved}
    return False, _("Umlagerung nicht möglich (Bestand/Standorte prüfen).")


@login_required
@drawer_mod.drawer_aware
def stock_book(request):
    from .views import ADJUST_REASONS

    lots_on = services.lots_enabled(request.tenant)
    stock_locations = list(StockLocation.objects.filter(is_active=True))
    arts = _arts(len(stock_locations) > 1)
    art = (request.POST.get("art") if request.method == "POST" else request.GET.get("art")) or ""
    posted_art_ok = art in arts
    if not posted_art_ok:
        art = arts[0]

    def render_form(values, errors=None):
        entities = services.stock_entities()
        current = values.get("entity") or ""
        if current not in {e["value"] for e in entities}:
            current = ""  # чужая/удалённая сущность не выбирается молча (урок D1.3)
        ctx = {
            "nav": "stock",
            "art": art,
            "arts": arts,
            "bv": {**values, "entity": current},
            "bv_errors": errors or {},
            "entities": entities,
            "reasons": ADJUST_REASONS,
            "lots_on": lots_on,
            "stock_locations": stock_locations,
            "next_url": drawer_mod.drawer_next(request, reverse("stock")),
        }
        if request.method == "POST":
            ctx["next_url"] = local_next(request) or ctx["next_url"]
        if drawer_mod.is_drawer(request) or request.GET.get("box") == "1":
            return drawer_mod.fragment(render(request, "inventory/_stock_book_drawer.html", ctx))
        return render(request, "inventory/stock_book.html", ctx)

    if request.method != "POST":
        return render_form({f: (request.GET.get(f) or "")[:64] for f in ("entity",)})
    if not posted_art_ok:
        # Ревью D6.2a: устаревшая форма (перемещение после выключения Standort) не должна
        # молча стать приходом — ничего не проводим, показываем форму заново.
        messages.error(request, _("Invalid input."))
        return render_form({"entity": (request.POST.get("entity") or "")[:64]})
    values, errors = parse(request.POST, art, lots_on=lots_on)
    keep = {f: (request.POST.get(f) or "").strip()[:200] for f in FIELDS}
    if errors:
        if drawer_mod.is_drawer(request):  # шторка показывает его в role=alert
            messages.error(request, next(iter(errors.values())))
        return render_form(keep, errors)
    ok, text = _book(request, art, values, lots_on=lots_on)
    if not ok:
        messages.error(request, text)  # одно сообщение (без дубля у поля)
        return render_form(keep)
    messages.success(request, text)
    return redirect(local_next(request) or reverse("stock"))
