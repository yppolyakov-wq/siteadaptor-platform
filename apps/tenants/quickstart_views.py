"""T-8.5 «Aktion in 3 Klicks»: страница ``/aktion-starten/`` и ожидание провижининга.

План — docs/t8-5-quick-start-plan-2026-10-10.md §1. Клик 1 «Weiter» (акция), клик 2
«Veröffentlichen» (бизнес + e-mail), клик 3 — «Teilen» на экране «Fertig» поддомена.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from apps.core import city_categories, ratelimit
from apps.promotions.quick import MAX_PHOTOS

from . import quickstart
from .models import Tenant
from .services import login_url_for, site_url_for, start_quick_provisioning

SESSION_KEY = "quick_handoff"  # {slug: {"token": ..., "title": ..., "price": ...}}


def _context(request, form):
    from .views import ui_languages

    return {
        "form": form,
        "type_cards": quickstart.type_cards(request),
        "stamp": quickstart.form_stamp(),
        "domain_base": quickstart.domain_base(),
        "known_cities": quickstart.known_cities(),
        "district_options": _district_options(),
        "max_photos": MAX_PHOTOS,
        "category_suggestions": dict(city_categories.BY_BUSINESS_TYPE),
        "ui_languages": ui_languages(),
    }


def _district_options() -> list[dict]:
    from apps.core import districts

    return districts.all_options()


def quick_start(request):
    if request.method == "GET":
        from .views import _capture_partner_ref

        _capture_partner_ref(request)
        form = quickstart.QuickStartForm(initial={"term": "week", "customer_response": "reserve"})
        return render(request, "tenants/quick_start.html", _context(request, form))

    form = quickstart.QuickStartForm(request.POST, request.FILES)
    # Бот: скрытое поле заполнено — форма возвращается как есть, ничего не создаём.
    if (request.POST.get("website") or "").strip():
        return render(request, "tenants/quick_start.html", _context(request, form))
    if not form.is_valid():
        return render(request, "tenants/quick_start.html", _context(request, form))
    if quickstart.too_fast(request.POST.get("stamp", "")):
        form.add_error(None, _("Bitte prüfen Sie Ihre Angaben und senden Sie erneut."))
        return render(request, "tenants/quick_start.html", _context(request, form))
    if ratelimit.hit("quick-start", ratelimit.client_ip(request), limit=5, window=3600):
        form.add_error(None, _("Zu viele Versuche. Bitte später erneut."))
        return render(request, "tenants/quick_start.html", _context(request, form))

    cd = form.cleaned_data
    promo = form.promo_payload()
    uploads = cd.get("photo") or []
    if uploads:
        from apps.promotions.quick import save_photos

        try:
            promo["images"] = save_photos(uploads)
        except ValidationError as exc:
            form.add_error("photo", "; ".join(exc.messages))
            return render(request, "tenants/quick_start.html", _context(request, form))

    try:
        tenant = start_quick_provisioning(
            business_name=cd["business_name"].strip(),
            slug=cd.get("subdomain") or quickstart.suggest_slug(cd["business_name"]),
            business_type=cd["business_type"],
            city=cd["city"],
            district=cd.get("district") or "",
            email=cd["email"],
            promo=promo,
            partner_code=request.session.get("partner_ref", ""),
            in_city_catalog=cd.get("in_city_catalog", False),
        )
    except IntegrityError:
        # Гонка: адрес заняли между проверкой и сохранением — просим выбрать другой.
        _drop_photos(promo)
        form.add_error("subdomain", _("Diese Adresse ist schon vergeben."))
        return render(request, "tenants/quick_start.html", _context(request, form))
    request.session.pop("partner_ref", None)
    from apps.core import owner_login

    handoff = dict(request.session.get(SESSION_KEY) or {})
    handoff[tenant.slug] = {
        "token": owner_login.issue_token(tenant.schema_name, cd["email"]),
        "title": cd["title"],
        "image": (promo.get("images") or [{}])[0].get("url", ""),
    }
    request.session[SESSION_KEY] = handoff
    # Литеральный путь: страницы платформы рендерятся и под tenant-urlconf (тесты).
    return redirect(f"/aktion-starten/{tenant.slug}/")


def _drop_photos(promo: dict) -> None:
    from apps.catalog.images import delete_stored_image

    for ref in promo.get("images") or []:
        delete_stored_image(ref)


def slug_check(request):
    """Живая проверка адреса для формы: {slug, ok, message}.

    ``?slug=`` — что ввёл человек (нормализуется так же, как на сервере при отправке);
    пусто + ``?name=`` — предложить свободный адрес из названия.
    """
    if ratelimit.hit("quick-slug", ratelimit.client_ip(request), limit=120, window=3600):
        return JsonResponse({"slug": "", "ok": False, "message": ""}, status=429)
    raw = (request.GET.get("slug") or "").strip()
    if not raw:
        name = (request.GET.get("name") or "").strip()
        slug = quickstart.suggest_slug(name) if name else ""
        return JsonResponse({"slug": slug, "ok": bool(slug), "message": ""})
    slug = quickstart.normalize_slug(raw)
    problem = quickstart.slug_problem(slug) if slug else str(_("Bitte eine Adresse eingeben."))
    suggestion = ""
    if problem and slug:
        suggestion = quickstart.suggest_slug(slug)
    return JsonResponse(
        {"slug": slug, "ok": not problem, "message": problem, "suggestion": suggestion}
    )


def _target(request, tenant) -> str | None:
    """Куда перейти, когда всё готово; None — ещё ждём."""
    if tenant.provisioning_status != Tenant.PROVISIONING_READY:
        return None
    done = cache.get(f"quick_promo:{tenant.pk}")
    if done is None:
        return None  # схема есть, акция ещё создаётся
    entry = (request.session.get(SESSION_KEY) or {}).get(tenant.slug)
    if not entry:
        return login_url_for(tenant)  # другой браузер — обычный вход
    next_url = f"/promotions/{done}/fertig/" if done != "none" else "/promotions/schnell/"
    return f"{site_url_for(tenant)}/start/{entry['token']}/?{urlencode({'next': next_url})}"


def quick_waiting(request, slug):
    tenant = get_object_or_404(Tenant, slug=slug)
    failed = tenant.provisioning_status == Tenant.PROVISIONING_FAILED
    if not failed:
        target = _target(request, tenant)
        if target:
            return redirect(target)
    entry = (request.session.get(SESSION_KEY) or {}).get(tenant.slug) or {}
    return render(
        request,
        "tenants/quick_waiting.html",
        {"tenant": tenant, "failed": failed, "preview": entry},
    )
