"""UX-D D6.3: «Kollektionen» — список строками с количествами, «＋» шторкой, страница
подборки с вкладками Grundlagen · Inhalt · Fotos.

Раньше каждая подборка была раскрытой карточкой со всеми чекбоксами состава (до 200 товаров)
и формой фото — список из пяти подборок занимал несколько экранов. Вкладки рисует сервер
(`?tab=`), у каждой вкладки своя форма (поля разных вкладок не смешиваются — W0 не нужен).
Состав пишется тем же `_save_members` (D6.0: невидимые члены не теряются)."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.core import drawer as drawer_mod
from apps.core.i18n_input import apply_i18n_overlay, extra_locales, i18n_inputs_for
from apps.core.owner_login import local_next

from .models import Collection
from .views import _save_members, _shown_queryset, _unique_slug

TABS = ("basis", "inhalt", "fotos")


def _modules(request) -> dict:
    tenant = getattr(request, "tenant", None)
    flags = {
        "has_booking": bool(tenant and tenant.is_module_active("booking")),
        "has_stays": bool(tenant and tenant.is_module_active("stays")),
        "has_catalog": bool(tenant and tenant.is_module_active("catalog")),
    }
    if not any(flags.values()):
        raise Http404
    return flags


def annotated(qs, flags):
    """Количества состава для строк списка — одним запросом (раньше 3 запроса на подборку)."""
    ann = {}
    if flags["has_booking"]:
        ann["n_services"] = Count("services", distinct=True)
    if flags["has_stays"]:
        ann["n_units"] = Count("stay_units", distinct=True)
    if flags["has_catalog"]:
        ann["n_products"] = Count(
            "products", filter=Q(products__deleted_at__isnull=True), distinct=True
        )
    return qs.annotate(**ann) if ann else qs


def page_url(collection, tab: str | None = None) -> str:
    url = reverse("collections:edit", args=[collection.pk])
    return f"{url}?tab={tab}" if tab in TABS and tab != TABS[0] else url


@login_required
@drawer_mod.drawer_aware
def collection_new(request):
    """«＋ Kollektion» — имя шторкой; переводы, состав и фото — на странице подборки."""
    _modules(request)
    error = ""
    name = (request.POST.get("name") or "").strip() if request.method == "POST" else ""
    if request.method == "POST":
        if not name:
            error = _("Bitte einen Namen angeben.")
        elif len(name) > 120:
            error = _("Höchstens %(n)s Zeichen.") % {"n": 120}
        else:
            collection = Collection.objects.create(name=name, slug=_unique_slug(name))
            messages.success(request, _("Collection created."))
            return redirect(page_url(collection, "inhalt"))
        if drawer_mod.is_drawer(request):
            messages.error(request, error)
    ctx = {
        "nav": "collections",
        "cv_name": name,
        "cv_error": error,
        "next_url": drawer_mod.drawer_next(request, reverse("collections:list")),
    }
    if request.method == "POST":
        ctx["next_url"] = local_next(request) or ctx["next_url"]
    if drawer_mod.is_drawer(request) or request.GET.get("box") == "1":
        return drawer_mod.fragment(render(request, "collections/_new_drawer.html", ctx))
    return render(request, "collections/new.html", ctx)


PAGE_ACTIONS = frozenset({"basis", "members", "photo", "toggle", "delete"})


@login_required
def collection_edit(request, pk):
    flags = _modules(request)
    tenant = getattr(request, "tenant", None)
    collection = get_object_or_404(Collection, pk=pk)
    if request.method == "POST":
        action = request.POST.get("action", "")
        # Страница правит только СВОЮ подборку: чужой pk в POST — 404, не тихая правка.
        if action not in PAGE_ACTIONS or request.POST.get("collection") != str(collection.pk):
            raise Http404
        tab = "basis"
        if action == "delete":
            collection.delete()
            messages.success(request, _("Collection deleted."))
            return redirect("collections:list")
        if action == "toggle":
            target = request.POST.get("active") == "1"  # явное состояние: двойной клик не откатит
            if collection.is_active != target:
                collection.is_active = target
                collection.save(update_fields=["is_active", "updated_at"])
            messages.success(request, _("Collection saved."))
        elif action == "basis":
            name = (request.POST.get("name") or "").strip()
            raw = (request.POST.get("sort_order") or "0").strip()
            if not name or len(name) > 120:
                messages.error(request, _("Bitte einen Namen angeben."))
            elif not raw.isascii() or not raw.isdigit() or int(raw) > 999:
                messages.error(
                    request,
                    _("Bitte eine Zahl von %(lo)s bis %(hi)s angeben.") % {"lo": 0, "hi": 999},
                )
            else:
                collection.name, collection.sort_order = name, int(raw)
                changed = apply_i18n_overlay(collection, request.POST, tenant, fields=("name",))
                collection.save(update_fields=["name", "sort_order", "updated_at", *changed])
                messages.success(request, _("Collection saved."))
        elif action == "members":
            tab = "inhalt"
            if flags["has_booking"] and request.POST.get("services_present"):
                _save_members(request, collection.services, "services")
            if flags["has_stays"] and request.POST.get("units_present"):
                _save_members(request, collection.stay_units, "units")
            if flags["has_catalog"] and request.POST.get("products_present"):
                _save_members(request, collection.products, "products")
            messages.success(request, _("Collection saved."))
        else:  # photo
            from apps.catalog.images import apply_gallery_op

            tab = "fotos"
            try:
                collection.images = apply_gallery_op(
                    collection.images,
                    op="remove" if request.POST.get("remove") else "add",
                    image_id=request.POST.get("remove") or "",
                    uploaded=request.FILES.get("photo"),
                    folder="collections",
                )
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
            else:
                collection.save(update_fields=["images", "updated_at"])
                messages.success(request, _("Collection saved."))
        return redirect(page_url(collection, tab))

    tabs = tuple(t for t in TABS if t != "fotos" or flags["has_catalog"])
    tab = request.GET.get("tab")
    if tab not in tabs:
        tab = tabs[0]
    groups = []
    if tab == "inhalt":
        from django.apps import apps as django_apps

        spec = (
            (
                "has_booking",
                "booking",
                "Service",
                "services",
                "services",
                _("Services in this collection"),
            ),
            (
                "has_stays",
                "stays",
                "StayUnit",
                "stay_units",
                "units",
                _("Rooms in this collection"),
            ),
            (
                "has_catalog",
                "catalog",
                "Product",
                "products",
                "products",
                _("Products in this collection"),
            ),
        )
        for flag, app, model_name, rel, field, label in spec:
            if not flags[flag]:
                continue
            model = django_apps.get_model(app, model_name)
            members = set(getattr(collection, rel).values_list("pk", flat=True))
            rows = [(obj, obj.pk in members) for obj in _shown_queryset(model)]
            groups.append(
                {
                    "field": field,
                    "label": label,
                    "rows": rows,
                    "hidden": len(members - {o.pk for o, _c in rows}),
                }
            )
    return render(
        request,
        "collections/page.html",
        {
            "nav": "collections",
            "col": collection,
            "tabs": tabs,
            "active_tab": tab,
            "groups": groups,
            "i18n_inputs": i18n_inputs_for(collection, tenant, fields=("name",)),
            "extra_locales": extra_locales(tenant),
            **flags,
        },
    )
