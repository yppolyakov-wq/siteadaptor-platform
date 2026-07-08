"""U-D3.3: кабинет склада — приёмки/корректировки/инвентаризация + реконсиляция.

Ручные движения меняют счётчик И пишут леджер в одной atomic (services.
apply_manual_movement). Реконсиляция сверяет счётчик с суммой дельт леджера;
«Startbestand buchen» проводит стартовый остаток (выравнивает леджер под счётчик).
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.catalog.models import Product

from . import services
from .models import StockMovement

DEFAULT_THRESHOLD = 5

# R3: причины ручной корректировки (ретейл списывает бой/усушку/кражу отдельно).
ADJUST_REASONS = [
    ("korrektur", _("Korrektur")),
    ("schwund", _("Schwund")),
    ("bruch", _("Bruch")),
    ("verderb", _("Verderb")),
    ("diebstahl", _("Diebstahl")),
    ("sonstiges", _("Sonstiges")),
]
_REASON_LABELS = {k: v for k, v in ADJUST_REASONS}


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


def _resolve_entity(value):
    """T2: разобрать значение пикера "p<pk>"/"v<pk>" → (product, variant)."""
    from apps.catalog.models import ProductVariant

    value = value or ""
    if value.startswith("v"):
        v = ProductVariant.objects.filter(pk=value[1:]).select_related("product").first()
        return (v.product, v) if v else (None, None)
    if value.startswith("p"):
        p = Product.objects.filter(pk=value[1:]).first()
        return (p, None) if p else (None, None)
    return (None, None)


def _export_csv():
    """T4: экспорт движений склада в CSV (последние 5000)."""
    import csv

    from django.http import HttpResponse

    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = "attachment; filename=lagerbewegungen.csv"
    w = csv.writer(resp)
    w.writerow(["Datum", "Produkt", "Variante", "Art", "Menge", "Quelle", "Notiz"])
    for mv in StockMovement.objects.select_related("product", "variant").all()[:5000]:
        w.writerow(
            [
                mv.created_at.strftime("%Y-%m-%d %H:%M"),
                str(mv.product),
                mv.variant.label if mv.variant else "",
                mv.get_kind_display(),
                mv.delta,
                mv.source,
                mv.note,
            ]
        )
    return resp


@login_required
def stock(request):
    if request.method == "POST":
        return _handle_post(request)
    if request.GET.get("export") == "csv":  # T4: CSV-экспорт движений
        return _export_csv()

    threshold = _threshold(request.tenant)
    rows = services.reconciliation_rows()  # T2: товары БЕЗ вариантов + варианты
    low = [r for r in rows if r["counter"] <= threshold]
    diverging = [r for r in rows if not r["ok"]]
    warenwert = services.inventory_value()  # T5: Bestandswert (Σ Bestand × EK)
    reorder = services.reorder_suggestions(threshold)  # T5: Bestellvorschläge
    # T4: drill-down истории по сущности (?history=p<pk>/v<pk>).
    mv_qs = StockMovement.objects.select_related("product", "variant")
    history, history_label = request.GET.get("history", ""), ""
    if history:
        hp, hv = _resolve_entity(history)
        if hp is not None:
            mv_qs = mv_qs.filter(product=hp)
            mv_qs = (
                mv_qs.filter(variant=hv) if hv is not None else mv_qs.filter(variant__isnull=True)
            )
            history_label = f"{hp} · {hv.label}" if hv is not None else str(hp)
    movements = mv_qs.all()[: 100 if history else 50]
    # R1: поиск по SKU/EAN (scan-to-count) — найденную сущность подсвечиваем.
    found = None
    code = (request.GET.get("code") or "").strip()
    if code:
        product, variant = services.find_entity_by_code(code)
        if product is not None:
            entity = variant if variant is not None else product
            found = {
                "value": f"v{variant.pk}" if variant is not None else f"p{product.pk}",
                "label": f"{product} · {variant.label}" if variant is not None else str(product),
                "counter": entity.stock_quantity,
            }
    return render(
        request,
        "inventory/stock.html",
        {
            "nav": "stock",
            "rows": rows,
            "low": low,
            "diverging": diverging,
            "movements": movements,
            "entities": services.stock_entities(),
            "warenwert": warenwert,
            "reorder": reorder,
            "threshold": threshold,
            "reasons": ADJUST_REASONS,
            "code": code,
            "found": found,
            "history": history,
            "history_label": history_label,
        },
    )


def _adjust_note(request):
    """R3: собрать заметку корректировки из причины (Schwund/Bruch/…) + свободного текста."""
    reason = str(_REASON_LABELS.get(request.POST.get("reason", ""), ""))
    free = (request.POST.get("note") or "").strip()
    return (f"{reason}: {free}" if reason and free else (reason or free))[:200]


def _handle_bulk_stocktake(request, actor):
    """R1b: инвентаризация по Zählliste — на каждую сущность с полем count_<value>
    книжим разницу до факта (stocktake). Пустое поле — пропуск."""
    n = 0
    for e in services.stock_entities():
        raw = request.POST.get(f"count_{e['value']}")
        if raw is None or raw.strip() == "":
            continue
        counted = _int(raw, -1)
        if counted < 0:
            continue
        mv = services.apply_manual_movement(
            product=e["product"],
            variant=e["variant"],
            kind=StockMovement.KIND_STOCKTAKE,
            set_absolute=counted,
            actor=actor,
            note=str(_("Inventur")),
        )
        if mv:
            n += 1
    messages.success(request, _("Inventur gebucht: %(n)s Korrektur(en).") % {"n": n})
    return redirect("stock")


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

    if action == "stocktake_bulk":
        return _handle_bulk_stocktake(request, actor)

    product, variant = _resolve_entity(request.POST.get("entity"))
    if product is None:
        messages.error(request, _("Bitte einen Artikel wählen."))
        return redirect("stock")

    if action == "receipt":
        qty = _int(request.POST.get("qty"))
        if qty <= 0:
            messages.error(request, _("Menge muss größer als 0 sein."))
        else:
            services.apply_manual_movement(
                product=product,
                variant=variant,
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
            variant=variant,
            kind=StockMovement.KIND_ADJUSTMENT,
            delta=delta,
            actor=actor,
            note=_adjust_note(request),  # R3: причина (Schwund/Bruch/…) + текст
        )
        messages.success(request, _("Korrektur gebucht.") if mv else _("Keine Änderung."))
    elif action == "stocktake":
        counted = _int(request.POST.get("counted"), -1)
        if counted < 0:
            messages.error(request, _("Bitte gezählten Bestand eingeben."))
        else:
            mv = services.apply_manual_movement(
                product=product,
                variant=variant,
                kind=StockMovement.KIND_STOCKTAKE,
                set_absolute=counted,
                actor=actor,
                note=_("Inventur"),
            )
            messages.success(
                request, _("Inventur gebucht.") if mv else _("Bestand stimmt bereits.")
            )
    elif action == "reconcile":
        mv = services.record_opening_balance(product=product, variant=variant, actor=actor)
        messages.success(request, _("Startbestand gebucht.") if mv else _("Bereits abgeglichen."))
    return redirect("stock")
