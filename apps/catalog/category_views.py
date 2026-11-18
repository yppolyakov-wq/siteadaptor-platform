"""FB-32 S5b: один построитель видов категорий «Regale», «Index», «Wegweiser» — для
страницы каталога и для секции «Kategorien» главной (план
`docs/fb32-unified-blocks-plan-2026-11-17.md`, S5b). Каталог и главная зовут одни функции,
поэтому вид на главной — тот же, что в каталоге.
"""

from __future__ import annotations

from django.urls import reverse

SHELF_ITEMS = 8  # товаров в ленте полки (DL-16.5)
HOME_SHELVES = 6  # полок на главной — дальше ведёт «Alle anzeigen» секции


def entries(categories) -> list[dict]:
    """Под-сущности для «Index» (и «Navigator» каталога): метка и ссылка."""
    return [{"label": c, "url": reverse("storefront-category", args=[c.slug])} for c in categories]


def shelves(sources, *, path_mode: bool = False, limit: int | None = None) -> list[dict]:
    """Полки «Regale»: лента ≤ 8 товаров на направление + «Alle anzeigen», если обрезано.

    `path_mode` — полки подкатегорий (свои товары); иначе корневое направление держит товары
    в прямых детях (KAT-1). Подкатегории направлений — одним prefetch (без запроса на полку)."""
    from django.db.models import Prefetch, prefetch_related_objects

    from apps.catalog.models import Category, Product
    from apps.promotions.price_layer import attach_promos

    sources = list(sources)
    if limit is not None:
        sources = sources[:limit]
    if not path_mode and sources:
        prefetch_related_objects(
            sources,
            Prefetch(
                "children",
                queryset=Category.objects.filter(is_active=True).only("pk", "parent_id"),
                to_attr="_shelf_children",
            ),
        )
    all_products = Product.objects.filter(is_active=True)
    out = []
    for sub in sources:
        if path_mode:
            sub_qs = all_products.filter(category=sub)
        else:
            ids = [sub.pk, *(c.pk for c in getattr(sub, "_shelf_children", []))]
            sub_qs = all_products.filter(category_id__in=ids)
        items = list(sub_qs.order_by("-is_featured", "-created_at")[:SHELF_ITEMS])
        if not items:
            continue
        total = sub_qs.count() if len(items) == SHELF_ITEMS else len(items)
        out.append(
            {
                "label": sub,
                "slug": sub.slug,
                "url": reverse("storefront-category", args=[sub.slug]),
                "category": sub,
                "items": items,
                "total": total,
                # «Alle anzeigen» — только когда полка обрезана (фидбэк 2026-09-03)
                "more": total > len(items),
            }
        )
    if out:  # промо-цены всех полок одним проходом слоя цен (SF-4b), а не на каждую полку
        attach_promos([p for sh in out for p in sh["items"]])
    return out


def departments(categories) -> dict:
    """«Wegweiser»: плитки направлений и число колонок (пусто — направлений меньше двух)."""
    from apps.catalog import wegweiser

    deps = wegweiser.departments(categories)
    return {"departments": deps, "cols": wegweiser.columns(len(deps)) if deps else 5}
