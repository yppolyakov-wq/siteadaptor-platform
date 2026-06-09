"""Материализация AggregatorListing из акций (кросс-схемно, идемпотентно).

Агрегатор — SHARED (public). Акции — в TENANT-схемах. Задача читает акцию в её
schema_context, снимает плоский снимок карточки, затем upsert/удаляет листинг в
public. Дёргается хуком PromotionSM на переходах (active → upsert; ended/paused/
archived → remove). Резистентна к отсутствию акции/тенанта (просто удаляет листинг).
"""

from django.conf import settings
from django_tenants.utils import schema_context

from apps.core.jobs import idempotent_task


def _scheme() -> str:
    return "http" if getattr(settings, "DEBUG", False) else "https"


def _snapshot(promotion_id):
    """Снимок карточки акции в ТЕКУЩЕЙ (tenant) схеме → dict или None."""
    from apps.promotions.models import Promotion

    promo = Promotion.objects.filter(id=promotion_id).first()
    if promo is None:
        return None
    return {
        "status": promo.status,
        "title": promo.title or {},
        "teaser": promo.description or {},
        "image": promo.primary_image or {},
        "currency": promo.currency,
        "old_price": promo.old_price,
        "new_price": promo.new_price,
        "discount_percent": promo.discount_percent_display,
        "starts_at": promo.starts_at,
        "ends_at": promo.ends_at,
    }


def sync_listing(tenant_schema, promotion_id) -> str:
    """Чистая логика (вызывается из задачи и тестов): upsert/remove листинга."""
    from apps.tenants.models import Tenant

    from .models import AggregatorListing

    with schema_context(tenant_schema):
        snap = _snapshot(promotion_id)

    tenant = Tenant.objects.filter(schema_name=tenant_schema).first()
    key = {"tenant_schema": tenant_schema, "promo_uuid": promotion_id}

    # Нет акции/тенанта или акция неактивна → листинга в агрегаторе быть не должно.
    if snap is None or tenant is None or snap["status"] != "active":
        AggregatorListing.objects.filter(**key).delete()
        return "removed"

    base = getattr(settings, "TENANT_DOMAIN_BASE", "siteadaptor.de")
    AggregatorListing.objects.update_or_create(
        **key,
        defaults={
            "tenant_slug": tenant.slug,
            "business_name": tenant.name,
            "business_type": tenant.business_type,
            "city": tenant.city,
            "title": snap["title"],
            "teaser": snap["teaser"],
            "image": snap["image"],
            "currency": snap["currency"],
            "old_price": snap["old_price"],
            "new_price": snap["new_price"],
            "discount_percent": snap["discount_percent"],
            "starts_at": snap["starts_at"],
            "ends_at": snap["ends_at"],
            "detail_url": f"{_scheme()}://{tenant.slug}.{base}/p/{promotion_id}/",
            "is_active": True,
        },
    )
    return "upserted"


@idempotent_task()
def sync_aggregator_listing(*, tenant_schema, promotion_id):
    """Beat/hook: материализовать листинг акции в агрегаторе."""
    return {"result": sync_listing(tenant_schema, promotion_id)}
