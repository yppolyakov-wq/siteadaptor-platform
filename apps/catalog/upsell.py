"""«Passt dazu»: товары-рекомендации к уже выбранному — одна точка истины для корзины
(FB-32 S4) и «Empfehlungen» подтверждения (FB-33 M2h): активные товары, рекомендованные
вперёд, без уже выбранных; с предзагрузкой того, что читает карточка (без N+1).

FB-33 M2h-5 (ревью безопасности): рекомендуется только то, что можно положить в корзину —
активное (как витринные листинги), без «nur auf Anfrage» (как наборы и быстрое «в корзину»;
у корзины-сметы — с ними) и без распроданного."""

from __future__ import annotations

#: запас выборки: распроданные отсеиваются уже после запроса (наличие — по вариантам)
_OVERFETCH = 3


def upsell_products(exclude_ids, limit: int, *, with_requests: bool = False) -> list:
    from apps.promotions.price_layer import attach_promos

    from .models import Product
    from .prefetch import prefetch_cards

    if limit <= 0:
        return []
    qs = Product.objects.filter(is_active=True).exclude(pk__in=[i for i in exclude_ids if i])
    if not with_requests:
        qs = qs.exclude(primary_action="request")
    qs = qs.select_related("category").order_by("-is_featured", "-created_at")
    candidates = prefetch_cards(qs[: limit * _OVERFETCH])
    return attach_promos([p for p in candidates if p.in_stock][:limit])
