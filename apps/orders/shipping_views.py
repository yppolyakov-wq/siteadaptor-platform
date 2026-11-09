"""SHP-3: экран способов доставки — форма способа (новый/правка), включение, порядок.

Список способов живёт на вкладке «Zahlung & Lieferung › Lieferung & Abholung»
(`templates/tenant/_shipping_methods.html`). Форма открывается шторкой (UX-D D1), без JS —
обычной страницей. Пишет только `orders.shipping_admin`.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core import drawer as drawer_mod

from . import carriers, shipping, shipping_admin
from .models import ShippingMethod

KIND_ICONS = {"pickup": "🛍", "courier": "🚚", "carrier": "📦"}


def list_url() -> str:
    return reverse("payment-settings") + "?tab=lieferung"


def _eur(cents) -> str:
    return f"{(cents or 0) / 100:.2f}".replace(".", ",") if cents else ""


def _kg(grams) -> str:
    if not grams:
        return ""
    return f"{grams / 1000:g}".replace(".", ",")


def form_values(method: ShippingMethod) -> dict:
    """Значения формы из способа (суммы — «3,99», вес — «2,5» кг, строки — «a | b»)."""
    return {
        "name": method.name,
        "delivery_time": method.delivery_time,
        "fee": _eur(method.fee_cents),
        "free_from": _eur(method.free_from_cents),
        "min_order": _eur(method.min_order_cents),
        "area_text": method.area_text,
        "carrier": method.carrier,
        "service": method.service or ShippingMethod.SERVICE_HOME,
        "pricing": method.pricing,
        "weight_tiers": "\n".join(
            f"{_kg(t.get('max_g'))} | {_eur(t.get('fee_cents')) or '0'}"
            for t in method.weight_tiers or []
            if isinstance(t, dict)
        ),
        "packaging_g": method.packaging_g or "",
        "default_item_g": method.default_item_g or "",
        "max_weight_kg": _kg(method.max_weight_g),
        "max_length_cm": method.max_length_cm or "",
        "bulky_ok": method.bulky_ok,
        "zones": "\n".join(
            " | ".join(
                [z.get("plz", "")]
                + [
                    _eur(z.get(k)) if z.get(k) not in (None, "") else ""
                    for k in ("fee_cents", "free_cents", "min_cents")
                ]
            ).rstrip(" |")
            for z in method.zones or []
            if isinstance(z, dict)
        ),
        "restrict_to_zones": method.restrict_to_zones,
        "locations": "\n".join(
            f"{p.get('name', '')} | {p.get('address', '')}".rstrip(" |")
            for p in method.locations or []
            if isinstance(p, dict)
        ),
    }


def summary(method: ShippingMethod) -> str:
    """Короткая строка для списка: цена, срок, зоны/пункты."""
    parts = []
    if method.kind == ShippingMethod.KIND_PICKUP:
        n = len([p for p in method.locations or [] if isinstance(p, dict) and p.get("name")])
        parts.append(_("%(n)s Abholorte") % {"n": n} if n > 1 else _("an Ihrer Adresse"))
    elif method.kind == ShippingMethod.KIND_CARRIER and method.pricing == "weight":
        parts.append(_("Preis nach Gewicht"))
    else:
        parts.append(f"{_eur(method.fee_cents)} €" if method.fee_cents else _("kostenlos"))
    if method.free_from_cents and method.kind != ShippingMethod.KIND_PICKUP:
        parts.append(_("kostenlos ab %(eur)s €") % {"eur": _eur(method.free_from_cents)})
    if method.min_order_cents:
        parts.append(_("ab %(eur)s € Bestellwert") % {"eur": _eur(method.min_order_cents)})
    if method.kind == ShippingMethod.KIND_COURIER and method.zones:
        parts.append(_("%(n)s Liefergebiete") % {"n": len(method.zones)})
    if method.delivery_time:
        parts.append(method.delivery_time)
    return " · ".join(str(p) for p in parts)


def list_context(tenant) -> dict:
    rows = []
    for method in shipping.methods(tenant, active_only=False):
        rows.append(
            {
                "m": method,
                "key": "" if shipping.is_legacy(method) else str(method.pk),
                "icon": KIND_ICONS.get(method.kind, "📦"),
                "label": shipping.label(method)
                if not shipping.is_legacy(method)
                else method.get_kind_display(),
                "summary": summary(method),
            }
        )
    return {"shipping_rows": rows, "shipping_legacy": not shipping.has_stored()}


def _render_form(request, ctx):
    if drawer_mod.is_drawer(request) or request.GET.get("box") == "1":
        return drawer_mod.fragment(render(request, "tenant/_shipping_method_drawer.html", ctx))
    return render(request, "tenant/shipping_method.html", ctx)


def _ctx(request, method, values, kind, errors=()):
    carrier_rows = [
        {"code": c.code, "name": c.name, "points": bool(c.pickup_point)} for c in carriers.REGISTRY
    ]
    return {
        "nav": "payments",
        "method": method,
        "kind": kind,
        "kind_label": dict(ShippingMethod.KINDS).get(kind, ""),
        "sv": values,
        "errors": list(errors),
        "carrier_rows": carrier_rows,
        "next_url": drawer_mod.drawer_next(request, list_url()),
    }


@login_required
@drawer_mod.drawer_aware
def shipping_method_new(request):
    """«＋ Versandart»: тип (самовывоз / курьер / Paketdienst) и поля этого типа."""
    kind = request.POST.get("kind") or request.GET.get("art") or ""
    if kind not in dict(ShippingMethod.KINDS):
        kind = ""
    blank = ShippingMethod(kind=kind or ShippingMethod.KIND_CARRIER)
    if request.method == "POST" and kind:
        parsed = shipping_admin.parse(request.POST, kind)
        if parsed.errors:
            for error in parsed.errors:
                messages.error(request, error)
            return _render_form(request, _ctx(request, None, request.POST, kind, parsed.errors))
        shipping_admin.create(request.tenant, kind, parsed.values)
        messages.success(request, _("Versandart gespeichert."))
        return redirect(list_url())
    values = form_values(blank)
    if kind == ShippingMethod.KIND_CARRIER:
        values.update({"carrier": "dhl", "fee": "4,99", "delivery_time": "2–4 Tage"})
    return _render_form(request, _ctx(request, None, values, kind))


@login_required
@drawer_mod.drawer_aware
def shipping_method_edit(request, pk):
    method = get_object_or_404(ShippingMethod, pk=pk)
    if request.method == "POST":
        parsed = shipping_admin.parse(request.POST, method.kind)
        if parsed.errors:
            for error in parsed.errors:
                messages.error(request, error)
            return _render_form(
                request, _ctx(request, method, request.POST, method.kind, parsed.errors)
            )
        shipping_admin.update(request.tenant, method, parsed.values)
        messages.success(request, _("Versandart gespeichert."))
        return redirect(list_url())
    return _render_form(request, _ctx(request, method, form_values(method), method.kind))


@login_required
@require_POST
def shipping_method_toggle(request, pk):
    method = get_object_or_404(ShippingMethod, pk=pk)
    try:
        shipping_admin.set_active(request.tenant, method, request.POST.get("on") == "1")
    except shipping_admin.LastMethod:
        messages.error(
            request,
            _(
                "Mindestens eine Versandart muss aktiv bleiben, sonst können Kunden nicht bestellen."
            ),
        )
    return redirect(list_url())


@login_required
@require_POST
def shipping_method_move(request, pk):
    method = get_object_or_404(ShippingMethod, pk=pk)
    shipping_admin.move(request.tenant, method, 1 if request.POST.get("dir") == "down" else -1)
    return redirect(list_url())


@login_required
@require_POST
def shipping_legacy_toggle(request, kind):
    """Список прежних настроек (строк ещё нет): «Bearbeiten»/выключение сначала переносит
    их в строки — дальше всё через обычные строки."""
    shipping_admin.materialize(request.tenant)
    method = ShippingMethod.objects.filter(kind=kind).order_by("sort_order").first()
    if method is None:
        return redirect(list_url())
    if request.POST.get("action") == "edit":
        return redirect(reverse("shipping-method-edit", args=[method.pk]))
    try:
        shipping_admin.set_active(request.tenant, method, request.POST.get("on") == "1")
    except shipping_admin.LastMethod:
        messages.error(
            request,
            _(
                "Mindestens eine Versandart muss aktiv bleiben, sonst können Kunden nicht bestellen."
            ),
        )
    return redirect(list_url())
