"""FB-31 P4: девять страниц-списков, «Team» и «Galerie» — оси блоков вместо кода шаблона
(ядро `apps/core/page_parts.py`; план `docs/fb31-p4-listings-plan-2026-11-16.md`).

У девяти листингов одинаковые оси: шапка `page_head` («Banner · Fotos der Seite») и строка
навигации `groups` (подборки, темы, разделы — над ★). Таблица кодов одна на все девять: код
навигации гасится данными (`compositions.resolve`, нет подразделов — обычная сетка), поэтому
листингу без подразделов строку навигации не предлагают (`NAV_SURFACES`). Вид ★ листинга —
прежняя сетка `*_layout` и форма карточки «Design» (P2), своих полей у ★ нет.

У «Team» и «Galerie» строк осей нет, у ★ — вид (`style`), как у секции главной: «nur hier»
поверх вида секции главной (R8).
"""

from __future__ import annotations

from apps.core import compositions
from apps.core import page_parts as pp

HEAD_KEY = "page_head"
GROUPS_KEY = "groups"
HEAD_OFF = "aus"
GROUPS_AUTO = "auto"
RASTER = "raster"
#: ★ туров: «Nach Ländern» (как раньше) / «Ohne Abschnitte»
FLAT = "ohne"
GROUPED = "auto"

#: листинги, у которых есть подразделы (подборки услуг и номеров, темы событий, разделы сетов)
NAV_SURFACES = frozenset({"services", "stays", "events", "combos"})
#: поверхность → хост блоков (у номеров хост исторически `stay_rooms`)
HOST_OF = {s: ("stay_rooms" if s == "stays" else s) for s in compositions.LISTING_SURFACES}
SURFACE_OF_HOST = {h: s for s, h in HOST_OF.items()}

_CODES = {
    "": {},
    "kopfbild": {"head": "titelbild"},
    "regale": {"groups": "regale"},
    "tabs": {"groups": "tabs"},
    "kompakt": {"groups": "index"},
    "navigator": {"groups": "side"},
}


def _listing(surface: str) -> pp.Surface:
    axes = [pp.Axis("head", HEAD_KEY, ("titelbild",), off=HEAD_OFF)]
    if surface in NAV_SURFACES:
        axes.append(
            pp.Axis("groups", GROUPS_KEY, ("regale", "tabs", "index", "side"), off=GROUPS_AUTO)
        )
        codes = _CODES
    else:
        # без подразделов навигационные коды и сегодня рисуют обычную сетку
        codes = {c: v for c, v in _CODES.items() if "groups" not in v}
    if surface == "tours":  # FB-31 P4 R6: туры делятся на страны сами — ★ «Abschnitte»
        axes.append(pp.Axis("grouping", pp.MAIN_KEY, (FLAT,), off=GROUPED, field="grouping"))
    return pp.surface(surface, axes=axes, codes=codes, priority=("groups", "head"))


def _section_view(name: str, views: tuple[str, ...]) -> pp.Surface:
    return pp.surface(name, axes=(pp.Axis("view", pp.MAIN_KEY, views, off=RASTER),), codes={"": {}})


LISTINGS = {s: _listing(s) for s in sorted(compositions.LISTING_SURFACES)}
TEAM = _section_view("team", ("circles", "list", "compact", "duo"))
GALLERY = _section_view("gallery", ("strip", "large", "polaroid", "soft"))
#: хост → поверхность (для `siteconfig.part_surface`)
BY_HOST = {
    **{HOST_OF[s]: surface for s, surface in LISTINGS.items()},
    "team": TEAM,
    "gallery": GALLERY,
}


def effective(cfg, surface: str) -> pp.Parts:
    """Оси листинга: прежний код (`page_styles[surface]`), поверх — строки его хоста."""
    s = LISTINGS[surface]
    styles = (cfg or {}).get("page_styles") if isinstance(cfg, dict) else None
    code = styles.get(surface, "") if isinstance(styles, dict) else ""
    return pp.effective(s, cfg, HOST_OF[surface], code=code if isinstance(code, str) else "")


def code_for(cfg, surface: str) -> str:
    """Код шаблона для набора осей (то, что читают `resolve` и `data-sf-page`)."""
    return pp.legacy_code(LISTINGS[surface], effective(cfg, surface))
