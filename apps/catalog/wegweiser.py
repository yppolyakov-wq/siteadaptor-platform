"""Wegweiser — корень каталога `/sortiment/` по макету S1 (2026-11-08).

Порядок страницы: направления (плитки с числами) → «Im Fokus» → сетка остальных
товаров. Вьюха `product_list` только зовёт эти функции: подсчёты живут здесь,
чтобы вьюха не росла дальше и чтобы число запросов не зависело от числа
направлений (замок `test_department_queries_do_not_grow_with_departments`).

План — `docs/sortiment-wegweiser-plan-2026-11-08.md`.
"""

from __future__ import annotations

from django.db.models import Count, Prefetch, Q, prefetch_related_objects

#: сколько подкатегорий печатать на плитке направления (остальные — «+N»)
SUBCATEGORY_NAMES = 4
#: Wegweiser имеет смысл, когда есть между чем выбирать
MIN_DEPARTMENTS = 2


def departments(categories) -> list[dict]:
    """Плитки направлений: категория, число товаров поддерева, подкатегории, «neu».

    `categories` — корневые активные категории с товарами (тот же набор, что у
    стандартного списка категорий). Поддерево — на один уровень, как у полок
    (KAT-1: контейнер включает прямых детей). Два запроса на все направления:
    подкатегории одним prefetch и один агрегат по товарам."""
    from .models import Category, Product

    roots = list(categories)
    if len(roots) < MIN_DEPARTMENTS:
        return []
    prefetch_related_objects(
        roots,
        Prefetch(
            "children",
            queryset=Category.objects.filter(is_active=True).order_by("sort_order", "slug"),
            to_attr="ww_children",
        ),
    )
    ids = [i for r in roots for i in (r.pk, *(c.pk for c in r.ww_children))]
    per_cat = {
        row["category_id"]: row
        for row in Product.objects.filter(is_active=True, category_id__in=ids)
        .values("category_id")
        .annotate(n=Count("id"), neu=Count("id", filter=Q(badge="neu")))
    }

    def _n(pk, key="n"):
        row = per_cat.get(pk)
        return row[key] if row else 0

    out = []
    for root in roots:
        # подкатегория без товаров на плитке — пустое обещание
        subs = [c for c in root.ww_children if _n(c.pk)]
        cats = [root.pk, *(c.pk for c in root.ww_children)]
        if not sum(_n(pk) for pk in cats):
            # товары только в НЕАКТИВНОЙ подкатегории: плитка «0» никуда не ведёт
            continue
        out.append(
            {
                "category": root,
                "count": sum(_n(pk) for pk in cats),
                "new": sum(_n(pk, "neu") for pk in cats),
                "subs": subs[:SUBCATEGORY_NAMES],
                "more_subs": max(0, len(subs) - SUBCATEGORY_NAMES),
            }
        )
    return out if len(out) >= MIN_DEPARTMENTS else []


def summary(all_products, departments_count: int, sale_count: int) -> dict:
    """Строка под H1: «N Artikel in M Bereichen · K reduziert · J neu».

    `sale_count` — тот же счётчик, что у фасета «Nur reduzierte» (одна правда с
    фильтром: число в сводке = число за ссылкой)."""
    agg = all_products.aggregate(n=Count("id"), neu=Count("id", filter=Q(badge="neu")))
    return {
        "articles": agg["n"] or 0,
        "departments": departments_count,
        "sale": sale_count or 0,
        "new": agg["neu"] or 0,
    }


#: карточек на вкладку «Im Fokus» (макет S1 — пять в ряд)
FOCUS_ITEMS = 5
#: вкладка с меньшим числом карточек — пустое обещание, её не рисуем
MIN_FOCUS_ITEMS = 3


def focus_panels(all_products, provider, *, sale_ids=None, ids_only=False) -> list[dict]:
    """«Im Fokus»: одна полка с вкладками Neu · Reduziert · Beliebt.

    Каждая вкладка — та же выборка, что за её ссылкой «Alle N →»: Neu и Beliebt —
    бейдж владельца (`?badge=…`), Reduziert — тот же резолвер, что у фасета «Nur
    reduzierte» (`?sale=1`, «показано = продано»). Поэтому число на ссылке всегда
    равно числу за ней. Решение Р-3 плана: «neu» по бейджу, а не по дате создания —
    у демо и импорта даты одинаковые, «neu diese Woche» соврал бы.

    Запросов постоянно: ≤ 3 выборки + ≤ 2 подсчёта (только когда вкладка обрезана).
    `sale_ids` — уже посчитанные pk со скидкой (вьюха считает их один раз: резолвер
    акций дорогой, а второй проход мог бы разойтись с чипом). `ids_only` — для
    курсорных страниц: нужны только pk, чтобы сетка их исключила."""
    from django.utils.translation import gettext_lazy as _

    specs = (
        ("neu", _("Neu"), all_products.filter(badge="neu"), "badge=neu"),
        (
            "sale",
            _("Reduziert"),
            all_products.filter(pk__in=sale_ids)
            if sale_ids is not None
            else provider.apply(all_products, {"sale": "1"}),
            "sale=1",
        ),
        ("beliebt", _("Beliebt"), all_products.filter(badge="beliebt"), "badge=beliebt"),
    )
    panels = []
    for key, label, qs, query in specs:
        ordered = qs.order_by("-is_featured", "-created_at", "-pk")
        if ids_only:
            pks = list(ordered.values_list("pk", flat=True)[: FOCUS_ITEMS + 1])
            if len(pks) >= MIN_FOCUS_ITEMS:
                panels.append({"key": key, "pks": pks[:FOCUS_ITEMS]})
            continue
        items = list(ordered[: FOCUS_ITEMS + 1])
        if len(items) < MIN_FOCUS_ITEMS:
            continue
        more = len(items) > FOCUS_ITEMS
        items = items[:FOCUS_ITEMS]
        panels.append(
            {
                "key": key,
                "label": label,
                "items": items,
                "total": (
                    (len(sale_ids) if key == "sale" and sale_ids is not None else qs.count())
                    if more
                    else len(items)
                ),
                "more": more,
                "query": query,
            }
        )
    return panels


def focus_ids(panels) -> set:
    """pk товаров «Im Fokus» — сетка ниже их не повторяет (дефект прода №2)."""
    return {
        pk
        for panel in panels
        for pk in (panel.get("pks") or [p.pk for p in panel.get("items", [])])
    }


#: подборок-чипов в «Schnell finden» (макет S1 — строка без переноса на десктопе)
GUIDE_COLLECTIONS = 4
#: «круглые» границы цены для чипа «Unter X €»
_NICE_PRICES = (5, 10, 15, 20, 25, 30, 40, 50, 75, 100, 150, 200, 250, 300, 500, 1000)


def _nice_price(value) -> int | None:
    for p in _NICE_PRICES:
        if p >= value:
            return p
    return None


def guides(all_products, provider, chips, *, combos=None, combos_label="") -> list[dict]:
    """«Schnell finden»: короткие входы в выборки со счётчиком.

    Каждый чип ведёт на существующий фасет, поэтому число на нём равно числу за ним
    (замок `test_guides_lead_to_exactly_the_promised_number_of_items`):
    * подборки владельца (`?kollektion=`), где есть товары;
    * «Unter X €» — нижняя треть цен, граница округлена вверх (`?preis_bis=`);
    * наборы (`/kombi/`), если они есть.
    Решение Р-2 плана: авто-набор v1; ручные «гиды» — через подборки."""
    from django.urls import reverse
    from django.utils.translation import gettext as _

    from apps.collections.models import Collection

    out = []
    slugs = [c["slug"] for c in chips.get("collection_chips", [])][:GUIDE_COLLECTIONS]
    if slugs:
        counted = {
            c.slug: c.n
            for c in Collection.objects.filter(slug__in=slugs, is_active=True).annotate(
                n=Count("products", filter=Q(products__is_active=True), distinct=True)
            )
        }
        for c in chips["collection_chips"][:GUIDE_COLLECTIONS]:
            if counted.get(c["slug"]):
                out.append(
                    {
                        "label": c["label"],
                        "count": counted[c["slug"]],
                        "url": f"?kollektion={c['slug']}",
                    }
                )
    lo, hi = chips.get("price_lo"), chips.get("price_hi")
    if chips.get("show_price_filter") and lo is not None and hi is not None and hi > lo:
        limit = _nice_price(float(lo) + (float(hi) - float(lo)) / 3)
        if limit is not None and limit < float(hi):
            n = provider.apply(all_products, {"preis_bis": str(limit)}).count()
            if n:
                out.append(
                    {
                        "label": _("Unter %(price)s €") % {"price": limit},
                        "count": n,
                        "url": f"?preis_bis={limit}",
                    }
                )
    if combos is not None:
        n = combos.count()
        if n:
            out.append({"label": combos_label, "count": n, "url": reverse("storefront-combos")})
    return out if len(out) >= 2 else []
