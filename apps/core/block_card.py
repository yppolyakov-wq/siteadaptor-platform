"""FB-33 M3-4: вкладка «Karte» окна блока (макет M0-2).

План — `docs/fb33-editor-model-2026-11-19.md` §«План M3», срез M3-4. Модуль только
ПЕРЕКЛАДЫВАЕТ готовое поле «Kartenform» панели списка (`list_panel.groups`: его пункты уже
отобраны по виду реестром `card_forms.forms_for_view`) из группы «Wie … aussehen» в свою
часть окна и раскладывает пункты по геометрии: плитки — «Wie eine Kachel aussieht», строки —
«Wie eine Zeile aussieht» (`card_forms.shape_of`). Второго списка форм здесь нет.

Поле переезжает целиком: запись — тем же писателем (`op=update`, `f_card`, патч), форма
вкладки «Wie anordnen» карточку больше не присылает и её не трогает. Пустое значение —
«как в Design» (или как у типа акции): строка наследования называет, что действует, и ведёт
туда, где это меняется; своя форма блока сбрасывается отдельной формой «zurücksetzen».
"""

from __future__ import annotations

from django.utils.translation import gettext as _

from apps.core import card_forms

#: что сбрасывает «zurücksetzen» вкладки «Karte» — только форма карточки (сброс «Wie
#: anordnen» — `block_views.VIEW_RESET_FIELDS`/`BUILTIN_RESET_FIELDS` — её не трогает)
CARD_RESET_FIELDS = ("card",)


def _legend(shape: str) -> str:
    if shape == card_forms.SHAPE_ROW:
        return _("Wie eine Zeile aussieht")
    return _("Wie eine Kachel aussieht")


def _not_offered(shape: str, examples: list[str], view: str) -> str:
    """M0-2: каких форм у вида нет вовсе — чтобы «их нет» не читалось как «сломано»."""
    sample = ", ".join(examples[:2])
    if shape == card_forms.SHAPE_ROW:
        text = _(
            "Zeilen (%(examples)s …) passen nicht zu „%(view)s“ und werden hier nicht angeboten."
        )
    else:
        text = _(
            "Kacheln (%(examples)s …) passen nicht zu „%(view)s“ und werden hier nicht angeboten."
        )
    return text % {"examples": sample, "view": view}


def _take_card_field(selected: dict) -> dict | None:
    """Поле «Kartenform» из группы «Wie … aussehen» — вынимается (форма вкладки «Wie
    anordnen» его больше не рисует); None — поля нет (вид без карточки, источник без форм)."""
    for g in selected.get("groups") or ():
        if g.get("key") != "wie":
            continue
        fields = g.get("fields") or []
        for i, f in enumerate(fields):
            if f.get("name") == "card":
                g["fields"] = [*fields[:i], *fields[i + 1 :]]
                return f
    return None


def _inherit(config: dict, data: dict, source: str, builtin: bool) -> dict:
    """Откуда форма при пустом значении: {key, label, source, link}. Встроенный список
    главной типа акции не знает (`siteui.row_card`: своя у строки → сайт)."""
    from django.urls import NoReverseMatch, reverse

    from apps.core import list_blocks, page_settings
    from apps.tenants import siteconfig

    kind = siteconfig.LIST_SOURCES[source]["card"]
    if builtin:
        defaults = config.get("site_defaults") or {}
        key = defaults.get("promo_card" if kind == card_forms.PROMO else "card_style", "")
        frm = "site"
    else:
        base = list_blocks.base_view(config, {**data, "source": source})
        key, frm = base["card"], base["card_from"]
    key = key if key in card_forms.keys_for(kind) else ""
    label = str(card_forms.label_for(key, kind) or _("Standard"))
    if frm == "type":
        try:
            link = reverse("promotions:promo-type-list")
        except NoReverseMatch:
            link = ""
        where = _("Wie bei diesem Aktionstyp")
    else:
        code = "promo_card_form" if kind == card_forms.PROMO else "product_card_form"
        link = page_settings.design_url(code)
        where = _("Wie im Design")
    return {"key": key, "label": label, "source": str(where), "link": link, "from": frm}


def _view_label(style: str) -> str:
    from apps.tenants import siteconfig

    if not style:
        return _("Raster")
    return str(siteconfig.SECTION_STYLE_LABELS.get(style, style))


def pick(config: dict, selected: dict, field: dict, data: dict, source: str, style: str) -> dict:
    """Содержимое вкладки «Karte» из пунктов поля «Kartenform» (их отобрал вид)."""
    from apps.tenants import siteconfig

    kind = siteconfig.LIST_SOURCES[source]["card"]
    builtin = selected.get("list_data") is None
    inherit = _inherit(config, data, source, builtin)
    value = field.get("value") or ""
    shapes = card_forms.view_shapes(style)
    order = [s for s in (card_forms.SHAPE_TILE, card_forms.SHAPE_ROW) if s in shapes]
    tiles: dict[str, list[dict]] = {s: [] for s in order}
    for v, label in field.get("options") or ():
        if not v:
            continue
        shape = card_forms.shape_of(v)
        tiles.setdefault(shape, []).append(
            {"value": v, "label": str(label), "hint": "", "checked": v == value}
        )
    # первая плитка — «как в Design»: «Standard», если там Standard, иначе с его картинкой
    first = _("Standard") if not inherit["key"] else f"{inherit['source']} ({inherit['label']})"
    home = card_forms.shape_of(inherit["key"])
    home = home if home in tiles else (order or [card_forms.SHAPE_TILE])[0]
    tiles.setdefault(home, []).insert(
        0, {"value": "", "label": str(first), "hint": "", "checked": not value}
    )
    groups = [
        {"shape": s, "legend": _legend(s), "tiles": tiles[s]}
        for s in (card_forms.SHAPE_TILE, card_forms.SHAPE_ROW)
        if tiles.get(s)
    ]
    missing = [
        s for s in (card_forms.SHAPE_TILE, card_forms.SHAPE_ROW) if s not in shapes and shapes
    ]
    not_offered = [
        _not_offered(
            s,
            [
                str(lab)
                for k, lab, _hint in card_forms.forms_for(kind)
                if card_forms.shape_of(k) == s
            ],
            _view_label(style),
        )
        for s in missing
    ]
    own_label = next((t["label"] for g in groups for t in g["tiles"] if t["checked"]), "")
    return {
        "groups": groups,
        "value": value,
        "base": inherit["key"],
        "inherit": inherit,
        "own": bool(value),
        "own_label": own_label if value else "",
        "reset": CARD_RESET_FIELDS,
        "not_offered": not_offered,
    }


def decorate(selected: dict | None, config: dict | None = None) -> None:
    """Вкладка «Karte» открытого списка (на месте, после `block_views.decorate` и до
    `block_window.tabs`): поле «Kartenform» уходит из «Wie … aussehen» в `card_pick`."""
    from apps.tenants import siteconfig

    if not selected:
        return
    data = selected.get("list_data")
    if data is not None:
        source = data.get("source")
        if source not in siteconfig.LIST_SOURCES:
            source = siteconfig.LIST_SOURCE_DEFAULT
    else:
        data = selected.get("builtin_data")
        source = siteconfig.BUILTIN_LIST_SOURCES.get(selected.get("key") or "")
        if data is None or source is None:
            return
    raw = data.get("style")
    style = raw if raw in siteconfig.list_styles(source) else ""
    field = _take_card_field(selected)
    kind = siteconfig.LIST_SOURCES[source]["card"]
    if field is None or not card_forms.card_applies(kind, style):
        return
    selected["card_pick"] = pick(config or {}, selected, field, data, source, style)
