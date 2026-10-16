"""Страница бизнеса + отзывы на порталах (G8 / G8a, config.urls_portal).

`/unternehmen/<slug>/` — хаб бизнеса: контакты + активные листинги + отзывы +
форма (только вошедшему PortalUser, один отзыв на бизнес). Отзывы привязаны к
бизнесу глобально (tenant_schema), показываются на любом портале.
"""

from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
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

    Одна точка истины — `visibility.listable` (приостановка, почта, согласие); демо —
    только на портале с `show_demo` (на `/entdecken/` демо не бывает, зеркало
    `views.py` ленты); городской/вертикальный портал показывает только свой город и
    тип (зеркало `_offer_in_scope` T-8.24). Гейт наследуют все приёмники страницы.
    """
    from .visibility import listable

    tenant = Tenant.objects.filter(slug=slug).exclude(schema_name="public").first()
    if tenant is None or not listable(tenant):
        raise Http404
    portal = getattr(request, "portal", None)
    if tenant.is_demo and not (portal is not None and portal.show_demo):
        raise Http404
    if portal is not None:
        if portal.city and (tenant.city or "").lower() != portal.city.lower():
            raise Http404
        if portal.business_type and tenant.business_type != portal.business_type:
            raise Http404
    return tenant


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
    return render(
        request,
        "aggregator/portal_business.html",
        {
            "portal": portal,
            "follow_target": follow_target,
            "following": follow.is_following(user, follow_target) if follow_target else False,
            "base_template": "aggregator/portal_base.html" if portal else "aggregator/_base.html",
            "business": business,
            "business_jsonld": business_jsonld,
            "listings": AggregatorListing.objects.public()
            .filter(tenant_slug=slug)
            .order_by("-updated_at"),
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
