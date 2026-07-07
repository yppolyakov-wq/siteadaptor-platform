"""U-D3.3: кабинет склада — приёмки/корректировки/инвентаризация + реконсиляция.

Ручные движения меняют счётчик И пишут леджер в одной atomic (services.
apply_manual_movement). Реконсиляция сверяет счётчик с суммой дельт леджера;
«Startbestand buchen» проводит стартовый остаток (выравнивает леджер под счётчик).
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.catalog.models import Product

from . import services
from .models import StockMovement

DEFAULT_THRESHOLD = 5


def _threshold(tenant) -> int:
    cfg = tenant.site_config if isinstance(getattr(tenant, "site_config", None), dict) else {}
    try:
        return max(0, int(cfg.get("low_stock_threshold", DEFAULT_THRESHOLD)))
    except (TypeError, ValueError):
        return DEFAULT_THRESHOLD


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@login_required
def stock(request):
    if request.method == "POST":
        return _handle_post(request)

    threshold = _threshold(request.tenant)
    tracked = Product.objects.filter(stock_quantity__isnull=False).order_by("name")
    rows = [{"product": p, **services.reconciliation(p)} for p in tracked]
    low = [r for r in rows if r["counter"] is not None and r["counter"] <= threshold]
    diverging = [r for r in rows if not r["ok"]]
    movements = StockMovement.objects.select_related("product", "variant").all()[:50]
    return render(
        request,
        "inventory/stock.html",
        {
            "nav": "stock",
            "rows": rows,
            "low": low,
            "diverging": diverging,
            "movements": movements,
            "products": Product.objects.order_by("name"),
            "threshold": threshold,
        },
    )


@require_POST
def _handle_post(request):
    action = request.POST.get("action", "")
    actor = getattr(request.user, "username", "") or ""

    if action == "threshold":
        tenant = request.tenant
        cfg = tenant.site_config if isinstance(tenant.site_config, dict) else {}
        cfg["low_stock_threshold"] = max(0, _int(request.POST.get("value"), DEFAULT_THRESHOLD))
        tenant.site_config = cfg
        tenant.save(update_fields=["site_config"])
        messages.success(request, _("Meldebestand aktualisiert."))
        return redirect("stock")

    product = get_object_or_404(Product, pk=request.POST.get("product"))

    if action == "receipt":
        qty = _int(request.POST.get("qty"))
        if qty <= 0:
            messages.error(request, _("Menge muss größer als 0 sein."))
        else:
            services.apply_manual_movement(
                product=product,
                kind=StockMovement.KIND_RECEIPT,
                delta=qty,
                actor=actor,
                note=(request.POST.get("note") or "")[:200],
            )
            messages.success(request, _("Wareneingang gebucht."))
    elif action == "adjustment":
        delta = _int(request.POST.get("delta"))
        mv = services.apply_manual_movement(
            product=product,
            kind=StockMovement.KIND_ADJUSTMENT,
            delta=delta,
            actor=actor,
            note=(request.POST.get("note") or "")[:200],
        )
        messages.success(request, _("Korrektur gebucht.") if mv else _("Keine Änderung."))
    elif action == "stocktake":
        counted = _int(request.POST.get("counted"), -1)
        if counted < 0:
            messages.error(request, _("Bitte gezählten Bestand eingeben."))
        else:
            mv = services.apply_manual_movement(
                product=product,
                kind=StockMovement.KIND_STOCKTAKE,
                set_absolute=counted,
                actor=actor,
                note=_("Inventur"),
            )
            messages.success(
                request, _("Inventur gebucht.") if mv else _("Bestand stimmt bereits.")
            )
    elif action == "reconcile":
        mv = services.record_opening_balance(product=product, actor=actor)
        messages.success(request, _("Startbestand gebucht.") if mv else _("Bereits abgeglichen."))
    return redirect("stock")
