"""UX-D D6.1: «Zusatzleistungen» — список строками, «＋ Zusatzleistung» шторкой и страница
допа (правка всех полей, фото, переводы, блок «Gefahr»).

Раньше у каждой строки висели 4 формы, форма создания (13 полей) была раскрыта, а править
доп после создания было нельзя вовсе — только удалить и завести заново.

Разбор полей — один на создание и правку (`parse`): строгий, ошибка у поля, ввод
сохраняется, ничего не пишется (класс D6.0: цена «1.234,50» молча давала 0 €).
Шторка — короткая форма (название, цена, где действует, за ночь); остальное — на странице.
Контракт шторки — `docs/references/patterns/drawer.md`."""

from __future__ import annotations

import re
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.core import drawer as drawer_mod
from apps.core import vat
from apps.core.i18n_input import apply_i18n_overlay
from apps.core.models import Extra
from apps.core.owner_login import local_next

NEW_FIELDS = ("label", "price", "scope", "per_night")
PAGE_FIELDS = (
    "label",
    "price",
    "scope",
    "per_night",
    "vat_rate",
    "entity",
    "tracker",
    "pool_size",
    "supplier",
    "stock_product",
    "consume_qty",
)


def _int(raw, lo: int, hi: int, default: int):
    """Целое из формы: пусто → default; мусор/вне границ → None (pitfalls §3: только ASCII)."""
    raw = (raw or "").strip()
    if not raw:
        return default
    if not re.fullmatch(r"[0-9]{1,4}", raw):
        return None
    value = int(raw)
    return value if lo <= value <= hi else None


def _uuid_or_none(raw):
    try:
        return uuid.UUID(str(raw or ""))
    except ValueError:
        return None


def parse(post, *, full: bool, current=None) -> tuple[dict, dict]:
    """Строгий разбор формы допа → (поля модели, ошибки {поле: текст}).

    `full=False` — короткая форма шторки: адресность/трекер/ставка не присланы и
    остаются по умолчанию (как у старой формы «New extra» без этих полей)."""
    from apps.core.money import parse_amount, to_cents
    from apps.core.views import _extra_entity_kinds

    errors, out = {}, {}
    label = (post.get("label") or "").strip()
    if not label:
        errors["label"] = _("Bitte einen Namen angeben.")
    elif len(label) > 120:
        errors["label"] = _("Höchstens %(n)s Zeichen.") % {"n": 120}
    out["label"] = label[:120]
    try:
        price = parse_amount(post.get("price"))
    except ValueError:
        errors["price"] = _("Bitte einen Betrag wie 25,00 angeben.")
        price = None
    out["price_cents"] = to_cents(price) if price is not None else 0
    scope = post.get("scope") or Extra.SCOPE_ALL
    out["scope"] = scope if scope in dict(Extra.SCOPES) else Extra.SCOPE_ALL
    out["per_night"] = bool(post.get("per_night"))
    if not full:
        return out, errors

    out["vat_rate"] = vat.parse_rate_optional(post.get("vat_rate"))
    out["entity_kind"], out["entity_id"] = "", ""
    kind, _sep, eid = (post.get("entity") or "").partition(":")
    if kind in _extra_entity_kinds() and eid:
        out["entity_kind"], out["entity_id"] = kind, eid[:64]
    tracker = post.get("tracker", "")
    out["tracker"] = tracker if tracker in dict(Extra.TRACKERS) else ""
    pool = _int(post.get("pool_size"), 0, 999, 0)
    if pool is None:
        errors["pool_size"] = _("Bitte eine Zahl von %(lo)s bis %(hi)s angeben.") % {
            "lo": 0,
            "hi": 999,
        }
        pool = 0
    out["pool_size"] = pool if out["tracker"] == Extra.TRACKER_POOL else 0
    out["supplier"] = None
    if out["tracker"] == Extra.TRACKER_PURCHASE and post.get("supplier"):
        from apps.inventory.models import Lieferant

        pk = _uuid_or_none(post.get("supplier"))
        out["supplier"] = Lieferant.objects.filter(pk=pk).first() if pk else None
    out["product"], out["consume_qty"] = None, 1
    if out["tracker"] == Extra.TRACKER_STOCK:
        from apps.catalog.models import Product

        pk = _uuid_or_none(post.get("stock_product"))
        out["product"] = Product.objects.filter(pk=pk).first() if pk else None
        # Ревью D6.1 (W0): у складского допа товар могли удалить (SET_NULL) — такой доп
        # сохраняется как был, пока учёт/товар не трогают; новая привязка требует товара.
        kept = (
            current is not None
            and current.tracker == Extra.TRACKER_STOCK
            and current.product_id is None
            and not post.get("stock_product")
        )
        if out["product"] is None and not kept:
            errors["stock_product"] = _("Bitte einen Lagerartikel wählen.")
        qty = _int(post.get("consume_qty"), 1, 99, 1)
        if qty is None:
            errors["consume_qty"] = _("Bitte eine Zahl von %(lo)s bis %(hi)s angeben.") % {
                "lo": 1,
                "hi": 99,
            }
            qty = 1
        out["consume_qty"] = qty
    return out, errors


def page_url(extra) -> str:
    return reverse("extra-edit", args=[extra.pk])


def _values_from_post(post) -> dict:
    """Ввод для повтора формы после ошибки (строки, обрезанные)."""
    return {f: (post.get(f) or "").strip()[:120] for f in PAGE_FIELDS}


def _values_from_extra(extra) -> dict:
    from apps.core.form_fields import format_money

    return {
        "label": extra.label,
        "price": format_money(extra.price_eur) if extra.price_cents else "",
        "scope": extra.scope,
        "per_night": "on" if extra.per_night else "",
        "vat_rate": "" if extra.vat_rate is None else str(extra.vat_rate),
        "entity": f"{extra.entity_kind}:{extra.entity_id}" if extra.entity_kind else "",
        "tracker": extra.tracker,
        "pool_size": str(extra.pool_size or ""),
        "supplier": str(extra.supplier_id or ""),
        "stock_product": str(extra.product_id or ""),
        "consume_qty": str(extra.consume_qty or 1),
    }


@login_required
@drawer_mod.drawer_aware
def extra_new(request):
    """«＋ Zusatzleistung»: короткая форма шторкой (без JS — страница)."""

    def render_form(values, errors=None):
        ctx = {
            "nav": "extras",
            "xv": values,
            "xv_errors": errors or {},
            "scopes": Extra.SCOPES,
            "next_url": drawer_mod.drawer_next(request, reverse("extras")),
        }
        if request.method == "POST":
            ctx["next_url"] = local_next(request) or ctx["next_url"]
        if drawer_mod.is_drawer(request) or request.GET.get("box") == "1":
            return drawer_mod.fragment(render(request, "tenant/_extra_new_drawer.html", ctx))
        return render(request, "tenant/extra_new.html", ctx)

    if request.method != "POST":
        return render_form({"scope": Extra.SCOPE_ALL})
    values, errors = parse(request.POST, full=False)
    if errors:
        if drawer_mod.is_drawer(request):  # шторка показывает его в role=alert
            messages.error(request, next(iter(errors.values())))
        return render_form(_values_from_post(request.POST), errors)
    extra = Extra.objects.create(**values)
    messages.success(request, _("Extra added."))
    return redirect(page_url(extra))


PAGE_ACTIONS = frozenset({"extra_update", "set_image", "toggle", "delete"})


@login_required
def extra_edit(request, pk):
    """Страница допа: одна форма всех полей + фото + переводы + «Gefahr»."""
    from apps.core import views as core_views

    extra = get_object_or_404(Extra.objects.select_related("supplier", "product"), pk=pk)
    tenant = getattr(request, "tenant", None)
    errors, values = {}, None
    if request.method == "POST":
        action = request.POST.get("action", "")
        # Страница правит только СВОЙ доп: чужой pk в POST — 404, не тихая правка.
        if action not in PAGE_ACTIONS or request.POST.get("extra") != str(extra.pk):
            raise Http404
        if action == "delete":
            extra.delete()
            messages.success(request, _("Extra removed."))
            return redirect("extras")
        if action == "toggle":
            target = request.POST.get("active") == "1"  # явное состояние: двойной клик не откатит
            if extra.is_active != target:
                extra.is_active = target
                extra.save(update_fields=["is_active", "updated_at"])
            messages.success(request, _("Saved."))
            return redirect(page_url(extra))
        if action == "set_image":
            if core_views._set_extra_image(request, extra):
                messages.success(request, _("Photo updated."))
            else:
                messages.error(request, _("Couldn't upload the image — please try another file."))
            return redirect(page_url(extra))
        parsed, errors = parse(request.POST, full=True, current=extra)
        if not errors:
            for field, value in parsed.items():
                setattr(extra, field, value)
            changed = apply_i18n_overlay(extra, request.POST, tenant, fields=("label",))
            extra.save(update_fields=[*parsed, *changed, "updated_at"])
            messages.success(request, _("Saved."))
            return redirect(page_url(extra))
        # Ошибка — у поля (aria-invalid + фокус); flash дублировал бы её на странице.
        values = _values_from_post(request.POST)

    entity_choices = core_views._extra_entity_choices(request)
    current = f"{extra.entity_kind}:{extra.entity_id}" if extra.entity_kind else ""
    if current and current not in {v for v, _label in entity_choices}:
        # Адресат снят с продажи/удалён — не теряем привязку молча при следующем Save.
        label = core_views._extra_entity_labels().get(current) or _("gelöschtes Objekt")
        entity_choices = [(current, label), *entity_choices]
    suppliers = core_views._extra_suppliers()
    if extra.supplier_id and extra.supplier_id not in {sp.pk for sp in suppliers}:
        suppliers = [extra.supplier, *suppliers]  # неактивный поставщик не теряется при Save
    stock_products = core_views._extra_stock_products()
    if extra.product_id and extra.product_id not in {p.pk for p in stock_products}:
        stock_products = [extra.product, *stock_products]
    return render(
        request,
        "tenant/extra_page.html",
        {
            "nav": "extras",
            "x": extra,
            "xv": values or _values_from_extra(extra),
            "xv_errors": errors,
            "scopes": Extra.SCOPES,
            "trackers": Extra.TRACKERS,
            "entity_choices": entity_choices,
            "suppliers": suppliers,
            "stock_products": stock_products,
        },
        status=200,
    )
