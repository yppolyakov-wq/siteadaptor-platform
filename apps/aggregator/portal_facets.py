"""FLT-1c: счётчики опций фильтров портала одним запросом.

План — docs/flt-portal-filters-plan-2026-11-04.md §3 и §13.4–13.5.

Пул (`base_qs`) — выдача БЕЗ районов, разделов и признаков: вид/«Neu», запрос и прочие
фильтры уже применены. Каждая опция считается как «что будет, если её отметить»:

* район / раздел / категория — исключают СВОЙ фасет (ИЛИ внутри фасета: отметить второй
  район = добавить его выдачу), но учитывают остальные;
* признак — И: невыбранный признак считает «текущие признаки ∪ {t}», выбранный = итог;
* `total` — точное число найденного (без потолка пагинации).

Один `aggregate()` с условными `Count(filter=…)` по `pk__in` пула: ранжирование и CASE-
аннотации поиска в подзапрос не попадают (`order_by()` + `values("pk")`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db.models import Count, Q

from apps.core import city_categories as cc


@dataclass(frozen=True)
class FacetCounts:
    total: int = 0
    districts: dict[str, int] = field(default_factory=dict)
    sections: dict[str, int] = field(default_factory=dict)
    categories: dict[str, int] = field(default_factory=dict)
    tags: dict[str, int] = field(default_factory=dict)


def _and(*parts: Q) -> Q | None:
    out = Q()
    for part in parts:
        out &= part
    return out if out.children else None


def _kat_q(kats) -> Q:
    keys = sorted({k for kat in kats for k in cc.keys_for_filter(kat)})
    return Q(city_category__in=keys) if keys else Q()


def _tags_q(tags) -> Q:
    q = Q()
    for tag in tags:
        q &= Q(city_tags__contains=[tag])
    return q


def allowed_tags(kats) -> list[str]:
    """Признаки, уместные для выбранных разделов/категорий (союз при нескольких)."""
    if not kats:
        return cc.tags_for("")
    wanted = {t for kat in kats for t in cc.tags_for(kat)}
    return [k for k, _label in cc.TAGS if k in wanted]


def open_sections(kats) -> list[str]:
    """Разделы, чьи категории показываем строками (выбран раздел или его категория)."""
    out = []
    for kat in kats:
        sec = cc.section(kat) or (
            cc.section(cc.category(kat).section) if cc.category(kat) else None
        )
        if sec and sec.key not in out:
            out.append(sec.key)
    return out


def counts(
    base_qs,
    *,
    district_options=(),
    area: tuple[str, ...] = (),
    kats: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
) -> FacetCounts:
    """Счётчики опций по пулу `base_qs` (см. модуль). `district_options` — slug'и районов
    города портала (реестр), для которых нужен счётчик."""
    from .models import AggregatorListing

    area_q = Q(district__in=list(area)) if area else Q()
    kat_q = _kat_q(kats)
    tags_q = _tags_q(tags)
    exprs: dict[str, Count] = {}
    names: dict[str, tuple[str, str]] = {}

    def add(group: str, key: str, cond: Q | None) -> None:
        alias = f"c{len(exprs)}"
        exprs[alias] = Count("pk", filter=cond) if cond is not None else Count("pk")
        names[alias] = (group, key)

    add("total", "", _and(area_q, kat_q, tags_q))
    for slug in district_options:
        add("districts", slug, _and(Q(district=slug), kat_q, tags_q))
    for sec in cc.SECTIONS:
        add("sections", sec.key, _and(_kat_q((sec.key,)), area_q, tags_q))
    for sec_key in open_sections(kats):
        for cat in cc.CATEGORIES:
            if cat.section == sec_key:
                add("categories", cat.key, _and(Q(city_category=cat.key), area_q, tags_q))
    for tag in allowed_tags(kats):
        if tag in tags:
            continue  # выбранный признак = итог (снять его — пилюля ✕)
        add("tags", tag, _and(area_q, kat_q, tags_q, Q(city_tags__contains=[tag])))

    pks = base_qs.order_by().values("pk")
    row = AggregatorListing.objects.filter(pk__in=pks).aggregate(**exprs)
    out: dict[str, dict[str, int]] = {"districts": {}, "sections": {}, "categories": {}, "tags": {}}
    total = 0
    for alias, (group, key) in names.items():
        value = int(row.get(alias) or 0)
        if group == "total":
            total = value
        else:
            out[group][key] = value
    for tag in tags:
        out["tags"][tag] = total
    return FacetCounts(total=total, **out)
