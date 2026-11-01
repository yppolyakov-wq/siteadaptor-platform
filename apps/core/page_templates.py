"""STU-19b: cabinet tab "Seitenvorlage" — page settings of a section's page types.

Plan: docs/stu19-page-templates-cabinet-ai-plan-2026-11-01.md §2.3. First section:
Sortiment (catalog / category / product). Reading and writing go through
`page_settings` only — one writer per setting; this view has no logic of its own
about allowed values. The preview iframe uses the stateless `?preview=1&tpl=` override
(nothing is stored until "Speichern").
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.core import page_settings, ratelimit, setup_assistant

SECTIONS = {
    "sortiment": {
        "types": ("catalog", "category", "product"),
        "module": "catalog",
        "url_name": "page-templates-sortiment",
    },
}


def _preview_path(type_code: str) -> str:
    """Storefront page that shows this type; "" when there is nothing to show yet."""
    from apps.catalog.models import Category, Product

    if type_code == "catalog":
        return reverse("storefront-products")
    if type_code == "category":
        cat = (
            Category.objects.filter(is_active=True, products__is_active=True)
            .order_by("sort_order", "pk")
            .first()
        )
        return reverse("storefront-category", args=[cat.slug]) if cat and cat.slug else ""
    if type_code == "product":
        product = Product.objects.filter(is_active=True).select_related("category").first()
        return product.get_absolute_url() if product else ""
    return ""


def _overrides(type_code: str) -> list[dict]:
    """Objects with their own value — shown so the owner knows why a page differs."""
    from apps.catalog.models import Category, Product

    rows = []
    if type_code == "category":
        for cat in (
            Category.objects.exclude(page_style="")
            .select_related("parent")
            .order_by("sort_order", "pk")[:20]
        ):
            rows.append(
                {
                    "label": str(cat),
                    "value": cat.page_style,
                    "url": reverse("catalog:category-edit", args=[cat.pk]),
                }
            )
    if type_code in ("category", "product"):
        for prod in (
            Product.objects.exclude(card_style="").select_related("category").order_by("pk")[:20]
        ):
            rows.append(
                {
                    "label": str(prod),
                    "value": prod.card_style,
                    "url": reverse("catalog:product-edit", args=[prod.pk]),
                }
            )
    return rows


PLAN_LIMIT = 20  # questions per user per window (the AI layer has its own daily budget)
PLAN_WINDOW = 600


def _setup_plan(request):
    """STU-19c: answer of the "Was möchten Sie anlegen?" bar (GET ?frage=)."""
    text = (request.GET.get("frage") or "").strip()
    if not text:
        return None
    if ratelimit.hit("setup-plan", str(request.user.pk), limit=PLAN_LIMIT, window=PLAN_WINDOW):
        return setup_assistant.Plan(note=_("Zu viele Fragen — bitte kurz warten."))
    return setup_assistant.build_plan(text, request.tenant, request.user)


def _render(request, section: str):
    spec = SECTIONS[section]
    tenant = request.tenant
    if not tenant.is_module_active(spec["module"]):
        raise Http404
    types = spec["types"]

    if request.method == "POST":
        code = request.POST.get("setting", "")
        typ = request.POST.get("typ", "")
        try:
            page_settings.write(tenant, code, request.POST.get("value", ""))
        except page_settings.PageSettingError:
            messages.error(request, _("Diese Einstellung kann hier nicht gespeichert werden."))
        else:
            messages.success(request, _("Gespeichert."))
        query = urlencode({"typ": typ}) if typ in types else ""
        return redirect(reverse(spec["url_name"]) + (f"?{query}" if query else ""))

    plan = _setup_plan(request)
    active = request.GET.get("typ", "")
    if active not in types:
        active = types[0]
    schemas = {ts.code: ts for ts in page_settings.schema(tenant, types)}
    preview_path = _preview_path(active)
    return render(
        request,
        "tenant/page_templates.html",
        {
            "nav": "seitenvorlage",
            "section": section,
            "types": [schemas[t] for t in types],
            "active": schemas[active],
            "preview_path": preview_path,
            "studio_url": reverse("site-home")
            + (f"?{urlencode({'page': preview_path})}" if preview_path else ""),
            "overrides": _overrides(active),
            "form_url": reverse(spec["url_name"]),
            "plan": plan,
            "frage": (request.GET.get("frage") or "")[: setup_assistant.TEXT_MAX],
        },
    )


@login_required
def page_templates_sortiment(request):
    return _render(request, "sortiment")
