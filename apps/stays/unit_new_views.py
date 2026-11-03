"""UX-D D4.5: «＋ Zimmer» — короткая форма нового номера шторкой (общий контракт
`docs/references/patterns/drawer.md`). Раньше — постоянно раскрытая форма
`<details id="neu">` над списком номеров со всеми полями номера.

Только то, без чего номер не продать: имя, тип, цена за ночь, НДС, количество,
вместимость (+ «Mehr»: минимум ночей, предоплата). Фото, описание, удобства,
комнаты, сезоны — на странице номера после создания. Ввод разбирается строго:
ошибка у поля, введённое сохраняется (прецедент D2.2 «＋ Leistung»).
Права: GET — `sortiment.view`, POST — `preise.edit` (номер создаётся с ценой; как
гейт `RATE_EDIT_ACTIONS` действия `unit`).
"""

from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.core import drawer as drawer_mod
from apps.core import setup_assistant, vat
from apps.core.owner_login import local_next

from .models import StayUnit
from .settings_actions import _strict_int

MAX_PRICE_CENTS = 10_000_000  # 100 000 € за ночь — потолок
FIELDS = (
    "name",
    "type",
    "price_eur",
    "vat_rate",
    "quantity",
    "max_guests",
    "min_nights",
    "deposit_eur",
)


def _cents(raw):
    """Сумма формы → центы; пусто → 0; мусор/вне диапазона → None."""
    from apps.core.money import parse_money

    try:
        value = parse_money(raw or "")
    except ValueError:
        return None
    if value is None:
        return 0
    cents = int(round(value * 100))
    return cents if 0 <= cents <= MAX_PRICE_CENTS else None


def parse_unit(post) -> tuple[dict, dict]:
    """Поля короткой формы → (значения StayUnit, ошибки {поле формы: текст})."""
    errors, values = {}, {}
    name = (post.get("name") or "").strip()
    if not name:
        errors["name"] = _("Bitte einen Namen angeben.")
    values["name"] = name[:120]
    kind = post.get("type") or StayUnit.TYPE_ROOM
    values["type"] = kind if kind in dict(StayUnit.TYPES) else StayUnit.TYPE_ROOM
    for field, model_field in (("price_eur", "price_cents"), ("deposit_eur", "deposit_cents")):
        cents = _cents(post.get(field))
        if cents is None:
            errors[field] = _("Bitte einen Betrag wie 25,00 angeben.")
        else:
            values[model_field] = cents
    ints = {"quantity": (1, 999, 1), "max_guests": (1, 99, 2), "min_nights": (1, 365, 1)}
    for field, (lo, hi, default) in ints.items():
        raw = (post.get(field) or "").strip()
        value = _strict_int(raw, lo, hi) if raw else default
        if value is None or value == 0:
            errors[field] = _("Bitte eine Zahl von %(lo)s bis %(hi)s angeben.") % {
                "lo": lo,
                "hi": hi,
            }
        else:
            values[field] = value
    values["vat_rate"] = vat.parse_rate(post.get("vat_rate"), Decimal("7.00"))
    return values, errors


def _values_for_form(data) -> dict:
    return {f: (data.get(f) or "")[:120] for f in FIELDS}


@login_required
@drawer_mod.drawer_aware
def unit_new(request):
    def render_form(values, errors=None):
        ctx = {
            "nav": "units",
            "uv": values,
            "uv_errors": errors or {},
            "types": StayUnit.TYPES,
            "next_url": drawer_mod.drawer_next(request, reverse("stays:units")),
        }
        if request.method == "POST":
            ctx["next_url"] = local_next(request) or ctx["next_url"]
        if drawer_mod.is_drawer(request) or request.GET.get("box") == "1":
            return drawer_mod.fragment(render(request, "stays/_unit_new_drawer.html", ctx))
        return render(request, "stays/unit_new.html", ctx)

    if request.method == "POST":
        values, errors = parse_unit(request.POST)
        if errors:
            if drawer_mod.is_drawer(request):  # шторка показывает его в role=alert
                messages.error(request, next(iter(errors.values())))
            return render_form(_values_for_form(request.POST), errors)
        unit = StayUnit.objects.create(**values)
        messages.success(request, _("Unit created."))
        return redirect(reverse("stays:unit-edit", args=[unit.pk]))
    return render_form(
        _values_for_form(setup_assistant.prefill(request, setup_assistant.ENTITY_ROOM))
    )
