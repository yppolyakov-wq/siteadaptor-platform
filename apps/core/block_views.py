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
from django.utils.translation import pgettext_lazy

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
    "textpage": (_("Von einer Seite"), _("Text einer Seite übernehmen")),  # M3-3d
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


def _faq_texts(host: str) -> dict[str, tuple[str, str]]:
    """Подпись и пояснение плитки вида FAQ — из реестра видов страницы (`faq_views.views`,
    M2b-2a), не второй список. Вида, которого у страницы нет, здесь нет: «чужой» сохранённый
    вид остаётся с подписью пункта (`fill_options`: имя и пометка)."""
    from apps.core import faq_views

    return {v.key: (str(v.label), str(v.hint)) for v in faq_views.views(host)}


def section_tiles(block: dict, host: str = "") -> None:
    """Поле «Darstellung» секции или ссылочного блока — плитками (на месте): `tiles` и
    `thumb_src`. Пункты — те, что уже положил `fill_options` (сохранённое значение, которого
    среди видов нет, остаётся выбранной плиткой — W0); у FAQ они зависят от страницы `host`
    (детальная — три вида, M2b-2a)."""
    src = tile_section(block)
    if not src:
        return
    texts = _faq_texts(host) if src == "faq" else {}
    for f in block.get("fields") or ():
        if f.get("name") == "style" and f.get("options"):
            f["thumb_src"] = src
            f["tiles"] = [
                {
                    "value": str(v),
                    "label": texts.get(str(v), (str(lab), ""))[0],
                    "hint": texts.get(str(v), ("", ""))[1],
                    "checked": str(v) == f["value"],
                }
                for v, lab in f["options"]
            ]


def family_tiles(view_options, current: str) -> list[dict]:
    """Плитки смены вида внутри семьи — из `block_catalog.switch_options` (их порядок).
    `keeps_both` — смена на этот вид меняет источник текста, а прежний помнится (M3-3d)."""
    from apps.core import block_catalog

    out = []
    for value, label in view_options or ():
        own = FAMILY_TILES.get(value)
        out.append(
            {
                "value": value,
                "label": str(own[0]) if own else str(label),
                "hint": str(own[1]) if own else "",
                "checked": value == current,
                "keeps_both": block_catalog.switch_keeps_both(current, value),
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


def decorate(
    selected: dict | None, blocks: list[dict], config: dict | None = None, host: str = ""
) -> None:
    """Плитки вкладки «Wie anordnen» открытого блока (на месте, после `fill_options`)."""
    if not selected:
        return
    section_tiles(selected, host)
    list_style_tiles(selected)  # FB-33 M3-3c
    line = list_view(config or {}, selected)
    if line is not None:
        selected["list_view"] = line
    if selected.get("view_options"):
        selected["view_tiles"] = family_tiles(selected["view_options"], selected.get("key", ""))
        # M3-3d: плашка M0-9 — среди плиток есть смена источника текста (оба помнятся)
        selected["view_keeps_both"] = any(t["keeps_both"] for t in selected["view_tiles"])
    if selected.get("widths"):  # FB-33 M3-3b
        selected["width_tiles"] = width_tiles(selected["widths"], selected.get("width_value", ""))
    link = regale_link(blocks, selected)
    if link is not None:
        selected["regale_link"] = link


# ───────────────────────── FB-33 M3-3b: секция «Platz» (макет M0-8) ─────────────────────────

#: крупные плитки ширины (решение владельца): подпись и пояснение словами; остальные ширины
#: `width_choices` — мелкими плитками в той же группе
BIG_WIDTHS: dict[str, tuple[object, object]] = {
    "contained": (pgettext_lazy("block width", "Voll"), _("ganze Breite")),
    "w23": ("2/3", _("zwei Drittel")),
    "w12": ("1/2", _("halbe Breite")),
    "w13": ("1/3", _("ein Drittel")),
}


def width_tiles(widths, current: str) -> dict:
    """Плитки «Breite auf dem Computer» из `blocks_for(...)["widths"]` — ровно те ширины,
    что можно выбрать блоку (`width_choices`), в их порядке: {big, small}."""
    big, small = [], []
    for value, label, name, percent in widths or ():
        tile = {"value": value, "name": name, "percent": percent, "current": value == current}
        if value in BIG_WIDTHS:
            text, hint = BIG_WIDTHS[value]
            big.append({**tile, "label": str(text), "hint": str(hint)})
        else:
            small.append({**tile, "label": label})
    return {"big": big, "small": small}


# ─────────────── FB-33 M3-3c: как выглядит список + наследование и сброс (макет M0-1) ───────────────

#: что сбрасывает «zurücksetzen» — ровно то, что названо в строке наследования (решение
#: владельца): у блока «Liste» — вид списка, вывод, колонки, ряды; у встроенного списка — только
#: раскладка («Darstellung» секции — её вид, не наследуется и не сбрасывается). «Kartenform» —
#: вкладка «Karte» (M3-4)
VIEW_RESET_FIELDS = ("style", "out", "cols", "rows")
BUILTIN_RESET_FIELDS = ("out", "cols", "rows")

#: виды товаров каталога, которых на главной (пока) нет — видны с причиной (решение по M0-1)
CATALOG_ONLY_PRODUCT_VIEWS = ("schaufenster", "magazin")


def _layout_page(layout_key: str):
    """Тип страницы-листинга, чья раскладка `layout_key` (каталог, акции, услуги…)."""
    from apps.core import studio_pages

    if not layout_key:
        return None
    codes = {c for c, s in studio_pages.SETTINGS.items() if tuple(s.site_key)[:1] == (layout_key,)}
    return next(
        (pt for pt in studio_pages.PAGE_TYPES if not pt.object_args and codes & set(pt.settings)),
        None,
    )


def _summary(layout: dict) -> str:
    from apps.tenants import siteconfig

    if siteconfig.output_mode(layout) == "slider":
        return str(_("Slider"))
    return " · ".join((str(_("Raster")), _("%(n)s Spalten") % {"n": layout.get("cols") or 1}))


def _own_names(selected: dict, own: list[str]) -> list[str]:
    """Подписи своих полей вида — те же, что у полей формы «Wie … aussehen»."""
    labels = {
        f["name"]: f["label"]
        for g in selected.get("groups") or ()
        if g.get("key") == "wie"
        for f in g.get("fields") or ()
    }
    return [str(labels[name]) for name in own if name in labels]


def list_view(config: dict, selected: dict) -> dict | None:
    """Строка наследования вида списка (M0-1): откуда вид, какой он, что у блока своё.
    {source, summary, link, own (имена своих полей), reset (поля сброса), inherits};
    None — у строки списка нет."""
    from apps.core import list_blocks
    from apps.tenants import siteconfig

    data = selected.get("list_data")
    if data is not None:  # блок «Liste»: вид страницы-листинга, типа акции или стандарт
        base = list_blocks.base_view(config, data)
        own = [k for k in VIEW_RESET_FIELDS if data.get(k) not in (None, "")]
        frm = base["layout_from"]
        source, link = str(_("Standard")), ""
        if frm == "page":
            source_key = data.get("source") or siteconfig.LIST_SOURCE_DEFAULT
            page = _layout_page(list_blocks.page_layout_key(source_key))
            if page is not None:
                from apps.core import site_schema, window_links

                source = str(_("Wie auf der Seite „%(page)s“") % {"page": page.label})
                # FB-33 M5b-2: настройки типа — на строке по единому правилу (★-строка «Seite»)
                block = site_schema.page_row_ref(None, page.code)
                if block:  # ревью M5b-2 №4: строки по правилу нет — ссылки нет (не `block=`)
                    link = window_links.block_window_url(page.code, block, "seite")
        elif frm == "type":
            source = str(_("Wie bei diesem Aktionstyp"))
        return {
            "source": source,
            "summary": _summary(base["layout"]),
            "link": link,
            "own": _own_names(selected, own),
            "reset": VIEW_RESET_FIELDS,
            "inherits": frm in ("page", "type"),
        }
    data = selected.get("builtin_data")
    if data is None:
        return None
    # встроенный список главной: своего «как у страницы» нет — стандарт секции
    default = siteconfig.normalize_layout(
        None, siteconfig.GRID_SECTION_DEFAULTS.get(selected.get("key"))
    )
    try:
        cols = int(data.get("cols") or default["cols"])
    except (TypeError, ValueError):
        cols = default["cols"]
    own = [
        name
        for name, mine in (
            ("out", data.get("out") == "slider"),
            ("cols", cols != default["cols"]),
            ("rows", bool(data.get("rows"))),
        )
        if mine
    ]
    return {
        "source": str(_("Standard")),
        "summary": _summary(default),
        "link": "",
        "own": _own_names(selected, own),
        "reset": BUILTIN_RESET_FIELDS,
        "inherits": False,
    }


def list_style_tiles(selected: dict) -> None:
    """Вид списка во вкладке «Wie anordnen» — плитками из пунктов поля (на месте); у товаров
    вне каталога — «Schaufenster»/«Magazin» недоступны с причиной (решение владельца M0-1)."""
    from apps.core import site_schema

    for g in selected.get("groups") or ():
        if g.get("key") != "wie":
            continue
        for f in g.get("fields") or ():
            if f.get("name") != "style" or not f.get("thumbs"):
                continue
            f["thumb_src"] = f["thumbs"]
            f["tiles"] = [
                {"value": str(v), "label": str(lab), "hint": "", "checked": str(v) == f["value"]}
                for v, lab in f["options"]
            ]
            if f["thumbs"] == "products" and not f.get("unavailable"):
                labels = {k: lab for k, lab, _hint, _thumb in site_schema.MAIN_VIEW_LABELS}
                f["unavailable"] = [
                    {
                        "key": k,
                        "label": str(labels[k]),
                        "reason": str(_("Vorerst nur auf Katalogseiten.")),
                        "thumb_page": k,
                    }
                    for k in CATALOG_ONLY_PRODUCT_VIEWS
                ]
