"""FB-30.16 / FB-31: шаблон страницы каталога → блоки страницы.

Решение владельца (2026-11-15): настройки привязаны к ТИПАМ блоков (баннер, категории, товары,
сеты), а не к шаблону страницы. Прежний код шаблона (`catalog_page_style`,
`category_page_style`) — это готовый набор блоков. Модуль чистый (без БД и запросов):

* `from_code(code)` — набор частей прежнего шаблона;
* `legacy_code(parts)` — обратно в код (витрина и CSS ключуются кодом `data-cat-layout`, поэтому
  разметка остаётся байт-в-байт);
* `rows_for(parts)` / `from_rows(rows)` — те же части строками схемы страницы (как блоки
  главной: `categories`, `combos`, маркер ★ `main` с полями вида);
* `effective(cfg, host, code=…)` — сохранённые строки страницы сильнее кода; нет строк — вывод
  из кода (старые конфиги читаются на лету, миграции нет).

Карта кодов — `docs/fb30-16-catalog-parts-plan-2026-11-15.md` §1.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from apps.tenants.siteconfig import CATALOG_CATEGORY_VIEWS as CATEGORY_VIEWS

#: «Darstellung» блока товаров (★), которую раньше задавал шаблон.
PRODUCT_VIEWS = ("schaufenster", "magazin", "mosaik", "preisliste")
HEAD_VIEWS = ("titelbild",)
SETS_PLACES = ("below", "above")


@dataclass(frozen=True)
class Parts:
    head: str = ""  # "" — без шапки страницы, "titelbild" — фото и описание
    categories: str = ""  # "" — как обычно (плитки/чипы), иначе CATEGORY_VIEWS
    sets: str = "below"  # сеты под товарами или над ними
    products: str = ""  # "" — сетка, иначе PRODUCT_VIEWS
    grid: str = ""  # подсказка плотности LAY-5 (действует, только если сетку не трогали)
    focus: bool = False  # полка «Im Fokus» (Wegweiser)


STANDARD = Parts()

#: Прежний код → части. Шапку «фото и описание» несли четыре кода (kopfbild, sets,
#: schaufenster, magazin — общий флаг шапки, план §1).
_FROM_CODE: dict[str, Parts] = {
    "": STANDARD,
    "kopfbild": Parts(head="titelbild"),
    "sets": Parts(head="titelbild", sets="above"),
    "schaufenster": Parts(head="titelbild", products="schaufenster"),
    "magazin": Parts(head="titelbild", products="magazin", grid="cols2"),
    "regale": Parts(categories="regale"),
    "tabs": Parts(categories="tabs"),
    "navigator": Parts(categories="side"),
    "kompakt": Parts(categories="index", grid="cols6"),
    "wegweiser": Parts(categories="wegweiser", focus=True),
    "mosaik": Parts(products="mosaik", grid="cols4"),
    "preisliste": Parts(products="preisliste", grid="preisliste"),
}
_TO_CODE = {parts: code for code, parts in _FROM_CODE.items()}


def from_code(code) -> Parts:
    """Части прежнего шаблона; неизвестный код — обычный вид (как `compositions.resolve`)."""
    return _FROM_CODE.get(code if isinstance(code, str) else "", STANDARD)


def legacy_code(parts: Parts) -> str:
    """Код шаблона для набора частей. Сочетание, которого прежде не было, — ближайший код
    по главной оси (товары → категории → шапка/сеты), чтобы CSS-каскад нашёл правило."""
    if parts in _TO_CODE:
        return _TO_CODE[parts]
    for probe in (
        Parts(products=parts.products, grid=_FROM_CODE.get(parts.products, STANDARD).grid),
        from_code(_code_of_category(parts.categories)),
    ):
        if probe != STANDARD and probe in _TO_CODE:
            return _TO_CODE[probe]
    if parts.sets == "above":
        return "sets"
    return "kopfbild" if parts.head else ""


def _code_of_category(view: str) -> str:
    return {"side": "navigator", "index": "kompakt"}.get(view, view)


def rows_for(parts: Parts) -> list[dict]:
    """Части строками схемы страницы в порядке витрины: шапка → категории → (сеты над) →
    ★ товары → (сеты под). Шапка — блок «Banner» с источником «фото страницы»."""
    rows: list[dict] = []
    if parts.head:
        rows.append({"key": "banner", "id": "catalog-head", "data": {"source": "page"}})
    rows.append({"key": "categories", **({"style": parts.categories} if parts.categories else {})})
    if parts.sets == "above":
        rows.append({"key": "combos"})
    marker = {"key": "main"}
    if parts.products:
        marker["style"] = parts.products
    if parts.focus:
        marker["focus"] = True
    if parts.grid:
        marker["grid"] = parts.grid
    rows.append(marker)
    if parts.sets == "below":
        rows.append({"key": "combos"})
    return rows


def from_rows(rows) -> Parts:
    """Части из строк схемы страницы (мусор отбрасывается)."""
    from apps.tenants.siteconfig import MAIN_MARKER_GRIDS

    rows = [r for r in (rows if isinstance(rows, list) else []) if isinstance(r, dict)]
    parts = STANDARD
    # маркер ★ не хранится, когда он первым, — тогда всё стоит под списком
    seen_main = not any(r.get("key") == "main" for r in rows)
    for row in rows:
        if row.get("enabled") is False and row.get("key") != "main":
            continue  # скрытая строка вида не задаёт
        key = row.get("key")
        if key == "banner" and row.get("id") == "catalog-head":
            parts = replace(parts, head="titelbild")
        elif key == "categories" and row.get("style") in CATEGORY_VIEWS:
            parts = replace(parts, categories=row["style"])
        elif key == "combos":
            parts = replace(parts, sets="below" if seen_main else "above")
        elif key == "main":
            seen_main = True
            parts = replace(
                parts,
                products=row.get("style") if row.get("style") in PRODUCT_VIEWS else "",
                grid=row.get("grid") if row.get("grid") in MAIN_MARKER_GRIDS else "",
                focus=row.get("focus") is True,
            )
    return parts


def has_parts(rows) -> bool:
    """Записаны ли части явно: вид «Kategorien» или поля вида у ★. Голая строка «Kategorien»
    вида не задаёт — тогда действует прежний код (ревью P0/R1)."""
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        if row.get("key") == "categories" and row.get("style") in CATEGORY_VIEWS:
            return True
        if row.get("key") == "main" and len(row) > 1:
            return True
    return False


def effective(cfg, host: str, *, code: str = "") -> Parts:
    """Части страницы: прежний код, поверх — оси, заданные сохранёнными строками хоста
    (вид «Kategorien» — строкой, вид товаров/сетка/«Im Fokus» — полями ★). Остальные оси
    (шапка, сеты) остаются из кода — его по-прежнему пишут Студия и готовые дизайны."""
    base = from_code(code)
    rows = ((cfg or {}).get("page_blocks") or {}).get(host) or []
    if not has_parts(rows):
        return base
    stored = from_rows(rows)
    marker = next(
        (r for r in rows if isinstance(r, dict) and r.get("key") == "main" and len(r) > 1), None
    )
    parts = base
    if stored.categories:
        parts = replace(parts, categories=stored.categories)
    if marker is not None:
        if "style" in marker or "grid" in marker:
            parts = replace(parts, products=stored.products, grid=stored.grid)
        if "focus" in marker:
            parts = replace(parts, focus=stored.focus)
    return parts
