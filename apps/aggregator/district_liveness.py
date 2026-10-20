"""Г5: «живой» район портала и хвост «Auch in der Nähe».

План — docs/g5-district-threshold-plan-2026-10-17.md. Район «живой», если в его выдаче
не меньше N разных бизнесов (`PORTAL_DISTRICT_MIN_BUSINESSES`). Иначе под собственной
выдачей района идёт подписанный хвост из соседних районов: группа на соседа, метка района
на карточке, ссылка «Alle in <Район> anzeigen». С выдачей района ничего не смешивается.

Счёт — по области страницы (отрасль портала + фасет пути), без запроса/раздела: «живость» —
свойство района, а не запроса. Видимость по-прежнему решает `public()` в момент запроса, так
что устаревший на ≤ TTL счётчик никогда не покажет скрытое.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache

from apps.core import districts

from . import portal_scope

log = logging.getLogger(__name__)

#: Не больше стольких непустых соседей в хвосте.
TAIL_NEIGHBORS = 2
#: Карточек в группе соседа и карточек одного бизнеса в группе.
TAIL_PER_NEIGHBOR = 6
TAIL_PER_BUSINESS = 2
#: Сколько строк соседа просматривать, отбирая ≤ 2 на бизнес (граница запроса).
TAIL_SCAN = 48


def min_businesses() -> int:
    return max(0, int(getattr(settings, "PORTAL_DISTRICT_MIN_BUSINESSES", 10) or 0))


def _cache_key(portal) -> str:
    return f"g5:districts:{portal_scope.fingerprint(portal)}"


def _compute(portal) -> dict[tuple[str, str], set[str]]:
    """{(район, отрасль): {схема бизнеса, …}} — ОДИН запрос по пулу портала."""
    rows = (
        portal_scope.pool(portal)
        .exclude(district="")
        .order_by()
        .values_list("district", "business_type", "tenant_schema")
        .distinct()
    )
    out: dict[tuple[str, str], set[str]] = {}
    for district, business_type, schema in rows:
        out.setdefault((district, business_type), set()).add(schema)
    return out


def business_counts(portal) -> dict[tuple[str, str], set[str]]:
    key = _cache_key(portal)
    try:
        cached = cache.get(key)
    except Exception:  # noqa: BLE001 — кэш недоступен: считаем напрямую
        log.warning("g5: district count cache unavailable", exc_info=True)
        return _compute(portal)
    if cached is not None:
        return cached
    data = _compute(portal)
    try:
        cache.set(key, data, getattr(settings, "PORTAL_DISTRICT_COUNT_TTL", 300))
    except Exception:  # noqa: BLE001
        log.warning("g5: district count cache write failed", exc_info=True)
    return data


def count_for(portal, district: str, business_type: str | None = None) -> int:
    """Разных бизнесов района в области (бизнес с листингами двух отраслей — один)."""
    schemas: set[str] = set()
    for (d, bt), found in business_counts(portal).items():
        if d == district and (not business_type or bt == business_type):
            schemas |= found
    return len(schemas)


def is_live(portal, district: str, business_type: str | None = None) -> bool:
    need = min_businesses()
    if not need or not district:
        return True
    return count_for(portal, district, business_type) >= need


def _pick(pool, ranked: bool) -> list:
    """≤ TAIL_PER_NEIGHBOR карточек, ≤ TAIL_PER_BUSINESS на бизнес. Без поиска — суточная
    ротация (честно ко всем, featured не поднимается: UWG §5a); с поиском — ранг движка."""
    if not ranked:
        from .portal_home_blocks import _order

        pool = pool.order_by(*_order("daily_rotation"))
    per_business: dict[str, int] = {}
    out = []
    for item in pool[:TAIL_SCAN]:
        n = per_business.get(item.tenant_schema, 0)
        if n >= TAIL_PER_BUSINESS:
            continue
        per_business[item.tenant_schema] = n + 1
        out.append(item)
        if len(out) >= TAIL_PER_NEIGHBOR:
            break
    return out


def neighbor_tail(
    portal, district: str, *, pool_for, more_url_for, collapse=None, business_type=None
) -> list[dict]:
    """Группы хвоста: [{slug, label, items, more_url}], ≤ TAIL_NEIGHBORS.

    ``pool_for(slug) -> (pool, outcome)`` — та же цепочка выборки, что у страницы соседа
    (поэтому группа ⊆ выдачи по ``more_url``); ``more_url_for(slug)`` — ссылка на соседа с
    той же областью. Сосед без карточек пропускается, берётся следующий по реестру."""
    out: list[dict] = []
    for slug in districts.neighbors(portal.city or "", district):
        if not count_for(portal, slug, business_type):
            continue  # у соседа нет бизнесов в области — без запроса (кэш подсчёта)
        pool, outcome = pool_for(slug)
        items = _pick(pool, outcome.ranked)
        if collapse is not None:
            items = collapse(items)
        if not items:
            continue
        out.append(
            {
                "slug": slug,
                "label": districts.label(portal.city or "", slug),
                "items": items,
                "more_url": more_url_for(slug),
            }
        )
        if len(out) >= TAIL_NEIGHBORS:
            break
    return out
