"""T-8.5 «Aktion in 3 Klicks»: страница ``/aktion-starten/`` и ожидание провижининга.

План — docs/t8-5-quick-start-plan-2026-10-10.md §1. Клик 1 «Weiter» (акция), клик 2
«Veröffentlichen» (бизнес + e-mail), клик 3 — «Teilen» на экране «Fertig» поддомена.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from apps.core import ratelimit

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
        "ui_languages": ui_languages(),
    }


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
    upload = cd.get("photo")
    if upload:
        from apps.catalog.images import save_product_image

        try:
            promo["images"] = [save_product_image(upload, is_primary=True, folder="promotions")]
        except ValidationError as exc:
            form.add_error("photo", "; ".join(exc.messages))
            return render(request, "tenants/quick_start.html", _context(request, form))

    tenant = start_quick_provisioning(
        business_name=cd["business_name"].strip(),
        slug=quickstart.suggest_slug(cd["business_name"]),
        business_type=cd["business_type"],
        city=quickstart.DEFAULT_CITY,
        district=cd.get("district") or "",
        email=cd["email"],
        promo=promo,
        partner_code=request.session.pop("partner_ref", ""),
    )
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
