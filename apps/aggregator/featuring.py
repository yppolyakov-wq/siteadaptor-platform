"""D2.4: generic self-serve featured для листингов агрегатора (stay/event).

Зеркалит флоу P2.4b акций (promotions.views.promotion_feature*): страница
планов + разовый Stripe-Checkout; вебхук `kind=featured` адресует листинг по
(listing_kind, source_ref). Вьюхи-обёртки живут в кабинетах stays/events и
зовут эти два хелпера — логика/шаблон одни.
"""

from django.contrib import messages
from django.db import connection
from django.shortcuts import redirect, render


def _listing(kind: str, source_ref: str):
    from .models import AggregatorListing

    return AggregatorListing.objects.filter(
        tenant_schema=connection.schema_name,
        listing_kind=kind,
        source_ref=str(source_ref),
    ).first()


def render_feature_page(
    request,
    *,
    obj_title: str,
    kind: str,
    source_ref: str,
    listable: bool,
    not_listed_hint: str,
    back_url: str,
    checkout_url: str,
    nav: str,
):
    """Страница продвижения (generic-зеркало promotion_feature)."""
    from apps.billing import featured as billing_featured

    listing = _listing(kind, source_ref)
    return render(
        request,
        "tenant/listing_feature.html",
        {
            "obj_title": obj_title,
            "listing": listing,
            "plans": billing_featured.get_plans(),
            "featured_enabled": billing_featured.is_enabled(),
            "is_listed": listable and listing is not None,
            "not_listed_hint": not_listed_hint,
            "back_url": back_url,
            "checkout_url": checkout_url,
            "checkout_status": request.GET.get("status", ""),
            "nav": nav,
        },
    )


def start_feature_checkout(
    request,
    *,
    kind: str,
    source_ref: str,
    title: str,
    listable: bool,
    not_listable_msg: str,
    sync,
    feature_page_url: str,
):
    """POST days → Stripe-Checkout за продвижение листинга (generic-зеркало).

    sync — callable(tenant_schema, source_ref): гарантирует листинг к моменту
    оплаты (featured_until переживает ресинк). Возвращает redirect.
    """
    from apps.billing import featured as billing_featured
    from apps.billing import services as billing_services

    days_raw = request.POST.get("days", "")
    plan = billing_featured.get_plan(int(days_raw)) if days_raw.isdigit() else None
    if not billing_featured.is_enabled() or plan is None:
        messages.error(request, "Empfehlung ist derzeit nicht verfügbar.")
        return redirect(feature_page_url)
    if not listable:
        messages.error(request, not_listable_msg)
        return redirect(feature_page_url)

    sync(connection.schema_name, str(source_ref))

    base = request.build_absolute_uri(feature_page_url)
    url = billing_services.create_featured_checkout_session(
        request.tenant,
        listing_kind=kind,
        source_ref=str(source_ref),
        days=plan.days,
        title=title,
        success_url=f"{base}?status=success",
        cancel_url=f"{base}?status=cancel",
    )
    return redirect(url)
