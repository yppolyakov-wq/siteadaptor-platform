"""T-8.31b: «So sehen Kunden die Aktion» (план docs/t8-31-mein-laden-plan-2026-10-20.md §2).

Две панели — карточка на своей витрине и карточка в каталоге города — из НАСТОЯЩИХ
партиалов (витрины и портала), внутри неактивной обёртки (``inert``): это картинка,
а не вторая витрина. Портал показывает тот листинг, который построил бы синк
(``promotion_listing_defaults``), поэтому mystery/§11/условия совпадают с реальностью
и для черновика. Только чтение; действия — штатные формы (FSM-переход с ``next``).
"""

from __future__ import annotations

import logging
import re

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from .models import Promotion

logger = logging.getLogger(__name__)

_HEX = re.compile(r"#[0-9a-fA-F]{3,8}")
# FSM-переходы, которые страница предлагает (остальное — на полной правке).
_ACTIONS = {"active": ("paused", "ended"), "paused": ("active", "ended")}


def portal_listing(tenant, promo):
    """Несохранённый листинг акции (никогда не ``save()``) или None."""
    from apps.aggregator import tasks
    from apps.aggregator.models import AggregatorListing

    try:
        snap = tasks._snapshot(promo.pk)
        if snap is None:
            return None
        listing = AggregatorListing(
            tenant_schema=tenant.schema_name,
            listing_kind=AggregatorListing.KIND_PROMOTION,
            source_ref=str(promo.pk),
            **tasks.promotion_listing_defaults(tenant, snap, promo.pk),
        )
    except Exception:  # noqa: BLE001 — превью не роняет страницу акции
        logger.warning("promotion_preview: portal listing failed", exc_info=True)
        return None
    listing.featured_until = None  # платное продвижение превью не показывает
    return listing


def _rows(where, tenant, promo) -> list:
    try:
        return where.rows(tenant, promo)
    except Exception:  # noqa: BLE001 — список «где видно» не роняет страницу акции
        logger.warning("promotion_preview: where.rows failed", exc_info=True)
        return []


def _accent(tenant) -> str:
    color = (getattr(tenant, "primary_color", "") or "").strip()
    return color if _HEX.fullmatch(color) else "#4f46e5"


@login_required
def promotion_preview(request, pk):
    from apps.promotions import where
    from apps.promotions.public_views import _attach_lowest_30d

    promo = get_object_or_404(Promotion.objects.select_related("product"), pk=pk)
    _attach_lowest_30d([promo])
    tenant = request.tenant
    listing = portal_listing(tenant, promo)
    return render(
        request,
        "promotions/promotion_preview.html",
        {
            "nav": "promotions",
            "promo": promo,
            "portal_items": [listing] if listing is not None else [],
            "rows": _rows(where, tenant, promo),
            "actions": _ACTIONS.get(promo.status, ()),
            # в style-атрибут — только hex (иначе CSS-инъекция через цвет тенанта)
            "accent": _accent(tenant),
        },
    )
