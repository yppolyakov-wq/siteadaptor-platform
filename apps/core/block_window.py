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
    # FB-33 M5d-1: неподвижная строка G2 — что показывает и где правится содержимое; у строки
    # с частью «pinned» (Gutschein-Formular, § 312j) — на её вкладке, над ней (`tab_of`)
    "inhalt": "was",
    "list": "was",  # блок «Liste» и встроенные списки: что показать (форма «Welche · Wie»)
    "banner": "was",  # выбор баннера из библиотеки и «Wo zeigen»
    "places": "was",  # FB-33 M3-6 (M0-7): «Wo zeigen» одного баннера — в черновик
    "tiles": "was",  # FB-33 M3-5b: плашки Schnellzugriff и «Vorlage für die Kacheln» — одна форма
    "views": "wie",  # виды картинками: категорий, товаров, групп
    "switch": "wie",  # смена вида внутри семьи (M2e)
    "listview": "wie",  # FB-33 M3-3c: как выглядит список (группа «Wie … aussehen» своей формой)
    "inherit": "wie",  # FB-33 M5b-2 (A-H2): у ★ категории — откуда вид товаров, «zurücksetzen»
    "pagelink": "wie",  # FB-33 M5b-2 (A-H1): у списка без своего вида — ссылка на ★-строку
    "card_pick": "karte",  # FB-33 M3-4 (M0-2): форма карточки — только подходящие виду
    "platz": "wie",  # ширина и ряд — секция «Platz» (решение владельца)
    "usp": "texte",  # пункты полосы доверия
    "faq": "texte",  # FB-33 M3-5b: вопросы FAQ (общие для всех страниц)
    "seo": "texte",  # FB-33 M3-6: SEO страницы у «Einstellungen der Seite» (текстовые)
    "seolink": "texte",  # FB-33 M3-6: у категории — ссылка на форму категории
    "pinned": "texte",  # FB-33 M3-6 (M0-10): плашка § 312j и подпись кнопки (только чтение)
    "settings": "seite",  # настройки типа страницы у ★-строки и строк-носителей
    "listlink": "seite",  # FB-33 M5b-2: у ★-строки — «Darstellung … im Block › Wie anordnen»
    "formfields": "felder",  # FB-33 M2i-5: поля формы заявки (режимы, свои вопросы)
    "noinput": "felder",  # FB-33 M3-6: «Hier werden keine Angaben abgefragt»
    "formlink": "felder",  # FB-33 M2i-5: у полосы/блока заявки — ссылка на окно формы
}
PART_ORDER = (
    "inhalt",
    "list",
    "banner",
    "places",
    "tiles",
    "views",
    "switch",
    "listview",
    "inherit",
    "pagelink",
    "card_pick",
    "fields",
    "formfields",
    "formlink",
    "platz",
    "usp",
    "faq",
    "seo",
    "seolink",
    "pinned",
    "noinput",
    "settings",
    "listlink",
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
    "view_tiles": "switch",  # FB-33 M3-3a: те же виды семьи плитками
    "view_keeps_both": "switch",  # стопка: плашка M0-9 «оба источника текста помнятся» (M3-3d)
    "list_view": "listview",  # FB-33 M3-3c: строка наследования вида списка
    "card_pick": "card_pick",  # FB-33 M3-4: вкладка «Karte» (`block_card.decorate`)
    "regale_link": "views",  # FB-33 M3-3a (M0-3): у «Regale» — где меняется вид товаров
    "fields": "fields",
    "source_url": "fields",
    "source_label": "fields",
    "style_only": "fields",
    "groups": "list",
    "result": "list",
    "pick": "list",
    "which": "list",
    "usp": "usp",
    "faq_items": "faq",  # FB-33 M3-5b
    "tiles": "tiles",  # FB-33 M3-5b
    "banner_pick": "banner",
    "places": "places",  # FB-33 M3-6
    "seo": "seo",
    "seo_link": "seolink",
    "page_inherit": "inherit",  # FB-33 M5b-2: строка наследования вида у ★ категории
    "list_link": "listlink",  # FB-33 M5b-2: ★-строка → вид основного списка
    "page_link": "pagelink",  # FB-33 M5b-2: основной список → настройки типа на ★-строке
    "legal": "pinned",
    "noinput": "noinput",
    "widths": "platz",
    "width_tiles": "platz",  # FB-33 M3-3b: те же ширины плитками (M0-8)
    "carrier": "settings",
    "setting_row": "settings",
    "form_spec": "formfields",  # FB-33 M2i-5 (`fields` занято формой блока)
    "field_langs": "fields",  # FB-33 M3-5c: языки переводов окна (поля — у своей части)
    "form_link": "formlink",
    "content": "inhalt",  # FB-33 M5d-1 (`window_parts.content_part`)
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
        "drop_after",  # FB-33 M3-6: закреплённая строка — цель броска только «после»
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
        "with_title",  # FB-33 M5b-2: на «Seite» — «Überschrift der Seite» и «…dieser Seitenart»
        "can_up",  # меню «⋯» в шапке
        "can_down",
        "can_hide",  # FB-33 M5c-2: «Ausblenden» в «⋯» — по правилу `mutate`
        "num",  # FB-33 M5c-2: номер строки схемы (только показ)
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
        "inhalt": bool(selected.get("content")),
        "list": bool(selected.get("groups")),
        "banner": bool(selected.get("banner_pick")),
        "places": bool(selected.get("places")),
        "tiles": bool(selected.get("tiles")),
        "views": bool(
            selected.get("catview") or selected.get("mainview") or selected.get("groupview")
        ),
        "switch": bool(selected.get("view_options")),
        "listview": any(
            g.get("key") == "wie" and g.get("fields") for g in selected.get("groups") or ()
        ),
        "card_pick": bool(selected.get("card_pick")),
        "inherit": bool(selected.get("page_inherit")),
        "pagelink": bool(selected.get("page_link")),
        "listlink": bool(selected.get("list_link")),
        "fields": bool(selected.get("fields")),
        "platz": bool(selected.get("widths")),
        "usp": bool(selected.get("usp")),
        "faq": bool(selected.get("faq_items")),
        "seo": bool(selected.get("seo")),
        "seolink": bool(selected.get("seo_link")),
        "pinned": bool(selected.get("legal")),
        "noinput": bool(selected.get("noinput")),
        "formfields": bool(selected.get("form_spec")),
        "formlink": bool(selected.get("form_link")),
        "settings": bool(selected.get("carrier") or selected.get("setting_row"))
        and bool(ctx.get("settings") or ctx.get("design_rows")),
    }
    return [p for p in PART_ORDER if have[p]]


def tab_of(part: str, selected: dict) -> str:
    from apps.core import site_schema

    if part == "fields":
        if site_schema.is_title_row(selected):
            # FB-33 M5b-2: поля «Seitentitel» — на «Seite» ★-строки (переводы — той же формой)
            return "seite"
        return fields_tab(selected.get("fields") or [])
    if part == "inhalt" and selected.get("legal"):
        # FB-33 M5d-1 (ответ владельца §8.5 №6): у правовой строки — на вкладке плашки
        # § 312j, над ней (`PART_ORDER`), без второй вкладки
        return PART_TAB["pinned"]
    return PART_TAB[part]


def tabs(selected: dict | None, ctx: dict, wanted: str = "") -> list[dict]:
    """Вкладки окна: [{key, label, parts, active}] — только непустые, в порядке `TABS`.
    Открыта запрошенная (`?tab=`), если она есть у блока, иначе первая."""
    from apps.core import site_schema

    found = parts(selected, ctx)
    out = []
    for key, label in TABS:
        mine = [p for p in found if tab_of(p, selected or {}) == key]
        if mine:
            out.append({"key": key, "label": label, "parts": mine, "active": False})
    if out:
        if not wanted and (selected or {}).get("ref") == site_schema.PAGE_REF:
            wanted = "seite"  # FB-33 M3-6 (M0-11): «Einstellungen der Seite» — с «Seite»
        active = next((t for t in out if t["key"] == wanted), out[0])
        active["active"] = True
    return out


#: FB-33 M5d-1: части, при которых окну «Vorschau» не нужна — неподвижная строка G2 показывает
#: только что в ней и где правится (вместе с плашкой § 312j у Gutschein-Formular)
NO_PREVIEW_PARTS = frozenset({"inhalt", "pinned"})


def has_preview(window: list[dict]) -> bool:
    """Строить ли «Vorschau» окна: есть вкладки и это не окно «Inhalt» (части только из
    `NO_PREVIEW_PARTS` и среди них «inhalt»; окно одной плашки § 312j — прежнее, с «Vorschau»)."""
    found = {p for t in window or () for p in t.get("parts") or ()}
    if not found:
        return False
    return not ("inhalt" in found and found <= NO_PREVIEW_PARTS)


def explicit_tab(window: list[dict], wanted: str) -> str:
    """Вкладка, которую надо помнить после действия: только явно запрошенная и
    существующая у блока (без запроса формы остаются прежними байт-в-байт)."""
    return wanted if wanted in TAB_KEYS and any(t["key"] == wanted for t in window) else ""


# --- FB-33 M3-5a: вкладка «Texte» — простые поля; без скриптов вкладки не теряют набранное ---

#: `maxlength` и подсказка «Höchstens N Zeichen» — у коротких полей; длинный текст (тело
#: 20 000) без `maxlength`: браузер молча обрезал бы вставку, потолок — на сервере с сообщением
_HINT_UP_TO = 2000


def field_caps(selected: dict | None) -> dict[str, int]:
    """Потолки ввода полей формы «fields» выбранной строки (тот же источник, что у записи:
    `siteconfig.CBLOCK_INPUT_CAPS`, «Seitentitel» — `page_title`, «Was passiert jetzt» —
    `confirmation_page`)."""
    from apps.core import site_schema
    from apps.tenants import siteconfig

    if not selected:
        return {}
    key = selected.get("key") or ""
    if site_schema.is_title_row(selected):  # FB-33 M5b-2: и ★-строка с полями заголовка
        from apps.core import page_title

        return {"title": page_title.TITLE_MAX, "intro": page_title.INTRO_MAX}
    if key == "next" and not selected.get("cblock"):
        from apps.core import confirmation_page

        return {"text": confirmation_page.NEXT_MAX}
    if not selected.get("cblock"):
        return {}
    return dict(siteconfig.CBLOCK_INPUT_CAPS.get(siteconfig.cblock_type(key) or key, {}))


def field_meta(selected: dict | None, field: dict) -> dict:
    """Контракт поля вкладки «Texte» (и закреплённых блоков M3-6): {max, max_hint, example,
    hint, described} — `described` — id подсказок для `aria-describedby`."""
    from django.utils.translation import gettext

    from apps.tenants import siteconfig

    name = field.get("name", "")
    cap = field_caps(selected).get(name)
    key = (selected or {}).get("key") or ""
    btype = siteconfig.cblock_type(key) or key
    example = (
        gettext("z. B. /kontakt oder https://…")
        if btype == "button" and name == "url" and (selected or {}).get("cblock")
        else ""
    )
    max_hint = (
        gettext("Höchstens %(n)s Zeichen.") % {"n": cap} if cap and cap <= _HINT_UP_TO else ""
    )
    hint = str(field.get("hint") or "")
    ids = []
    if hint:
        ids.append(f"schema-f-{name}-hint")
    if example or max_hint:
        ids.append(f"schema-f-{name}-max")
    return {
        "max": cap if cap and cap <= _HINT_UP_TO else "",
        "max_hint": max_hint,
        "example": example,
        "hint": hint,
        "described": " ".join(ids),
    }


#: части-формы окна, которые без скриптов применяет кнопка вкладки (решение M3-2 п.3): у
#: открытой вкладки с ровно одной такой ЧАСТЬЮ прочие вкладки — кнопки её формы
#: (`form="bw-form-<часть>"`, `name="zu_tab"`): набранное уходит в черновик, затем
#: открывается выбранная вкладка. Считаются части, не `<form>`: у «Karte» вторая форма —
#: «zurücksetzen». `card_pick` (вкладка `karte`, M3-4) и `faq` (во «Texte», M3-5b) — формы
#: `bw-form-card_pick`/`bw-form-faq`.
#: Замок: у каждой живой применяющей части окна есть форма с её `form_id`.
APPLY_FORM_PARTS = ("fields", "usp", "formfields", "card_pick", "faq", "seo")  # seo — M3-6
#: вкладка → её применяющие части. FB-33 стопка 14 E3 (решение владельца 2026-11-24): на «Wie
#: anordnen» применяет только вид списка (`bw-form-listview`; «Platz» и «zurücksetzen» — свои
#: формы, не части); у прочих блоков с видом на «Wie» (FAQ, `usp_bar`, …) вкладки — ссылки
APPLY_TAB_PARTS: dict[str, tuple[str, ...]] = {
    "texte": APPLY_FORM_PARTS,
    "felder": APPLY_FORM_PARTS,
    "karte": APPLY_FORM_PARTS,
    "wie": ("listview",),
}
#: вкладки, переход с которых применяет форму — ключи `APPLY_TAB_PARTS` (второго списка нет)
APPLY_TABS = tuple(APPLY_TAB_PARTS)
#: Enter в поле — та же кнопка, что первая кнопка самой формы (кнопка «по умолчанию» перед
#: вкладками: иначе ею стала бы кнопка вкладки, и Enter переключал бы вкладку). У FAQ первая
#: кнопка формы — «Übernehmen» `faq_add` (принимает и новый вопрос; op=update — скрытое поле)
_DEFAULT_SUBMIT = {"formfields": ("f_commit_new", "1"), "faq": ("faq_add", "1")}
#: операция формы без своей кнопки, когда её шлёт кнопка вкладки (`op_default`)
OP_DEFAULTS = ("update", "faq_update")


def form_id(part: str) -> str:
    return f"bw-form-{part}"


def apply_form(window: list[dict]) -> dict | None:
    """Форма, которую применяют кнопки вкладок: {part, form, name, value} (name/value —
    кнопки «по умолчанию»), либо None — вкладки остаются ссылками байт-в-байт."""
    active = next((t for t in window or () if t["active"]), None)
    if active is None or len(window) < 2 or active["key"] not in APPLY_TABS:
        return None
    mine = [p for p in active["parts"] if p in APPLY_TAB_PARTS[active["key"]]]
    if len(mine) != 1:
        return None
    name, value = _DEFAULT_SUBMIT.get(mine[0], ("op", "update"))
    return {"part": mine[0], "form": form_id(mine[0]), "name": name, "value": value}


#: части с кнопкой «Übernehmen»: без скриптов набранное в них при переходе по вкладке-ссылке
#: не применяется — у таких вкладок подсказка «erst übernehmen»
#: tiles — стопка 2 (M3-5b), places — M3-6 («Hinzufügen» у мест баннера)
_TYPED_PARTS = (*APPLY_FORM_PARTS, "list", "listview", "tiles", "places")


def link_hint(window: list[dict]) -> bool:
    """Вкладки — ссылки, а у открытой есть форма с «Übernehmen»: подсказать применить до
    перехода (без скриптов; со скриптами правки применяются сами — подсказку прячет JS)."""
    active = next((t for t in window or () if t["active"]), None)
    if active is None or len(window) < 2 or apply_form(window) is not None:
        return False
    return any(p in _TYPED_PARTS for p in active["parts"])


def goto_tab(post) -> str:
    """Вкладка, на которую ушла кнопка вкладки (`zu_tab`): из белого списка и среди вкладок
    окна этого блока (`bw_tabs` — их рисует сервер рядом с кнопками; подделка влияет только
    на свой адрес возврата). Иначе — нет."""
    wanted = post.get("zu_tab", "")
    offered = str(post.get("bw_tabs", "")).split()
    return wanted if wanted in TAB_KEYS and wanted in offered else ""


def default_op(post) -> str:
    """Операция формы, отправленной кнопкой вкладки без `op`: `op_default` из белого
    списка, иначе правка полей (`update`)."""
    op = post.get("op_default", "")
    return op if op in OP_DEFAULTS else "update"


#: FB-33 M2i-5 (a11y, отложено до M3-5a): фокус после кнопок вкладки «Felder» — на вопрос
_FELDER_ID = r"(q[1-9][0-9]{0,3}|n[0-9]{1,3})"


def felder_anchor(post, form_state: dict | None) -> str:
    """Якорь после кнопки вопроса во «Felder»: ↑/↓ — тот же вопрос, «Entfernen» — соседний
    (следующий, иначе предыдущий; нет — список «Eigene Fragen»), «+ Frage» — новый
    (последний) вопрос. Пусто — прежний якорь."""
    import re

    do = post.get("f_do", "")
    match = re.fullmatch(rf"(up|down|del):{_FELDER_ID}", do)
    if match:
        action, qid = match.groups()
        if action != "del":
            return f"schema-tab-q-{qid}"
        # порядок вопросов — как в форме (поля подписей идут в порядке DOM)
        order = [
            m.group(1) for k in post for m in [re.fullmatch(rf"f_q_{_FELDER_ID}_label", k)] if m
        ]
        if form_state is None:
            # черновика вкладки нет (правка вернула сохранённое) — прочие вопросы на месте
            left = set(order) - {qid}
        else:
            custom = form_state.get("custom") or ()
            left = {q.get("id") for q in custom if isinstance(q, dict)}
        if qid in order:
            at = order.index(qid)
            for near in (*order[at + 1 :], *reversed(order[:at])):
                if near in left:
                    return f"schema-tab-q-{near}"
        return "schema-tab-questions"
    if do == "add":
        custom = (form_state or {}).get("custom") or []
        last = custom[-1].get("id") if custom and isinstance(custom[-1], dict) else ""
        if last and re.fullmatch(_FELDER_ID, str(last)):
            return f"schema-tab-q-{last}"
        return "schema-tab-questions"
    return ""


def felder_said(post) -> str:
    """Что сделала кнопка вопроса во «Felder» — для живой области (a11y ревью M3-5a)."""
    from django.utils.translation import gettext

    do = str(post.get("f_do", ""))
    if do == "add":
        return gettext("Hinzugefügt.")
    return {
        "up": gettext("Nach oben verschoben."),
        "down": gettext("Nach unten verschoben."),
        "del": gettext("Frage entfernt."),
    }.get(do.split(":", 1)[0], "")
