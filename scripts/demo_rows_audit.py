#!/usr/bin/env python
"""DL-11: аудит демо-китов «ряды плиток полные?» — статикой, без стенда.

Для каждого DemoKit и каждой секции-сетки главной считает число элементов по спеке
кита и колонки (телефон/планшет/десктоп) из GRID_SECTION_DEFAULTS + kit.section_layouts
+ жёстких сеток стилей (categories compact = 1/2/3, promotions spotlight = хвост с
4-й акции). Печатает таблицу; строки с остатком на lg или sm помечены ⚠ — это
ровно то, что на витрине-образце будет обрезано trim'ом (владелец: «делать 4 или 8,
но по типу вывода»). Тот же расчёт — замок test_demo_kits_rows_full.

Запуск: `uv run python scripts/demo_rows_audit.py [--kit aktionsmarkt]`.
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django  # noqa: E402

django.setup()

from apps.tenants import demo_kits, siteconfig  # noqa: E402


def _count_products(kit) -> int:
    n = 0
    for cat in kit.categories:
        items = cat[2] if len(cat) > 2 and isinstance(cat[2], (list, tuple)) else ()
        n += len(items)
    return n


def _active_promos(kit) -> int:
    specs = getattr(kit, "promotions_spec", None) or []
    n = 0
    for s in specs:
        if not isinstance(s, dict):
            continue
        if s.get("status") in ("draft", "scheduled", "ended", "archived", "paused"):
            continue
        if (s.get("starts_in_days") or 0) > 0:
            continue
        n += 1
    return n


def kit_sections(kit) -> dict[str, int]:
    """Секция → число элементов на главной по спеке кита."""
    limits = siteconfig.GRID_SECTION_LIMITS
    top_cats = [c for c in kit.categories if not (isinstance(c, dict) and c.get("parent"))]
    out = {
        "categories": min(len(top_cats), limits["categories"]),
        "products": min(_count_products(kit), limits["products"]),
        "promotions": _active_promos(kit),
        "events": min(len(getattr(kit, "events", None) or []), limits["events"]),
        "tours": min(len(getattr(kit, "tours", None) or []), limits["tours"]),
        "services": len(getattr(kit, "services", None) or []),
        "stay_rooms": len(getattr(kit, "stay_units", None) or []),
        "team": len(getattr(kit, "team", None) or []),
        "testimonials": len(getattr(kit, "testimonials", None) or []),
        "gallery": len(getattr(kit, "gallery_kw", None) or []),
        "blog": min(len(getattr(kit, "blog", None) or []), limits["blog"]),
    }
    return {k: v for k, v in out.items() if v}


def kit_styles_layouts(kit) -> tuple[dict, dict]:
    """Стили и раскладки секций: оси СБОРКИ кита (apply_bundle идёт первым при
    сидинге), поверх — свои поля кита (section_styles/section_layouts)."""
    from apps.tenants import sitetemplates  # noqa: PLC0415

    styles, layouts = {}, {}
    bundle = sitetemplates.get_bundle(getattr(kit, "bundle", "") or "")
    if bundle:
        over = bundle.get("config") or {}  # оси сборки живут под "config"
        styles.update(over.get("section_styles") or {})
        layouts.update(over.get("section_layouts") or {})
    styles.update(getattr(kit, "section_styles", None) or {})
    layouts.update(getattr(kit, "section_layouts", None) or {})
    return styles, layouts


def kit_triplet(kit, key: str) -> tuple[int, int, int]:
    """Колонки секции у кита: раскладка (сборка → кит) или дефолт секции. Стиль
    categories compact держит жёсткую сетку 1/2/3 ТОЛЬКО при нетронутой раскладке
    (зеркало тега layout_is_default)."""
    styles, layouts = kit_styles_layouts(kit)
    default = siteconfig.GRID_SECTION_DEFAULTS.get(key, {"preset": "cols3"})
    lay = siteconfig.normalize_layout(layouts.get(key), default)
    if key == "categories" and styles.get("categories") == "compact":
        if lay == siteconfig.normalize_layout(None, default):
            return (1, 2, 3)
    return siteconfig.grid_cols_triplet(lay)


def audit(kit) -> list[dict]:
    rows = []
    styles, _layouts = kit_styles_layouts(kit)
    for key, n in kit_sections(kit).items():
        m, s, lg = kit_triplet(kit, key)
        count = n
        if key == "promotions" and styles.get("promotions") in ("spotlight", "banner"):
            # spotlight: featured + 2 плитки сбоку, сетка — с 4-й; banner — с 2-й
            count = max(0, n - (3 if styles["promotions"] == "spotlight" else 1))
        rem = {
            "lg": count % lg if count >= lg else 0,
            "sm": count % s if count >= s else 0,
            "m": count % m if count >= m else 0,
        }
        rows.append({"section": key, "n": n, "grid_n": count, "cols": (m, s, lg), "rem": rem})
    return rows


def main() -> int:
    only = None
    if "--kit" in sys.argv:
        only = sys.argv[sys.argv.index("--kit") + 1]
    kits = demo_kits.KITS if hasattr(demo_kits, "KITS") else demo_kits.DEMO_KITS
    bad = 0
    for key, kit in kits.items():
        if only and key != only:
            continue
        print(f"== {key} ({kit.business_type}) bundle={getattr(kit, 'bundle', '') or '-'}")
        for r in audit(kit):
            flag = "⚠" if (r["rem"]["lg"] or r["rem"]["sm"]) else " "
            if flag == "⚠":
                bad += 1
            m, s, lg = r["cols"]
            print(
                f"  {flag} {r['section']:12} n={r['n']:2} grid={r['grid_n']:2} "
                f"cols {m}/{s}/{lg}  rest lg={r['rem']['lg']} sm={r['rem']['sm']} m={r['rem']['m']}"
            )
    print(f"\n⚠ строк с остатком на lg/sm: {bad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
