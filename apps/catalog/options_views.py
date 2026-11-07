"""FB-24b: экран «Sortiment › Optionen» — типы опций магазина и их значения, + оси товара.

Пишет только через `catalog.options` (единственный писатель). Удаление типа/значения —
только если им не пользуется ни один вариант (иначе — «ausblenden»: варианты и заказы
держатся за значения).
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.catalog import option_types as reg
from apps.catalog import options
from apps.catalog.models import OptionType, OptionValue, Product

from .option_styles import VARIANT_STYLES


@login_required
def option_list(request):
    if request.method == "POST":
        _apply(request)
        return redirect("catalog:option-list")
    types = list(OptionType.objects.prefetch_related("values").order_by("sort_order", "id"))
    enabled = {t.code for t in types if t.is_active}
    standard = [
        {"code": code, "label": label, "google": bool(google), "on": code in enabled}
        for code, (label, google, _key) in reg.STANDARD.items()
    ]
    rows = []
    for t in types:
        rows.append(
            {
                "type": t,
                "label": reg.type_label(t),
                "standard": bool(t.standard),
                "field_backed": t.code in reg.FIELD_BACKED,
                "values": list(t.values.all()),
                "in_use": options.type_in_use(t),
            }
        )
    return render(
        request,
        "catalog/option_list.html",
        {
            "nav": "options",
            "standard": standard,
            "rows": rows,
            "display_options": VARIANT_STYLES,
            "max_values": reg.MAX_VALUES,
        },
    )


def _apply(request) -> None:
    action = request.POST.get("action", "")
    if action == "standard":
        code = request.POST.get("code", "")
        if request.POST.get("on") == "1":
            if options.enable_standard(code):
                messages.success(request, _("Option aktiviert."))
        else:
            OptionType.objects.filter(code=code).update(is_active=False)
            messages.success(request, _("Option ausgeblendet."))
        return
    if action == "add":
        if options.add_custom(request.POST.get("name", "")):
            messages.success(request, _("Option angelegt."))
        else:
            messages.error(request, _("Bitte einen Namen angeben (höchstens 30 Optionen)."))
        return
    option_type = get_object_or_404(OptionType, pk=request.POST.get("type") or 0)
    if action == "save":
        if not option_type.standard:
            name = " ".join(request.POST.get("name", "").split())[:60]
            if name:
                option_type.name = name
        display = request.POST.get("display", "")
        option_type.display = display if display in {k for k, *_r in VARIANT_STYLES} else ""
        option_type.is_active = request.POST.get("is_active") == "on"
        option_type.save(update_fields=["name", "display", "is_active", "updated_at"])
        for value in option_type.values.all():
            order = request.POST.get(f"order_{value.pk}", "")
            if order.isdigit() and int(order) != value.sort_order:
                value.sort_order = int(order)
                value.save(update_fields=["sort_order", "updated_at"])
        added = options.add_values(option_type, request.POST.get("new_values", ""))
        messages.success(
            request, _("Gespeichert.") if not added else _("Gespeichert, Werte ergänzt.")
        )
        return
    if action == "delete":
        if options.type_in_use(option_type):
            messages.error(request, _("Wird von Varianten benutzt — bitte nur ausblenden."))
        else:
            option_type.delete()
            messages.success(request, _("Option gelöscht."))
        return
    if action == "delete_value":
        value = get_object_or_404(
            OptionValue, pk=request.POST.get("value") or 0, option_type=option_type
        )
        if options.value_in_use(value):
            messages.error(request, _("Dieser Wert wird von Varianten benutzt."))
        else:
            value.delete()
            messages.success(request, _("Wert gelöscht."))


@login_required
@require_POST
def product_axes(request, pk):
    """Оси вариантов товара (≤ 3 из активных типов магазина)."""
    product = get_object_or_404(Product, pk=pk)
    axes = options.set_product_axes(product, request.POST.getlist("axes"))
    if len(request.POST.getlist("axes")) > reg.MAX_AXES:
        messages.warning(request, _("Höchstens drei Optionen pro Produkt."))
    elif axes:
        messages.success(request, _("Optionen des Produkts gespeichert."))
    return redirect("catalog:product-edit", pk=pk)


def product_axis_rows(product) -> list[dict]:
    """Для формы товара: активные типы магазина + отметка «ось этого товара»."""
    axes = options.product_axes(product)
    rows = [
        {"code": code, "label": reg.standard_label(code), "on": code in axes}
        for code in reg.FIELD_BACKED
    ]
    for t in options.shop_types():
        if t.code in reg.FIELD_BACKED:
            continue
        rows.append({"code": t.code, "label": reg.type_label(t), "on": t.code in axes})
    return rows
