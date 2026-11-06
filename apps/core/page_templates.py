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
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext_lazy as _

from apps.core import page_settings, ratelimit, setup_assistant, studio_pages

#: Cabinet sections with a "Seitenvorlage" tab (plan §2.2). The types each section
#: shows are filtered by `page_settings.active_types` — a hotel sees "Zimmer", not
#: "Termine". "website" is the single entry for every page type (home, text pages,
#: blog, …); the other two put the tab next to the things the pages show.
SECTIONS = {
    "sortiment": {
        "types": (
            "catalog",
            "category",
            "product",
            "combos",
            "lookbook",
            "wishlist",
            "finder",
            "cart",
            "services",
            "service",
            "stays",
            "stay",
            "events",
            "event",
            "tours",
        ),
        "module": None,
        "url_name": "page-templates-sortiment",
        "nav": "seitenvorlage",
        "title": _("Seitenvorlage"),
        "intro": _(
            "So zeigt Ihre Website Ihr Angebot: Listen, Kategorien und Detailseiten. "
            "Eine Kategorie oder ein Produkt mit eigener Vorlage behält diese."
        ),
    },
    "aktionen": {
        "types": ("promos", "promo_group", "promo"),
        "module": "promotions",
        "url_name": "page-templates-aktionen",
        "nav": "seitenvorlage-aktionen",
        "title": _("Seitenvorlage"),
        "intro": _(
            "So zeigt Ihre Website die Aktionsseite, eine Aktionsgruppe und eine einzelne "
            "Aktion. Ein Aktionstyp oder eine Aktion mit eigener Vorlage behält diese."
        ),
    },
    "website": {
        "types": page_settings.SUPPORTED_TYPES,
        "module": None,
        "url_name": "page-templates-website",
        "nav": "seitenvorlagen",
        "title": _("Seitenvorlagen"),
        "intro": _(
            "Alle Seiten Ihrer Website an einem Ort: Startseite, Textseiten, Blog und "
            "alle Listen. Reihenfolge und Texte der Blöcke ändern Sie in der Studio."
        ),
    },
}


def cabinet_url(type_code: str) -> str:
    """The cabinet screen that owns this page type's settings (`?typ=` selects it).
    A section tab beats the "website" screen; the latter shows every type."""
    for key in ("sortiment", "aktionen", "website"):
        if type_code in SECTIONS[key]["types"]:
            return reverse(SECTIONS[key]["url_name"]) + "?" + urlencode({"typ": type_code})
    return reverse(SECTIONS["website"]["url_name"])


def _first(qs):
    try:
        return qs.first()
    except Exception:  # noqa: BLE001 — no preview beats a broken settings screen
        return None


def _object_path(type_code: str) -> str:
    """Detail types need an object to show; "" when there is none yet."""
    from apps.catalog.models import Category, Product

    if type_code == "category":
        cat = _first(
            Category.objects.filter(is_active=True, products__is_active=True).order_by(
                "sort_order", "pk"
            )
        )
        return reverse("storefront-category", args=[cat.slug]) if cat and cat.slug else ""
    if type_code == "product":
        product = _first(Product.objects.filter(is_active=True).select_related("category"))
        return product.get_absolute_url() if product else ""
    if type_code in ("promo", "promo_group"):
        from apps.promotions.models import Promotion

        qs = Promotion.objects.filter(status="active")
        if type_code == "promo_group":
            promo = _first(qs.exclude(group="").order_by("group"))
            if promo is None:
                return ""
            return reverse("storefront-aktionen") + "?" + urlencode({"gruppe": promo.group})
        promo = _first(qs.order_by("-pk"))
        return reverse("storefront-promotion", args=[promo.pk]) if promo else ""
    if type_code == "service":
        from apps.booking.models import Service

        obj = _first(Service.objects.filter(is_active=True).order_by("pk"))
        return reverse("storefront-service-detail", args=[obj.pk]) if obj else ""
    if type_code == "stay":
        from apps.stays.models import StayUnit

        obj = _first(StayUnit.objects.filter(is_active=True).order_by("pk"))
        return reverse("storefront-unterkunft-unit", args=[obj.pk]) if obj else ""
    if type_code == "event":
        from apps.events.models import Event

        obj = _first(Event.objects.filter(status=Event.STATUS_PUBLISHED).order_by("starts_at"))
        return reverse("storefront-event", args=[obj.pk]) if obj else ""
    if type_code == "blog_post":
        from apps.events.models import BlogPost

        obj = _first(BlogPost.objects.filter(is_published=True).order_by("-pk"))
        return reverse("storefront-blog-post", args=[obj.slug]) if obj and obj.slug else ""
    if type_code == "lookbook":
        from apps.collections.models import Collection

        obj = _first(Collection.objects.filter(is_active=True).exclude(images=[]).order_by("pk"))
        return reverse("storefront-lookbook", args=[obj.slug]) if obj and obj.slug else ""
    return ""


def _preview_path(type_code: str) -> str:
    """Storefront page that shows this type; "" when there is nothing to show yet."""
    page = studio_pages.page_type(type_code)
    if page.object_kind or type_code in ("category", "product", "promo_group", "lookbook"):
        return _object_path(type_code)
    for name in page.url_names:
        try:
            return reverse(name)
        except NoReverseMatch:
            continue
    return _object_path(type_code)


def _with_preview(path: str, tpl: str = "") -> str:
    if not path:
        return ""
    query = {"preview": "1", **({"tpl": tpl} if tpl else {})}
    return path + ("&" if "?" in path else "?") + urlencode(query)


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
    if type_code == "promo":
        from apps.promotions.models import Promotion

        for promo in Promotion.objects.exclude(page_style="").order_by("-pk")[:20]:
            rows.append(
                {
                    "label": str(promo),
                    "value": promo.page_style,
                    "url": reverse("promotions:promotion-edit", args=[promo.pk]),
                }
            )
    return rows


PLAN_LIMIT = 20  # questions per user per window (the AI layer has its own daily budget)
PLAN_WINDOW = 600


def _setup_plan(request):
    """STU-19c: answer of the "Was möchten Sie anlegen?" bar (GET ?frage=)."""
    return setup_plan_for(request, request.GET.get("frage") or "")


def setup_plan_for(request, text: str):
    """The plan for a phrase, checked for this request (rights, package, Mini App).
    AIS A-3a: also the answer of the assistant drawer to "create X"."""
    text = (text or "").strip()
    if not text:
        return None
    if ratelimit.hit("setup-plan", str(request.user.pk), limit=PLAN_LIMIT, window=PLAN_WINDOW):
        return setup_assistant.Plan(note=_("Zu viele Fragen — bitte kurz warten."))
    plan = setup_assistant.build_plan(text, request.tenant, request.user)
    return setup_assistant.for_request(plan, request)


def _render(request, section: str):
    spec = SECTIONS[section]
    tenant = request.tenant
    if spec["module"] and not tenant.is_module_active(spec["module"]):
        raise Http404
    types = page_settings.active_types(tenant, spec["types"])
    url = reverse(spec["url_name"])
    if not types:
        # e.g. a "Nur Aktionen" shop: the menu item exists, its pages do not — say so
        # instead of a 404 behind a visible menu entry
        return render(
            request,
            "tenant/page_templates.html",
            {"nav": spec["nav"], "title": spec["title"], "intro": spec["intro"], "types": []},
        )

    if request.method == "POST":
        code = request.POST.get("setting", "")
        typ = request.POST.get("typ", "")
        # a section writes only the settings it shows (one screen ↔ its own settings)
        own = {s.code for t in types for s in page_settings.cabinet_settings(t)}
        try:
            if code not in own:
                raise page_settings.PageSettingError(code)
            # 19f-1: a grid form also carries its output axis (the "out_mode" field is
            # its sentinel — a form without the block keeps the stored output fields)
            output = (
                page_settings.output_payload(request.POST, "out")
                if "out_mode" in request.POST
                else None
            )
            value = request.POST.get("value", "")
            page_settings.write(tenant, code, value, output=output)
            skipped = []
            if request.POST.get("apply_all") and code in page_settings.APPLY_ALL_LAYOUTS:
                # SE-2d-4: the same grid for the other listing pages of this shop; a list
                # that does not offer this preset (catalog-only price views) is skipped —
                # and named, so the owner knows what did not change
                for other in page_settings.APPLY_ALL_LAYOUTS:
                    if other == code or other not in own:
                        continue
                    try:
                        page_settings.write(tenant, other, value, output=output)
                    except page_settings.PageSettingError:
                        skipped.append(
                            str(studio_pages.page_type(page_settings.APPLY_ALL_TYPES[other]).label)
                        )
            if skipped:
                messages.warning(
                    request,
                    _("Nicht übernommen (diese Ansicht gibt es dort nicht): %(lists)s")
                    % {"lists": ", ".join(skipped)},
                )
        except page_settings.PageSettingError:
            messages.error(request, _("Diese Einstellung kann hier nicht gespeichert werden."))
        else:
            messages.success(request, _("Gespeichert."))
        query = urlencode({"typ": typ}) if typ in types else ""
        return redirect(url + (f"?{query}" if query else ""))

    # the setup helper creates catalog things — it answers on the catalog tab only
    plan = _setup_plan(request) if section == "sortiment" else None
    active = request.GET.get("typ", "")
    if active not in types:
        active = types[0]
    schemas = {ts.code: ts for ts in page_settings.schema(tenant, types)}
    preview_path = _preview_path(active)
    return render(
        request,
        "tenant/page_templates.html",
        {
            "nav": spec["nav"],
            "section": section,
            "title": spec["title"],
            "intro": spec["intro"],
            "types": [schemas[t] for t in types],
            "active": schemas[active],
            "preview_path": preview_path,
            "preview_src": _with_preview(preview_path),
            "studio_url": reverse("site-home")
            + (f"?{urlencode({'page': preview_path})}" if preview_path else ""),
            "overrides": _overrides(active),
            "form_url": url,
            # STU-19g: the helper creates services/rooms/events/offers too — but its
            # answers link back here, so it lives on the Sortiment tab only
            "show_ask": section == "sortiment",
            "plan": plan,
            "frage": (request.GET.get("frage") or "")[: setup_assistant.TEXT_MAX],
        },
    )


@login_required
def page_templates_sortiment(request):
    return _render(request, "sortiment")


@login_required
def page_templates_aktionen(request):
    return _render(request, "aktionen")


@login_required
def page_templates_website(request):
    return _render(request, "website")
