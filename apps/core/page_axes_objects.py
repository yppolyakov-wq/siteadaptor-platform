"""FB-31.7 B1b-2b: свои шаблоны ОБЪЕКТОВ → строки своих хостов (план
`docs/fb31-7-materialize-plan-2026-11-16.md`, «B1b-2 план»).

Три единицы, каждая — целиком или никак (сайт — тоже целиком, как B1b-1):

* `categories` — свои коды категорий (`Category.page_style`) закрепляются строками своих хостов
  `catalog:<slug>` (все оси явно), затем «Alle Kategorien» (`site_defaults.category_page_style`)
  → строки хоста `category`. Порядок важен: строки общего шаблона перекрыли бы свой код.
* `promos` — свой шаблон акции (`Promotion.page_style`) → хост `promo:<hex>` (ось «Angebot» явно).
* `promo_groups` — свой шаблон группы (`promo_groups[key].style`) → хост `promo_group:<md5>`
  (все оси явно; новый хост — копия общих блоков, решение владельца D1 — в отчёте `detached`).

Старые коды остаются (решение владельца 4, снимаются в B3). Сверка: оси «как видит посетитель»
до, после и после-без-кодов (`objects_blind` + без ключа «Alle Kategorien») совпадают, затем —
отрисованные страницы (`render_path`). Чистые функции: данные объектов — `ObjectIndex`.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

#: сколько страниц одной единицы сверять рендером (каждая — три отрисовки)
MAX_RENDER_PAGES = 150


@dataclass(frozen=True)
class CategoryRef:
    slug: str
    page_style: str = ""
    parent_slug: str = ""


@dataclass(frozen=True)
class PromoRef:
    hex: str
    page_style: str = ""
    on_sale: bool = True


@dataclass
class ObjectIndex:
    categories: list[CategoryRef] = field(default_factory=list)  # активные
    all_category_slugs: frozenset = frozenset()  # все (для чистки хостов удалённых)
    promos: list[PromoRef] = field(default_factory=list)  # со своим шаблоном
    groups: list[str] = field(default_factory=list)  # живые группы (ключ — как у акции)


@dataclass
class UnitResult:
    status: str = ""
    notes: list[str] = field(default_factory=list)
    pages: list[str] = field(default_factory=list)  # пути для сверки рендером


def build_index() -> ObjectIndex:
    """Объекты текущей схемы — по запросу на вид."""
    from apps.catalog.models import Category
    from apps.promotions.models import Promotion

    cats = list(
        Category.objects.filter(is_active=True)
        .order_by("pk")
        .values_list("slug", "page_style", "parent__slug")
    )
    promos = list(
        Promotion.objects.exclude(page_style="").order_by("pk").values_list("pk", "page_style")
    )
    on_sale = set(
        Promotion.objects.filter(Promotion.on_sale_q())
        .exclude(page_style="")
        .values_list("pk", flat=True)
    )
    groups = sorted(
        set(Promotion.objects.exclude(group="").values_list("group", flat=True).distinct())
    )
    return ObjectIndex(
        categories=[CategoryRef(s, p or "", ps or "") for s, p, ps in cats],
        all_category_slugs=frozenset(Category.objects.values_list("slug", flat=True)),
        promos=[PromoRef(pk.hex, st or "", pk in on_sale) for pk, st in promos],
        groups=groups,
    )


# ───────── общие помощники ─────────


def _blocks(cfg) -> dict:
    b = (cfg or {}).get("page_blocks") if isinstance(cfg, dict) else None
    return b if isinstance(b, dict) else {}


def _set_rows(out: dict, host: str, rows: list) -> dict:
    """Новый хост без своих блоков и переводов — прямо в сырые настройки; у хоста со своими
    блоками переводы едут за ними (`_with_host_rows`)."""
    from apps.core import page_axes_migration as pam
    from apps.tenants import siteconfig

    if host in _blocks(out):
        return pam._with_host_rows(out, siteconfig.normalize(out), host, rows)
    res = copy.deepcopy(out)
    blocks = dict(_blocks(res))
    blocks[host] = rows
    res["page_blocks"] = blocks
    return res


def _hidden_categories_row(rows) -> bool:
    return any(
        isinstance(r, dict)
        and r.get("key") == "categories"
        and not r.get("id")
        and r.get("enabled") is False
        for r in rows or []
    )


def _drop_hosts(out: dict, hosts: set[str]) -> dict:
    res = copy.deepcopy(out)
    res["page_blocks"] = {k: v for k, v in _blocks(res).items() if k not in hosts}
    for layer in (res.get("i18n") or {}).values() if isinstance(res.get("i18n"), dict) else ():
        pb = layer.get("page_blocks") if isinstance(layer, dict) else None
        if isinstance(pb, dict):
            layer["page_blocks"] = {k: v for k, v in pb.items() if k not in hosts}
    return res


# ───────── категории ─────────


def _cat_obj(ref: CategoryRef):
    from types import SimpleNamespace

    return SimpleNamespace(slug=ref.slug, page_style=ref.page_style)


def _cat_view(cfg, ref: CategoryRef):
    from apps.catalog import catalog_parts

    return catalog_parts.category_parts(cfg, _cat_obj(ref))


def migrate_categories(raw: dict, idx: ObjectIndex) -> tuple[dict, UnitResult]:
    from apps.catalog import catalog_parts
    from apps.catalog.category_styles import VALID_PAGE_STYLES
    from apps.core import page_axes_migration as pam
    from apps.tenants import siteconfig

    res = UnitResult()
    src = raw if isinstance(raw, dict) else {}
    norm = siteconfig.normalize(src)
    default = pam._old_code(norm, "category_page_style")
    blocks = _blocks(norm)

    def own_host(ref):
        return siteconfig.category_host(ref.slug)

    pins = [
        ref
        for ref in idx.categories
        if own_host(ref)
        and (
            (ref.page_style in VALID_PAGE_STYLES and ref.page_style)
            or catalog_parts.has_parts(blocks.get(own_host(ref)) or [])
        )
    ]
    if not pins and not default:
        return copy.deepcopy(src), res
    want = {ref.slug: _cat_view(norm, ref) for ref in idx.categories}

    out = copy.deepcopy(src)
    # потолок своих схем: новые хосты + существующие; сначала — хосты удалённых категорий
    new_hosts = {own_host(r) for r in pins} - set(_blocks(out))
    existing = {h for h in _blocks(out) if h.startswith(siteconfig.CATEGORY_HOST_PREFIX)}
    if len(existing) + len(new_hosts) > siteconfig._MAX_CATEGORY_HOSTS:
        ghosts = {
            h
            for h in existing
            if h[len(siteconfig.CATEGORY_HOST_PREFIX) :] not in idx.all_category_slugs
        }
        out = _drop_hosts(out, ghosts)
        res.notes.append(f"purged:{len(ghosts)}")
        if len(existing - ghosts) + len(new_hosts) > siteconfig._MAX_CATEGORY_HOSTS:
            res.status = pam.HOSTS_FULL
            return copy.deepcopy(src), res

    for ref in pins:
        host = own_host(ref)
        rows0 = list(_blocks(norm).get(host) or [])
        if _hidden_categories_row(rows0):
            res.status = pam.SKIP
            return copy.deepcopy(src), res
        rows = catalog_parts.write_rows(rows0, want[ref.slug], root=False)
        if rows0 == rows:
            continue
        out = _set_rows(out, host, rows)
        res.pages.append(ref.slug)
    if default:
        cur = siteconfig.normalize(out)
        rows = pam.template_rows(cur, "category_page_style")
        if rows is None:
            res.status = pam.SKIP
            return copy.deepcopy(src), res
        if "category" not in _blocks(cur):
            res.notes.append("detached:category")
        out = pam._with_host_rows(out, cur, "category", rows)
    if out == src or siteconfig.normalize(out) == norm:
        res.status = pam.SAME  # повтор: строки уже задают этот вид
        return copy.deepcopy(src), res

    after = siteconfig.normalize(out)
    bare = siteconfig.normalize(pam._without_key(out, "category_page_style"))
    for ref in idx.categories:
        with pam.objects_blind():
            blind = _cat_view(bare, ref)
        if _cat_view(after, ref) != want[ref.slug] or blind != want[ref.slug]:
            res.status = pam.MISMATCH
            res.notes.append(f"axes:{ref.slug}")
            return copy.deepcopy(src), res
    # страницы для сверки: закреплённые, их подкатегории (табы родителя), одна без своей схемы
    pinned = {r.slug for r in pins}
    sample = [r.slug for r in pins]
    sample += [r.slug for r in idx.categories if r.parent_slug in pinned and r.slug not in pinned]
    plain = next((r.slug for r in idx.categories if r.slug not in pinned), None)
    if plain:
        sample.append(plain)
    res.pages = list(dict.fromkeys(sample))[:MAX_RENDER_PAGES]
    res.status = pam.DONE
    return out, res


# ───────── акции ─────────


def migrate_promos(raw: dict, idx: ObjectIndex) -> tuple[dict, UnitResult]:
    from apps.core import page_axes_migration as pam
    from apps.core import page_parts as pp
    from apps.promotions import group_styles, promo_parts
    from apps.tenants import siteconfig

    res = UnitResult()
    src = raw if isinstance(raw, dict) else {}
    norm = siteconfig.normalize(src)
    default = pam._old_code(norm, "promo_detail_style")
    refs = [r for r in idx.promos if group_styles.promotion_detail_style(r.page_style, "") != ""]
    if not refs:
        return copy.deepcopy(src), res
    new_hosts = {f"promo:{r.hex}" for r in refs} - set(_blocks(src))
    objects = sum(1 for h in _blocks(src) if siteconfig.is_object_host(h))
    if objects + len(new_hosts) > siteconfig._MAX_OBJECT_HOSTS:
        res.status = pam.HOSTS_FULL
        return copy.deepcopy(src), res
    out = copy.deepcopy(src)
    want = {}
    for r in refs:
        host = f"promo:{r.hex}"
        want[r.hex] = promo_parts.detail_parts(norm, r.page_style, default, host)
        rows0 = list(_blocks(norm).get(host) or [])
        rows = pp.rows_with(promo_parts.PROMO_DETAIL, rows0, want[r.hex], explicit=True)
        if rows is None:
            res.status = pam.SKIP
            return copy.deepcopy(src), res
        if rows != rows0:
            out = _set_rows(out, host, rows)
            if r.on_sale:
                res.pages.append(r.hex)
    if out == src or siteconfig.normalize(out) == norm:
        res.status = pam.SAME  # повтор: строки уже задают этот вид
        return copy.deepcopy(src), res
    after = siteconfig.normalize(out)
    for r in refs:
        host = f"promo:{r.hex}"
        with pam.objects_blind():
            blind = promo_parts.detail_parts(after, r.page_style, default, host)
        if promo_parts.detail_parts(after, r.page_style, default, host) != want[r.hex] or (
            blind != want[r.hex]
        ):
            res.status = pam.MISMATCH
            res.notes.append(f"axes:promo:{r.hex}")
            return copy.deepcopy(src), res
    res.pages = res.pages[:MAX_RENDER_PAGES]
    res.status = pam.DONE
    return out, res


# ───────── группы акций ─────────


def migrate_groups(raw: dict, idx: ObjectIndex) -> tuple[dict, UnitResult]:
    from apps.core import page_axes_migration as pam
    from apps.core import page_parts as pp
    from apps.promotions import group_styles, promo_parts
    from apps.tenants import siteconfig

    res = UnitResult()
    src = raw if isinstance(raw, dict) else {}
    norm = siteconfig.normalize(src)
    per_group = norm.get("promo_groups")
    live = set(idx.groups)
    styled = [
        g
        for g in (siteconfig.normalize_promo_groups(per_group) or {})
        if group_styles.group_style(g, per_group, "")
    ]
    res.notes += [f"orphan:{g}" for g in styled if g not in live]
    keys = [g for g in idx.groups if group_styles.group_style(g, per_group, "")]
    if not keys:
        return copy.deepcopy(src), res
    new_hosts = {siteconfig.promo_group_host(g) for g in keys} - set(_blocks(src))
    have = sum(1 for h in _blocks(src) if siteconfig.is_promo_group_host(h))
    if have + len(new_hosts) > siteconfig._MAX_PROMO_GROUP_HOSTS:
        res.status = pam.HOSTS_FULL
        return copy.deepcopy(src), res
    out = copy.deepcopy(src)
    want = {}
    for g in keys:
        host = siteconfig.promo_group_host(g)
        want[g] = promo_parts.group_parts(norm, g)
        rows0 = siteconfig.page_rows(norm, host)  # нет своих — копия общих (D1)
        rows = pp.rows_with(promo_parts.PROMO_GROUP, rows0, want[g], explicit=True)
        if rows is None:
            res.status = pam.SKIP
            return copy.deepcopy(src), res
        if host not in _blocks(norm):
            res.notes.append(f"detached:{host}")
            # переводы общих блоков — за копией (по позициям, как в «Seitenaufbau»)
            out = pam._with_host_rows(out, siteconfig.normalize(out), host, rows)
            out = _copy_overlays(out, norm, host)
        elif rows != list(_blocks(norm).get(host) or []):
            out = _set_rows(out, host, rows)
        else:
            continue
        res.pages.append(g)
    if out == src or siteconfig.normalize(out) == norm:
        res.status = pam.SAME  # повтор: строки уже задают этот вид
        return copy.deepcopy(src), res
    after = siteconfig.normalize(out)
    for g in keys:
        with pam.objects_blind():
            blind = promo_parts.group_parts(after, g)
        if promo_parts.group_parts(after, g) != want[g] or blind != want[g]:
            res.status = pam.MISMATCH
            res.notes.append(f"axes:group:{g}")
            return copy.deepcopy(src), res
    res.pages = res.pages[:MAX_RENDER_PAGES]
    res.status = pam.DONE
    return out, res


def _copy_overlays(out: dict, norm: dict, host: str) -> dict:
    """Переводы блоков нового хоста группы — от общих блоков, с которых он скопирован
    (`page_rows`): сопоставление по личности блока (id, как `realign_block_overlays`), не по
    позиции — у копии с обзора акций часть строк отфильтрована."""
    from apps.tenants import siteconfig

    source = siteconfig.shared_promo_group_host(norm)
    src_rows = _blocks(norm).get(source) or []
    new_rows = _blocks(siteconfig.normalize(out)).get(host) or []
    index_of = {}
    for i, item in enumerate(src_rows):
        index_of.setdefault(siteconfig._item_identity(item, "title"), i)
    i18n = norm.get("i18n") if isinstance(norm.get("i18n"), dict) else {}
    res = copy.deepcopy(out)
    for loc, layer in i18n.items():
        tr = ((layer or {}).get("page_blocks") or {}).get(source)
        if not isinstance(tr, list) or not tr:
            continue
        moved = []
        for item in new_rows:
            k = index_of.get(siteconfig._item_identity(item, "title"))
            moved.append(copy.deepcopy(tr[k]) if k is not None and k < len(tr) else {})
        while moved and not moved[-1]:
            moved.pop()
        if not moved:
            continue
        raw_i18n = res.setdefault("i18n", {})
        raw_layer = dict(raw_i18n.get(loc) or {})
        pb = dict(raw_layer.get("page_blocks") or {})
        pb[host] = moved
        raw_layer["page_blocks"] = pb
        raw_i18n[loc] = raw_layer
    return res


def page_url(unit: str, key: str) -> str:
    """Адрес страницы объекта для сверки рендером (в схеме тенанта)."""
    import uuid
    from urllib.parse import urlencode

    from django.urls import reverse

    if unit == "categories":
        return reverse("storefront-category", args=[key], urlconf="config.urls_tenant")
    if unit == "promos":
        return reverse(
            "storefront-promotion", args=[uuid.UUID(hex=key)], urlconf="config.urls_tenant"
        )
    base = reverse("storefront-aktionen", urlconf="config.urls_tenant")
    return f"{base}?{urlencode({'gruppe': key})}"


UNITS = (
    ("categories", migrate_categories),
    ("promos", migrate_promos),
    ("promo_groups", migrate_groups),
)
