"""FB-33 M3-1: окно блока — вкладки панели «Seitenaufbau».

План — `docs/fb33-editor-model-2026-11-19.md` §«План M3» (решения владельца, правки architect).
Модуль только РАСКЛАДЫВАЕТ готовые части панели по вкладкам Was · Wie anordnen · Karte ·
Texte · Seite · Felder. Поля, их значения и операции — прежние (`site_schema.PANEL_FIELDS`,
`row_settings`, `_catalog_view_panel`/`_part_view_panel`, `width_choices`, `usp_panel`,
`_banner_choice`, `block_catalog.switch_options`): второго списка полей здесь нет.

Часть — неделимый кусок панели, обычно одна форма: форма целиком живёт в одной вкладке, иначе
`panel_present` стёр бы поля скрытой вкладки. Без скриптов вкладки — ссылки `?tab=`, все
части в разметке, неактивные вкладки `hidden`.
"""

from __future__ import annotations

from django.utils.translation import pgettext_lazy

#: вкладки окна в порядке показа (макеты M0-1, M0-7…M0-12)
TABS: tuple[tuple[str, object], ...] = (
    ("was", pgettext_lazy("block window tab", "Was")),
    ("wie", pgettext_lazy("block window tab", "Wie anordnen")),
    ("karte", pgettext_lazy("block window tab", "Karte")),
    ("texte", pgettext_lazy("block window tab", "Texte")),
    ("seite", pgettext_lazy("block window tab", "Seite")),
    ("felder", pgettext_lazy("block window tab", "Felder")),
)
TAB_KEYS = tuple(key for key, _label in TABS)

#: часть панели → вкладка; порядок — порядок частей внутри вкладки
PART_TAB: dict[str, str] = {
    "list": "was",  # блок «Liste» и встроенные списки: что показать (форма «Welche · Wie»)
    "banner": "was",  # выбор баннера из библиотеки и «Wo zeigen»
    "views": "wie",  # виды картинками: категорий, товаров, групп
    "switch": "wie",  # смена вида внутри семьи (M2e)
    "platz": "wie",  # ширина и ряд — секция «Platz» (решение владельца)
    "usp": "texte",  # пункты полосы доверия
    "settings": "seite",  # настройки типа страницы у ★-строки и строк-носителей
    "formfields": "felder",  # FB-33 M2i-5: поля формы заявки (режимы, свои вопросы)
    "formlink": "felder",  # FB-33 M2i-5: у полосы/блока заявки — ссылка на окно формы
}
PART_ORDER = (
    "list",
    "banner",
    "views",
    "switch",
    "fields",
    "formfields",
    "formlink",
    "platz",
    "usp",
    "settings",
)

#: роль формы «fields» по её полям: выбор источника или набора — «Was», вид — «Wie
#: anordnen»; есть хоть одно текстовое поле — «Texte» (форма неделима)
FIELD_TAB: dict[str, str] = {"style": "wie", "page": "was", "mode": "was", "set": "was"}

#: ключ строки схемы → часть панели, которую он наполняет (замок M3-0: каждый непустой
#: ключ выбранной строки — либо часть панели, либо в `ROW_KEYS`)
PANEL_KEYS: dict[str, str] = {
    "catview": "views",
    "mainview": "views",
    "groupview": "views",
    "view_options": "switch",
    "fields": "fields",
    "source_url": "fields",
    "source_label": "fields",
    "style_only": "fields",
    "groups": "list",
    "result": "list",
    "pick": "list",
    "which": "list",
    "usp": "usp",
    "banner_pick": "banner",
    "widths": "platz",
    "carrier": "settings",
    "setting_row": "settings",
    "form_spec": "formfields",  # FB-33 M2i-5 (`fields` занято формой блока)
    "form_link": "formlink",
}
#: ключи строки, которые панель не рисует частью (метки строки, шапка окна, сырые данные)
ROW_KEYS = frozenset(
    {
        "ref",
        "key",
        "label",
        "enabled",
        "main",
        "cblock",
        "summary",
        "thumb",
        "shape",
        "fixed",
        "pinned",
        "width",
        "newline",
        "width_label",
        "flex",
        "basis",
        "width_value",
        "narrow",
        "list_data",
        "builtin_data",
        "banner_choice",
        "family_label",  # шапка окна: «Gehört zu: …»
        "can_up",  # меню «⋯» в шапке
        "can_down",
    }
)


def fields_tab(fields: list[dict]) -> str:
    names = [f.get("name", "") for f in fields or ()]
    if not names or any(n not in FIELD_TAB for n in names):
        return "texte"
    return FIELD_TAB[names[0]]


def parts(selected: dict | None, ctx: dict) -> list[str]:
    """Непустые части панели выбранной строки — по тем же условиям, что рисует шаблон."""
    if not selected:
        return []
    have = {
        "list": bool(selected.get("groups")),
        "banner": bool(selected.get("banner_pick")),
        "views": bool(
            selected.get("catview") or selected.get("mainview") or selected.get("groupview")
        ),
        "switch": bool(selected.get("view_options")),
        "fields": bool(selected.get("fields")),
        "platz": bool(selected.get("widths")),
        "usp": bool(selected.get("usp")),
        "formfields": bool(selected.get("form_spec")),
        "formlink": bool(selected.get("form_link")),
        "settings": bool(selected.get("carrier") or selected.get("setting_row"))
        and bool(ctx.get("settings") or ctx.get("design_rows")),
    }
    return [p for p in PART_ORDER if have[p]]


def tab_of(part: str, selected: dict) -> str:
    if part == "fields":
        return fields_tab(selected.get("fields") or [])
    return PART_TAB[part]


def tabs(selected: dict | None, ctx: dict, wanted: str = "") -> list[dict]:
    """Вкладки окна: [{key, label, parts, active}] — только непустые, в порядке `TABS`.
    Открыта запрошенная (`?tab=`), если она есть у блока, иначе первая."""
    found = parts(selected, ctx)
    out = []
    for key, label in TABS:
        mine = [p for p in found if tab_of(p, selected or {}) == key]
        if mine:
            out.append({"key": key, "label": label, "parts": mine, "active": False})
    if out:
        active = next((t for t in out if t["key"] == wanted), out[0])
        active["active"] = True
    return out


def explicit_tab(window: list[dict], wanted: str) -> str:
    """Вкладка, которую надо помнить после действия: только явно запрошенная и
    существующая у блока (без запроса формы остаются прежними байт-в-байт)."""
    return wanted if wanted in TAB_KEYS and any(t["key"] == wanted for t in window) else ""
