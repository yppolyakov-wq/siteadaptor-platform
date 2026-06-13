"""Страница бизнеса + отзывы на порталах (G8 / G8a, config.urls_portal).

`/unternehmen/<slug>/` — хаб бизнеса: контакты + активные листинги + отзывы +
форма (только вошедшему PortalUser, один отзыв на бизнес). Отзывы привязаны к
бизнесу глобально (tenant_schema), показываются на любом портале.
"""

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core.seo import localbusiness_ld
from apps.tenants.models import Tenant

from . import auth, reviews
from .models import AggregatorListing, BusinessRating, BusinessReview


def _portal_or_404(request):
    portal = getattr(request, "portal", None)
    if portal is None:
        raise Http404
    return portal


def _business_or_404(slug):
    tenant = Tenant.objects.filter(slug=slug, is_active=True).exclude(schema_name="public").first()
    if tenant is None:
        raise Http404
    return tenant


def business_page(request, slug):
    portal = _portal_or_404(request)
    business = _business_or_404(slug)
    user = auth.current_portal_user(request)
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
    return render(
        request,
        "aggregator/portal_business.html",
        {
            "portal": portal,
            "business": business,
            "business_jsonld": business_jsonld,
            "listings": AggregatorListing.objects.filter(tenant_slug=slug, is_active=True).order_by(
                "-updated_at"
            ),
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
    business = _business_or_404(slug)
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
