"""«Passt dazu»: товары-рекомендации к уже выбранному — одна точка истины для корзины
(FB-32 S4) и «Empfehlungen» подтверждения (FB-33 M2h): активные товары, рекомендованные
вперёд, без уже выбранных; с предзагрузкой того, что читает карточка (без N+1)."""

from __future__ import annotations


def upsell_products(exclude_ids, limit: int) -> list:
    from apps.promotions.price_layer import attach_promos

    from .models import Product
    from .prefetch import prefetch_cards

    qs = (
        Product.objects.filter(is_active=True)
        .exclude(pk__in=[i for i in exclude_ids if i])
        .select_related("category")
        .order_by("-is_featured", "-created_at")[:limit]
    )
    return prefetch_cards(attach_promos(qs))
