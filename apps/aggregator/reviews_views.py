"""Страница бизнеса + отзывы на порталах (G8 / G8a, config.urls_portal).

`/unternehmen/<slug>/` — хаб бизнеса: контакты + активные листинги + отзывы +
форма (только вошедшему PortalUser, один отзыв на бизнес). Отзывы привязаны к
бизнесу глобально (tenant_schema), показываются на любом портале.
"""

from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import get_language
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core import ratelimit
from apps.core.seo import localbusiness_ld
from apps.tenants.models import Tenant

from . import auth, reviews
from .models import AggregatorListing, BusinessRating, BusinessReview


def _portal_or_404(request):
    portal = getattr(request, "portal", None)
    if portal is None:
        raise Http404
    return portal


def _business_or_404(request, slug):
    """T-8.26 S1: карточка бизнеса подчиняется тем же правилам, что его листинги.

    Одна точка истины — `visibility.listable` (приостановка, почта, согласие); правило
    области = `_offer_in_scope` (T-8.24): настоящий портал без `show_demo` демо не
    показывает, городской/вертикальный портал — только свой город и тип; на главном
    домене (`/entdecken/`, portal=None) ограничений нет, как у его ленты
    (`include_demo=True`). Гейт наследуют все приёмники страницы.
    """
    from .visibility import listable

    tenant = Tenant.objects.filter(slug=slug).exclude(schema_name="public").first()
    if tenant is None or not listable(tenant):
        raise Http404
    from . import portal_scope

    if not portal_scope.contains_tenant(tenant, getattr(request, "portal", None)):
        raise Http404
    return tenant


def _count_business_view(request, business, card) -> None:
    """В5 V5-2: просмотр профиля компании. Страница не кэшируется — счёт внутри вьюхи;
    если сюда придёт `@cache_public_page`, учёт выносится в декоратор СНАРУЖИ кэша
    (как `views.count_offer_view`). Ключ строки = ключ карточки бизнеса."""
    from . import portal_stats

    if not portal_stats.should_count(request):
        return
    channel = portal_stats.channel_for(request)
    if card is not None:
        portal_stats.record(request, action="view", channel=channel, listings=[card])
    else:
        portal_stats.record(
            request,
            action="view",
            channel=channel,
            tenant_schema=business.schema_name,
            kind=AggregatorListing.KIND_BUSINESS,
            ref="business",
            is_demo=bool(business.is_demo),
        )


NARROW_MAX = 30


def _business_listings(request, slug: str):
    """Листинги компании в границах портала (T-8.14: на тематическом — только тема)."""
    from . import portal_scope

    portal = getattr(request, "portal", None)
    base = portal_scope.pool(portal) if portal is not None else AggregatorListing.objects.public()
    return base.filter(tenant_slug=slug)


def _narrow_choices(request, slug: str) -> dict:
    """Разделы/категории и марки, которые есть в выдаче компании (для формы сужения)."""
    from apps.core import city_categories as cc

    from .search import BRAND_MAX

    rows = (
        _business_listings(request, slug)
        .exclude(listing_kind=AggregatorListing.KIND_BUSINESS)
        .order_by()
        .values_list("city_category", "brand")
        .distinct()[:500]
    )
    kats: dict[str, str] = {}
    brands: set[str] = set()
    for key, brand in rows:
        node = cc.category(key) if key else None
        if node is not None:
            kats[key] = str(node.label)
        if brand and len(brand) <= BRAND_MAX:  # длиннее фильтр марки не примет — не предлагаем
            brands.add(brand)
    return {
        "kats": sorted(kats.items(), key=lambda kv: kv[1])[:NARROW_MAX],
        "brands": sorted(brands, key=str.lower)[:NARROW_MAX],
    }


def business_page(request, slug):
    # A8/E-2: страница бизнеса работает и на главном /entdecken (portal=None):
    # там read-only отзывы (портальный логин — только на портальных хостах).
    portal = getattr(request, "portal", None)
    business = _business_or_404(request, slug)
    user = auth.current_portal_user(request) if portal else None
    rating = BusinessRating.objects.filter(tenant_schema=business.schema_name).first()
    # G8: LocalBusiness + AggregateRating в <head> — звёзды бизнеса в сниппете.
    business_jsonld = localbusiness_ld(
        business,
        url=request.build_absolute_uri(),
        aggregate_rating=(rating.avg_rating, rating.review_count)
        if rating and rating.review_count
        else None,
    )
    review_list = list(
        BusinessReview.objects.filter(
            tenant_schema=business.schema_name, status=BusinessReview.STATUS_PUBLISHED
        ).select_related("author")
    )
    from . import follow

    follow_target = follow.business_target(business)  # T-8.7: None у демо/скрытых
    business_card = (
        AggregatorListing.objects.public()
        .filter(tenant_slug=slug, listing_kind=AggregatorListing.KIND_BUSINESS)
        .first()
    )
    _count_business_view(request, business, business_card)
    # T-8.10d (Р-4): «Nur bestimmte Angebote?» — сузить подписку на компанию разделом,
    # маркой или словом. Варианты — только то, что у компании реально есть в каталоге.
    narrow = None
    if follow_target is not None:
        narrow = _narrow_choices(request, slug)
    return render(
        request,
        "aggregator/portal_business.html",
        {
            "portal": portal,
            "follow_target": follow_target,
            "follow_narrow": narrow,
            "following": follow.is_following(user, follow_target) if follow_target else False,
            "base_template": "aggregator/portal_base.html" if portal else "aggregator/_base.html",
            "business": business,
            "business_jsonld": business_jsonld,
            # T-8.26: страница демо-бизнеса — плашка + noindex (на любом хосте)
            "shows_demo": bool(business.is_demo),
            "robots_noindex": bool(business.is_demo),
            # Блок А4: сама компания — не «своё предложение»; её карточка даёт
            # описание и «Zur Website».
            "listings": _business_listings(request, slug)
            .exclude(listing_kind=AggregatorListing.KIND_BUSINESS)
            .order_by("-updated_at"),
            "business_card": business_card,
            "open_status": business.open_status(),
            "opening_hours": business.opening_hours_localized(get_language()),
            "reviews": review_list,
            # G8: «Verifizierter Gast» — у автора есть реальная сделка в бизнесе.
            "verified_emails": reviews.verified_emails(
                business.schema_name, [r.author.email for r in review_list]
            ),
            "rating": rating,
            "review_user": user,
            "my_review": (
                BusinessReview.objects.filter(
                    author=user, tenant_schema=business.schema_name
                ).first()
                if user
                else None
            ),
        },
    )


@require_POST
def submit_review(request, slug):
    _portal_or_404(request)
    user = auth.current_portal_user(request)
    if user is None:
        return redirect("portal-login")
    # MEDIUM-11: отзыв публикуется сразу и двигает агрегатный рейтинг бизнеса (SEO
    # JSON-LD). Отзыв на бизнес можно оставить по slug на ЛЮБОГО (не только там, где
    # была покупка), поэтому дросселируем массовую накрутку/бомбинг по IP. Полная
    # защита (верификация визита/модерация) — отдельным продуктовым решением владельца.
    if ratelimit.hit("biz_review", ratelimit.client_ip(request), limit=10, window=3600):
        return HttpResponse(status=429)
    business = _business_or_404(request, slug)
    try:
        rating = int(request.POST.get("rating", ""))
    except (TypeError, ValueError):
        rating = 0
    if not 1 <= rating <= 5:
        messages.error(request, _("Please choose a rating from 1 to 5 stars."))
        return redirect("portal-business", slug=slug)
    BusinessReview.objects.update_or_create(
        author=user,
        tenant_schema=business.schema_name,
        defaults={
            "tenant_slug": slug,
            "business_name": business.name,
            "rating": rating,
            "comment": request.POST.get("comment", "").strip()[:2000],
            "status": BusinessReview.STATUS_PUBLISHED,
        },
    )
    reviews.recompute_rating(business.schema_name)
    messages.success(request, _("Thank you for your review!"))
    return redirect("portal-business", slug=slug)
