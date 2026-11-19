"""FB-31.7 B3a: остаток перед снятием чтения старых кодов шаблонов (`materialize_page_axes
--residue`, план «B3 план» в `docs/fb31-7-materialize-plan-2026-11-16.md`).

Что посетитель увидит, если старые коды перестать читать (B3b), — сравнивается по ОСЯМ всех
поверхностей: оси при чтении кодов == оси без них (ключи уровня сайта сняты из настроек, коды
объектов не видны — `objects_blind`). Рендер страниц выводится из этих осей, поэтому сверка по
осям — та же, что видит посетитель. Плюс то, что сменит вид ПОЗЖЕ: старые конфиги в истории
версий и черновике, откаченный перенос, неактивные/удалённые объекты со своим кодом.

Ноль у всех сайтов — условие B3b.
"""

from __future__ import annotations

import copy
from types import SimpleNamespace

#: старые ключи уровня сайта (для подсчёта в истории/черновике)
SITE_KEYS = ("page_styles", "catalog_page_style", "promo_page_style")
SITE_DEFAULT_KEYS = ("category_page_style", "promo_group_style", "promo_detail_style")


def strip_site_codes(cfg: dict) -> dict:
    """Копия настроек без старых ключей шаблонов уровня сайта (так их увидит B3b)."""
    out = copy.deepcopy(cfg if isinstance(cfg, dict) else {})
    for key in SITE_KEYS:
        out.pop(key, None)
    sd = out.get("site_defaults")
    if isinstance(sd, dict):
        out["site_defaults"] = {k: v for k, v in sd.items() if k not in SITE_DEFAULT_KEYS}
    groups = out.get("promo_groups")
    if isinstance(groups, dict):
        # своя запись типа: строка — только шаблон; словарь — без оси `style`
        kept = {}
        for name, spec in groups.items():
            if isinstance(spec, dict):
                rest = {k: v for k, v in spec.items() if k != "style"}
                if rest:
                    kept[name] = rest
        out["promo_groups"] = kept
    return out


def has_site_codes(cfg) -> bool:
    if not isinstance(cfg, dict):
        return False
    if any(cfg.get(k) for k in SITE_KEYS):
        return True
    sd = cfg.get("site_defaults")
    if isinstance(sd, dict) and any(sd.get(k) for k in SITE_DEFAULT_KEYS):
        return True
    groups = cfg.get("promo_groups")
    return isinstance(groups, dict) and any(
        isinstance(v, str) and v or isinstance(v, dict) and v.get("style") for v in groups.values()
    )


def _views(cfg: dict, idx, promos) -> dict:
    """Все оси, которые видит посетитель: листинги, шаблоны уровня сайта, категории, акции,
    группы. Без БД (объекты — из `idx`)."""
    from apps.catalog import catalog_parts
    from apps.core import listing_parts
    from apps.promotions import promo_parts
    from apps.tenants import siteconfig

    norm = siteconfig.normalize(cfg)
    out = {}
    for surface in sorted(listing_parts.LISTINGS):
        out[f"listing:{surface}"] = listing_parts.effective(norm, surface)
    for key in sorted(siteconfig.PAGE_TEMPLATE_HOSTS):
        out[f"site:{key}"] = siteconfig.page_template_parts(norm, key)
    for ref in idx.categories:
        cat = SimpleNamespace(slug=ref.slug, page_style=ref.page_style)
        out[f"category:{ref.slug}"] = catalog_parts.category_parts(norm, cat)
    default = (norm.get("site_defaults") or {}).get("promo_detail_style", "")
    for hexed, own in promos:
        out[f"promo:{hexed}"] = promo_parts.detail_parts(norm, own, default, f"promo:{hexed}")
    # ревью B3a: и встроенные типы (`sys:*`), и группы со своим шаблоном без живых акций
    styled = siteconfig.normalize_promo_groups(norm.get("promo_groups")) or {}
    for group in sorted({*idx.groups, *styled, *_builtin_keys()}):
        out[f"group:{group}"] = promo_parts.group_parts(norm, group)
    return out


def _builtin_keys() -> tuple[str, ...]:
    from apps.promotions import promo_types

    return tuple(promo_types.builtin_keys())


def view_residue(cfg: dict, idx, promos) -> list[str]:
    """Поверхности, чей вид сменится без старых кодов."""
    from apps.core import page_axes_migration as pam

    before = _views(cfg, idx, promos)
    with pam.objects_blind():
        after = _views(strip_site_codes(cfg), idx, promos)
    return sorted(k for k in before if before[k] != after.get(k))


def tenant_residue(tenant) -> list[str]:
    """Причины, по которым у сайта снятие чтения сменит вид (сейчас или позже)."""
    from django_tenants.utils import schema_context

    from apps.core import page_axes_migration as pam
    from apps.tenants.models import SiteConfigSnapshot

    reasons: list[str] = []
    cfg = tenant.site_config if isinstance(tenant.site_config, dict) else {}
    with schema_context(tenant.schema_name):
        from apps.catalog.models import Category
        from apps.core import page_axes_objects
        from apps.promotions.models import Promotion

        idx = page_axes_objects.build_index()
        promos = list(Promotion.objects.exclude(page_style="").values_list("pk", "page_style"))
        hidden_cats = (
            Category.all_objects.exclude(page_style="").filter(deleted_at__isnull=False).count()
        )
        hidden_promos = (
            Promotion.all_objects.exclude(page_style="").filter(deleted_at__isnull=False).count()
        )
    reasons += [f"view:{k}" for k in view_residue(cfg, idx, [(pk.hex, st) for pk, st in promos])]
    reasons += [f"inactive_category:{slug}" for slug in idx.inactive_coded]
    if hidden_cats:
        reasons.append(f"trashed_categories:{hidden_cats}")
    if hidden_promos:
        reasons.append(f"trashed_promos:{hidden_promos}")
    pairs = [(pk.hex, st) for pk, st in promos]
    history = cfg.get("history") if isinstance(cfg.get("history"), list) else []
    # версия/черновик со старыми кодами без строк: откат или публикация после B3b сменит вид
    old = [
        i
        for i, h in enumerate(history)
        if isinstance(h, dict)
        and isinstance(h.get("config"), dict)
        and has_site_codes(h["config"])
        and view_residue(h["config"], idx, pairs)
    ]
    if old:
        reasons.append(f"history:{len(old)}")
    draft = cfg.get("_draft")
    if isinstance(draft, dict) and has_site_codes(draft) and view_residue(draft, idx, pairs):
        reasons.append("draft")
    last = (
        SiteConfigSnapshot.objects.filter(tenant_id=tenant.pk, reason=pam.REASON)
        .order_by("-created_at", "-id")
        .first()
    )
    if last is not None and last.undone_at is not None:
        reasons.append("rolled_back")  # последний перенос откачен (повтор — уже не остаток)
    return reasons
