"""FB-32 S5a: один реестр видов блока «Kategorien» для главной и каталога (решение владельца
2026-11-17, `docs/fb32-unified-blocks-plan-2026-11-17.md`).

Обе панели «Seitenaufbau» показывают ОДИН список видов со схемами. Вид, который на этой
странице пока не рисуется, виден недоступным с причиной: «Reiter» и «Seitenspalte» управляют
списком товаров и бывают только на страницах каталога (решение владельца); «Regale», «Index»
и «Wegweiser» на главной — следующий шаг (S5b); формы плиток главной в каталоге — тоже позже.
Хранение прежнее: главная — `style` строки секции, каталог — вид его строки категорий.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _

HOME = "home"
CATALOG = "catalog"


@dataclass(frozen=True)
class View:
    key: str
    label: object
    home: str | None  # значение на главной (`style` секции) или None — здесь нет
    catalog: str | None  # значение в каталоге (вид строки категорий) или None
    thumb_style: str = ""  # схема главной (`_style_thumb.html`)
    thumb_page: str = ""  # схема каталога (`_pagelayout_thumb.html`)
    #: вид бывает ТОЛЬКО в каталоге (управляет там списком товаров), не «пока»
    home_only_catalog: bool = False


CATEGORY_VIEWS: tuple[View, ...] = (
    View("standard", _("Standard"), "", "auto", thumb_style=""),
    View("square", _("Quadratisch"), "square", None, thumb_style="square"),
    View("tall", _("Hochformat"), "tall", None, thumb_style="tall"),
    View("wide", _("Breitbild"), "wide", None, thumb_style="wide"),
    View("compact", _("Kompakt"), "compact", None, thumb_style="compact"),
    # FB-32 S5b: и на главной — тот же построитель (`apps/catalog/category_views.py`)
    View("regale", _("Regale"), "regale", "regale", thumb_style="regale", thumb_page="regale"),
    View("index", _("Index"), "index", "index", thumb_style="index", thumb_page="kompakt"),
    View(
        "wegweiser",
        _("Wegweiser"),
        "wegweiser",
        "wegweiser",
        thumb_style="wegweiser",
        thumb_page="wegweiser",
    ),
    View("tabs", _("Reiter"), None, "tabs", thumb_page="tabs", home_only_catalog=True),
    View("side", _("Seitenspalte"), None, "side", thumb_page="navigator", home_only_catalog=True),
)


def reason(view: View, where: str) -> str:
    """Почему вид недоступен на странице `where` (пусто — доступен)."""
    if where == HOME and view.home is None:
        if view.home_only_catalog:
            return str(_("Nur auf Katalogseiten – steuert dort die Produktliste."))
        return str(_("Vorerst nur auf Katalogseiten."))
    if where == CATALOG and view.catalog is None:
        return str(_("Vorerst nur auf der Startseite."))
    return ""


def unavailable(where: str) -> list[dict]:
    """Виды реестра, недоступные на `where`: [{key, label, reason, thumb_style, thumb_page}]."""
    return [
        {
            "key": v.key,
            "label": str(v.label),
            "reason": reason(v, where),
            "thumb_style": v.thumb_style,
            "thumb_page": v.thumb_page,
        }
        for v in CATEGORY_VIEWS
        if reason(v, where)
    ]


# ─────────────────── FB-33 M3-3a: виды картинками во вкладке «Wie anordnen» ───────────────────
# План — `docs/fb33-editor-model-2026-11-19.md` §«План M3», подсрез M3-3a (макеты M0-1, M0-3,
# M0-9). Плитки строятся из УЖЕ заполненных пунктов поля «Darstellung» (`site_schema.
# fill_options`) и из `block_catalog.switch_options` — второго списка видов здесь нет; модуль
# добавляет только то, что нужно картинке: схему (`_style_thumb.html` по ключу и секции) и
# подпись вида семьи на плитке.

#: секции (и их ссылочные блоки `<секция>_ref`), вид которых окно показывает картинками —
#: у них есть схемы в `_style_thumb.html` (решение владельца: Team/Galerie — существующие виды)
TILE_SECTIONS = frozenset({"team", "gallery", "faq"})

#: подпись и пояснение вида семьи на плитке (M0-9). «Text» на плитке, «Nur Text» — в «+ Block»
#: (решение владельца); чего здесь нет — подпись `switch_options`
FAMILY_TILES: dict[str, tuple[object, object]] = {
    "text": (_("Text"), _("Überschrift + Absätze")),
    "image_text": (_("Foto + Text"), _("Foto links oder rechts")),
}


def tile_section(block: dict) -> str:
    """Секция, чьими схемами рисуются плитки вида блока (пусто — у блока плиток нет)."""
    from apps.tenants import siteconfig

    key = block.get("key") or ""
    if key in siteconfig.PAGE_REF_BLOCKS:
        base = key[: -len("_ref")]
    elif not block.get("cblock"):
        base = key
    else:
        return ""
    return base if base in TILE_SECTIONS else ""


def section_tiles(block: dict) -> None:
    """Поле «Darstellung» секции или ссылочного блока — плитками (на месте): `tiles` и
    `thumb_src`. Пункты — те, что уже положил `fill_options` (сохранённое значение, которого
    среди видов нет, остаётся выбранной плиткой — W0)."""
    src = tile_section(block)
    if not src:
        return
    for f in block.get("fields") or ():
        if f.get("name") == "style" and f.get("options"):
            f["thumb_src"] = src
            f["tiles"] = [
                {"value": str(v), "label": str(lab), "hint": "", "checked": str(v) == f["value"]}
                for v, lab in f["options"]
            ]


def family_tiles(view_options, current: str) -> list[dict]:
    """Плитки смены вида внутри семьи — из `block_catalog.switch_options` (их порядок)."""
    out = []
    for value, label in view_options or ():
        own = FAMILY_TILES.get(value)
        out.append(
            {
                "value": value,
                "label": str(own[0]) if own else str(label),
                "hint": str(own[1]) if own else "",
                "checked": value == current,
            }
        )
    return out


def regale_link(blocks: list[dict], selected: dict) -> str | None:
    """M0-3: у вида «Regale» своих карточек нет — товары в полках выглядят как в блоке
    «Produkte». Ссылка на тот блок этой страницы ("" — блока нет, None — подсказка не нужна)."""
    view = selected.get("catview") or {}
    style = (selected.get("builtin_data") or {}).get("style")
    if view.get("value") != "regale" and not (
        selected.get("key") == "categories" and style == "regale"
    ):
        return None
    if view:  # каталог и категории: товары — ★-строка
        return next((b["ref"] for b in blocks if b.get("main")), "")
    return next((b["ref"] for b in blocks if b["key"] == "products" and not b["cblock"]), "")


def decorate(selected: dict | None, blocks: list[dict]) -> None:
    """Плитки вкладки «Wie anordnen» открытого блока (на месте, после `fill_options`)."""
    if not selected:
        return
    section_tiles(selected)
    if selected.get("view_options"):
        selected["view_tiles"] = family_tiles(selected["view_options"], selected.get("key", ""))
    link = regale_link(blocks, selected)
    if link is not None:
        selected["regale_link"] = link
