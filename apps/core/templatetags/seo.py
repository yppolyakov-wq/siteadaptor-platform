"""Шаблонные теги SEO: LocalBusiness JSON-LD в <head> витрины (Track B5)."""

from django import template
from django.utils.safestring import mark_safe

from apps.core.seo import localbusiness_ld

register = template.Library()


def _tenant_rating():
    """(avg, count) рейтинга текущего тенанта из SHARED BusinessRating, или None.

    Ленивая зависимость на aggregator (импорт в теле функции) — core не тянет его
    на уровне модуля (иначе цикл: aggregator → core.seo). SEO не должен ронять
    <head>, поэтому ошибки гасим."""
    try:
        from django.db import connection

        from apps.aggregator.models import BusinessRating

        r = BusinessRating.objects.filter(
            tenant_schema=connection.schema_name, review_count__gt=0
        ).first()
        return (r.avg_rating, r.review_count) if r else None
    except Exception:  # noqa: BLE001 — SEO-обвязка не должна ломать страницу
        return None


def _stays_seo(tenant):
    """(price_range, image) для отеля/пансиона (H6): диапазон цен «ab …€» и фото
    из активных номеров. Только при активном модуле stays; ошибки гасим (SEO не
    должен ронять <head>)."""
    try:
        from apps.core import modules

        if not modules.is_module_active(tenant, "stays"):
            return "", ""
        from apps.stays.models import StayUnit

        units = list(StayUnit.objects.filter(is_active=True, price_cents__gt=0))
        if not units:
            return "", ""
        prices = sorted(u.price_cents for u in units)
        lo, hi = prices[0] // 100, prices[-1] // 100
        price_range = f"ab {lo} €" if lo == hi else f"{lo}–{hi} €"
        image = next((u.image_url for u in units if u.image_url), "")
        return price_range, image
    except Exception:  # noqa: BLE001 — SEO-обвязка не должна ломать страницу
        return "", ""


@register.simple_tag(takes_context=True)
def house_rules_present(context):
    """True, если у активного модуля stays задана Hausordnung (H6) — для ссылки в
    футере. Ошибки гасим (футер не должен ломаться)."""
    try:
        from django.db import connection

        from apps.core import modules
        from apps.stays.models import StaySettings

        request = context.get("request")
        tenant = getattr(request, "tenant", None) if request is not None else None
        if tenant is None or connection.schema_name == "public":
            return False
        if not modules.is_module_active(tenant, "stays"):
            return False
        return bool((StaySettings.load().house_rules or "").strip())
    except Exception:  # noqa: BLE001
        return False


@register.simple_tag
def business_rating():
    """(avg, count) рейтинга текущего тенанта или None — для звёзд на витрине (P3)."""
    return _tenant_rating()


@register.simple_tag
def storefront_reviews(limit=6):
    """Опубликованные отзывы текущего тенанта (G8/#6) для блока на витрине.

    Читаем SHARED BusinessReview напрямую по connection.schema_name (public в
    search_path, как business_rating). Имя автора — дружелюбная производная от
    email (приватность; имени у PortalUser нет). Ошибки гасим — секция витрины
    не должна ронять страницу."""
    try:
        from django.db import connection

        from apps.aggregator.models import BusinessReview

        rows = list(
            BusinessReview.objects.filter(
                tenant_schema=connection.schema_name, status=BusinessReview.STATUS_PUBLISHED
            ).select_related("author")[: max(1, min(int(limit), 24))]
        )
    except Exception:  # noqa: BLE001 — блок отзывов не должен ломать витрину
        return []
    out = []
    for r in rows:
        email = getattr(r.author, "email", "") or ""
        local = email.split("@", 1)[0].replace(".", " ").replace("_", " ").strip()
        name = local.split(" ")[0].capitalize() if local else "Gast"
        out.append(
            {
                "name": name,
                "rating": r.rating,
                "stars": "★" * r.rating + "☆" * (5 - r.rating),
                "comment": r.comment,
                "created_at": r.created_at,
            }
        )
    return out


@register.simple_tag(takes_context=True)
def localbusiness_jsonld(context):
    """Готовый <script type=application/ld+json> с LocalBusiness текущего тенанта.

    Тенант берём из request; вне витрины (нет request/tenant) — пусто. Если у
    бизнеса есть отзывы (G8) — добавляем AggregateRating (звёзды в сниппете).
    """
    request = context.get("request")
    tenant = getattr(request, "tenant", None) if request is not None else None
    if tenant is None:
        return ""
    # H6: для отелей/пансионов добавляем priceRange («ab …€») и фото из номеров.
    price_range, image = _stays_seo(tenant)
    payload = localbusiness_ld(
        tenant,
        url=request.build_absolute_uri("/"),
        aggregate_rating=_tenant_rating(),
        price_range=price_range,
        image=image,
    )
    if not payload:
        return ""
    return mark_safe(f'<script type="application/ld+json">{payload}</script>')
