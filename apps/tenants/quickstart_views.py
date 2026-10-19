"""T-8.5 «Aktion in 3 Klicks»: страница ``/aktion-starten/`` и ожидание провижининга.

План — docs/t8-5-quick-start-plan-2026-10-10.md §1. Клик 1 «Weiter» (акция), клик 2
«Veröffentlichen» (бизнес + e-mail), клик 3 — «Teilen» на экране «Fertig» поддомена.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from urllib.parse import urlencode

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core import city_categories, ratelimit
from apps.core.archetypes import FOOD_BUSINESS_TYPES
from apps.promotions.quick import MAX_PHOTOS

from . import quickstart
from .models import Tenant
from .services import login_url_for, site_url_for, start_quick_provisioning

logger = logging.getLogger(__name__)

# Ожидание: схема готова, а ключ акции пропал — через READY_GRACE ведём в список
# акций; PENDING дольше STALE_AFTER — задача потеряна, круг не крутим вечно.
READY_GRACE = timedelta(minutes=3)
STALE_AFTER = timedelta(minutes=15)
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
        # ИИ — только после регистрации (расход считается на бизнес и его дневной
        # лимит; анонимная страница бюджет не тратит) — здесь лишь честная подсказка.
        "ai_after_signup": _ai_enabled(),
        # T-8.5e: проверка текста без входа (свой эндпоинт публичного хоста; ИИ-кнопки нет).
        "text_check_url": "/aktion-starten/pruefen/",
        "food_types": sorted(FOOD_BUSINESS_TYPES),
    }


def _ai_enabled() -> bool:
    from apps.ai.api import is_enabled

    return is_enabled()


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
            address=form.address_line(),
            phone=cd["phone"],
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
        # Схема есть, акция ещё создаётся. Ключ мог и потеряться (истёк, рестарт
        # Redis, задача зависла на письме) — тогда не ждать вечно: через несколько
        # минут ведём в список акций, там всё уже видно.
        if timezone.now() - tenant.created_at < READY_GRACE:
            return None
        done = "list"
    entry = (request.session.get(SESSION_KEY) or {}).get(tenant.slug)
    if not entry:
        return login_url_for(tenant)  # другой браузер — обычный вход
    if done == "list":
        next_url = "/promotions/"
    elif done == "none":
        next_url = "/promotions/schnell/"
    else:
        next_url = f"/promotions/{done}/fertig/"
    return f"{site_url_for(tenant)}/start/{entry['token']}/?{urlencode({'next': next_url})}"


def quick_waiting(request, slug):
    """Ожидание провижининга. Страница опрашивает статус fetch'ем (``?poll=1``) —
    без видимой перезагрузки; meta refresh только как запасной путь без JS.
    Висящее «PENDING» дольше STALE_AFTER — честное сообщение вместо вечного круга."""
    tenant = get_object_or_404(Tenant, slug=slug)
    failed = tenant.provisioning_status == Tenant.PROVISIONING_FAILED
    stale = (
        tenant.provisioning_status == Tenant.PROVISIONING_PENDING
        and timezone.now() - tenant.created_at > STALE_AFTER
    )
    target = None if failed or stale else _target(request, tenant)
    if request.GET.get("poll"):
        return JsonResponse({"redirect": target or "", "stop": failed or stale})
    if target:
        return redirect(target)
    entry = (request.session.get(SESSION_KEY) or {}).get(tenant.slug) or {}
    return render(
        request,
        "tenants/quick_waiting.html",
        {"tenant": tenant, "failed": failed, "stale": stale, "preview": entry},
    )


# T-8.5e E3: «Vor dem Veröffentlichen prüfen» без входа — только правила (без ИИ и без БД
# каталога). Поля — белым списком: товар не принимается (на публичной схеме каталога нет,
# а ответ стал бы оракулом существования товаров).
TEXT_CHECK_FIELDS = (
    "title",
    "description",
    "new_price",
    "old_price",
    "percent",
    "quantity",
    "term",
    "until",
    "perishable",
)
TEXT_CHECK_LIMIT = 30  # запросов с одного IP за окно
TEXT_CHECK_WINDOW = 600


@require_POST
def quick_text_check(request):
    from types import SimpleNamespace

    from django.http import HttpResponse
    from django.template.loader import render_to_string

    from apps.promotions import text_check as ptc

    if ratelimit.hit(
        "quick-text-check",
        ratelimit.client_ip(request),
        limit=TEXT_CHECK_LIMIT,
        window=TEXT_CHECK_WINDOW,
    ):
        return HttpResponse(status=429)
    data = {k: request.POST.get(k, "") for k in TEXT_CHECK_FIELDS}
    btype = request.POST.get("business_type", "")
    tenant = SimpleNamespace(
        business_type=btype if btype in quickstart.QUICK_TYPES else "",
        opening_hours_structured=None,
        opening_hours="",
    )
    try:
        promo = ptc.promotion_from_payload(data, tenant)
        findings = ptc.for_promotion(promo, tenant)
    except Exception:  # noqa: BLE001 — подсказки не стоят 500: клиент оставит прежние
        logger.exception("quick text check failed")
        return HttpResponse(status=503)
    html = render_to_string(
        "promotions/_text_check_results.html",
        {"text_findings": findings, "text_checked": True},
    )
    response = HttpResponse(html)
    response["Cache-Control"] = "no-store"
    return response
