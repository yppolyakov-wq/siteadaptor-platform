"""FB-33 M3-5b: части окна блока «Seitenaufbau» — вопросы FAQ («Texte») и плашки
Schnellzugriff («Was»). Только модель для шаблона: пишут `faq_content` (черновик —
`aufbau_draft`) и данные блока `quick_links` (`hero_tiles.update_data`)."""

from __future__ import annotations

import logging

from django.utils.translation import gettext_lazy

logger = logging.getLogger(__name__)


def _item(config: dict, home: bool, host: str, ref: str) -> dict | None:
    """Строка блока в показанном конфиге; None — прочитать не удалось (в лог)."""
    from django.db import connection

    from apps.core import site_schema

    try:
        items = site_schema.load_items(config, home, host)
    except Exception:  # noqa: BLE001 — окно без формы плашек лучше, чем упавший экран
        logger.exception(
            "window_parts: block rows unavailable (%s, %s, %s)",
            getattr(connection, "schema_name", ""),
            host or "home",
            ref,
        )
        return None
    return next((it for it in items if isinstance(it, dict) and it.get("id") == ref), None)


def _items(config: dict, home: bool, host: str) -> list:
    from apps.core import site_schema

    try:
        return site_schema.load_items(config, home, host)
    except Exception:  # noqa: BLE001 — как `_item`: окно без подсказки лучше упавшего экрана
        logger.exception("window_parts: rows unavailable (%s)", host or "home")
        return []


def decorate(
    selected: dict | None,
    saved: dict,
    draft: dict | None,
    home: bool,
    config: dict,
    host: str,
    opened: int | None = None,
    user=None,
) -> None:
    """Дополнить выбранную строку частями среза. `saved` — сохранённый конфиг (вопросы
    черновика и их источники — из `draft`), `config` — показанный (с черновиком)."""
    if not selected:
        return
    from apps.core import aufbau_draft, faq_content, hero_tiles, object_faq
    from apps.tenants import siteconfig

    row = {"key": selected.get("key"), "id": selected.get("ref") if selected.get("cblock") else ""}
    key = selected.get("key") or ""
    if row["id"] and (siteconfig.cblock_type(key) or key) == "faq_ref" and not home:
        # FB-33 M2b-2b: источник вопросов — в данных строки (`data.source`)
        item = _item(config, home, host, selected["ref"])
        row["data"] = (item or {}).get("data") or {}
    own = None
    if not home and (siteconfig.cblock_type(key) or key) in ("faq", "faq_ref"):
        page = {"home": home, "host": host, "items": (draft or {}).get("items")}
        if page["items"] is None:
            page["items"] = _items(config, home, host)
        own = object_faq.panel(page, host, row, opened, saved, user)
    if aufbau_draft._is_faq_row({"home": home}, row):
        items, src = faq_content.state(saved, draft)
        selected["faq_items"] = faq_content.panel(items, src, saved, opened)
        if own:  # детальная: общие вопросы и выбор источника
            selected["faq_items"].update(own)
        # FB-33 E5: общий заголовок FAQ — только при общем источнике (ревью H3); в окне — правка
        # черновика, иначе сохранённый
        pending = draft or {}
        selected["faq_items"]["title_on"] = True
        selected["faq_items"]["title"] = (
            pending["faq_title"] if "faq_title" in pending else faq_content.title(saved)
        )
    elif own:
        selected["faq_items"] = own  # FB-33 M2b-2b: свои вопросы объекта (или подсказка)
    if selected.get("cblock") and (siteconfig.cblock_type(key) or key) == "quick_links":
        # плашки и выбор набора — одна форма (смена набора сбрасывает скрытие и подписи)
        item = _item(config, home, host, selected["ref"])
        if item is None:
            # ревью M3-5b: без данных блока форма плашек не рисуется — иначе «Übernehmen» с
            # пустым набором стёр бы набор, скрытие и подписи (остаётся прежняя форма набора)
            return
        selected["tiles"] = hero_tiles.panel(item.get("data") or {})
        selected["fields"] = []


#: стопка 2 (a11y M3-5b, как «Felder» M3-5a): список вопросов, когда их не осталось
FAQ_LIST_ANCHOR = "schema-tab-faq-list"


def faq_anchor_id(i: int) -> str:
    """id вопроса FAQ в окне (заголовок <summary> его <details>)."""
    return f"schema-tab-faq-{i}"


def faq_anchor(post, count: int, opened=None) -> str:
    """Якорь после кнопки вопроса FAQ: ↑/↓ — сдвинутый вопрос (`opened` — куда он встал),
    «Entfernen» — тот, что встал на его место (иначе предыдущий; нет — список), новый вопрос —
    последний. `count` — вопросов после правки. Пусто — прежний якорь."""
    if post.get("faq_present") != "1":
        return ""
    if post.get("faq_scope") == "object":
        # FB-33 M2b-2b: свои вопросы объекта — номер после кнопки помнит сама правка (`opened`,
        # `object_faq._remember_focus`): `count` вызывающего — число ОБЩИХ вопросов
        if not isinstance(opened, int) or not any(
            post.get(k) is not None for k in ("faq_move", "faq_remove", "faq_add")
        ):
            return ""
        return faq_anchor_id(opened) if opened >= 0 else FAQ_LIST_ANCHOR
    if post.get("faq_move") is not None:
        return faq_anchor_id(opened) if isinstance(opened, int) and 0 <= opened < count else ""
    removed = str(post.get("faq_remove") or "")
    if removed.isdigit():
        return faq_anchor_id(min(int(removed), count - 1)) if count else FAQ_LIST_ANCHOR
    if post.get("faq_add") is not None and str(post.get("faq_new_q") or "").strip() and count:
        return faq_anchor_id(count - 1)
    return ""


# --- FB-33 M5d-1 (D1) / M5d-2: часть «Inhalt» — что показывает строка и где это правится -------


#: почему ссылки нет — видимой строкой (решение владельца; ревью M5d-1); ключ — ответ
#: `nav_registry.screen_closed`
_CLOSED_REASONS = {
    "perm": gettext_lazy("Nur mit Berechtigung bearbeitbar"),
    "module": gettext_lazy("Modul ist nicht aktiv"),
    "package": gettext_lazy("Nicht in Ihrem Paket enthalten"),
}

#: FB-33 M5d-2 (Y4): что можно сделать со строкой — по её флагам; «⋯» есть и в шапке окна,
#: поэтому без «in der Liste» (список под модальным окном инертен)
_ACT_HIDE_MOVE = gettext_lazy("Ausblenden und Verschieben über „⋯“.")
_ACT_HIDE = gettext_lazy("Ausblenden über „⋯“.")
#: ответ владельца (план стопки 12 §11): у скрытой строки — текст, кнопки в окне нет
_ACT_SHOW = gettext_lazy("Schließen Sie das Fenster; dann „Einblenden“ unter „Ausgeblendet“.")
_VISIBLE = gettext_lazy("sichtbar.")
_VISIBLE_ALL = gettext_lazy("sichtbar — %(all)s.")
_HIDDEN = gettext_lazy("ausgeblendet.")
#: A7a: раздел, который у еды скрыть нельзя (`detail_parts.FOOD_LOCKED`)
_VISIBLE_LMIV = gettext_lazy("sichtbar — bei Lebensmitteln Pflicht (LMIV).")
_FILLED = gettext_lazy("— ausgefüllt.")
_EMPTY = gettext_lazy("— leer.")
_FIELD_EVERY = gettext_lazy("Feld „%(field)s“ %(every)s.")
_FIELD_THIS = gettext_lazy("Feld „%(field)s“ %(this)s")
#: FB-33 M5d-2b: раздел рисуется не у этого вида объекта (`ContentSource.kinds`) — вместо
#: видимости; «all» — слова вида строки («bei allen Reisen»)
_NOT_FOR_KIND = gettext_lazy("%(all)s wird dieser Block nicht gezeigt.")
#: FB-33 M5d-8 (E7): «Woher» из нескольких полей — списком (`detail_sections.SourceField`)
_LIST_EVERY = gettext_lazy("Diese Felder %(every)s:")
_LIST_THIS = gettext_lazy("Felder %(this)s — %(n)s von %(m)s ausgefüllt:")
#: группа полей одной вкладки формы (a11y M3: без «›» в озвучиваемом тексте)
_GROUP_TAB = gettext_lazy("Formular, Reiter „%(tab)s“:")
_GROUP_SECTION = gettext_lazy("Formular, Reiter „%(tab)s“, Abschnitt „%(section)s“:")
_QUOTED = gettext_lazy("„%(field)s“")
_ITEM_FILLED = gettext_lazy("„%(field)s“ — ausgefüllt")
_ITEM_EMPTY = gettext_lazy("„%(field)s“ — leer")
#: у группы из стольких полей и больше — вложенный список, меньше — через запятую (a11y M3)
_NESTED_FROM = 3
#: значок состояния — только украшение (`aria-hidden`), состояние сказано словом (a11y M1)
_ICONS = {True: "✓", False: "–"}
#: ревью M4, M-1/M-2: пробы «заполнено ли» по тому же ПРОИЗВОДНОМУ значению, что решает показ
#: витрины, — ЗАКРЫТЫЙ реестр «имя → (вид, модуль, имя)»; помощник импортируется лениво,
#: незнакомое имя — в журнал без вызова. Виды:
#: - "object" — функция(obj, tenant) (точка карты: координаты события или адрес бизнеса);
#: - "field" — функция(значение поля модели — голова пути), дальше ключи пути по результату
#:   (коды аллергенов → подписи каталога; `details` → `landing` базового языка);
#: - "property" — свойство модели объекта (только `property`, читает свои поля; модуль пуст).
#: - "tenant" — функция(бизнес, вид блока строки) (FB-33 M5e-2a: пункты «Kontakt» главной).
#: Без запросов к БД (кроме `contact_hours`: каникулы `open_status`, как у витрины).
_PROBES = {
    "map_point": ("object", "apps.events.services", "map_point"),
    "allergen_labels": ("field", "apps.catalog.food", "allergen_labels"),
    "additive_labels": ("field", "apps.catalog.food", "additive_labels"),
    "landing": ("field", "apps.events.details", "normalize"),
    "amenity_badges": ("property", "", "amenity_badges"),
    # FB-33 M5e-2a: пункты блока «Kontakt» главной — условия `storefront/sections/_contact.html`
    # у вида блока (`section_row.style`): вид "tenant" — функция(бизнес, вид блока)
    "contact_address": ("tenant", "apps.core.window_parts", "contact_address"),
    "contact_phone": ("tenant", "apps.core.window_parts", "contact_phone"),
    "contact_email": ("tenant", "apps.core.window_parts", "contact_email"),
    "contact_hours": ("tenant", "apps.core.window_parts", "contact_hours"),
    "contact_map": ("tenant", "apps.core.window_parts", "contact_map"),
}
#: FB-33 M5e-2a: разделы меню, где живут списки сущностей (не «Verkäufe»: там сделки —
#: «Check-ins» с ключом `stays`)
_LIST_HUBS = ("sellables", "marketing")
#: FB-33 M5e-2a: итог «Woher» данных бизнеса — статичный текст (без живой области, Y4)
_N_OF_M = gettext_lazy("%(n)s von %(m)s ausgefüllt")
#: вид блока «Kontakt» одной строкой: без карты и без часов текстом (`_contact.html`)
_COMPACT = "compact"


def contact_address(tenant, style: str = "") -> bool:
    """Проба M5e-2a: адрес — `{% if request.tenant.address %}` (`_contact.html`, все виды)."""
    return bool(tenant.address)


def contact_phone(tenant, style: str = "") -> bool:
    """Проба M5e-2a: телефон — `public_phone` (свой или телефон владельца), все виды."""
    return bool(tenant.public_phone)


def contact_email(tenant, style: str = "") -> bool:
    """Проба M5e-2a (ревью 1 №4): e-mail — `public_email` (свой или владельца), все виды."""
    return bool(tenant.public_email)


def contact_hours(tenant, style: str = "") -> bool:
    """Проба M5e-2a: часы — у вида «compact» только «Heute» по статусу (`open_status`: часы по
    дням или каникулы), у прочих — ещё текст часов (`_contact.html`)."""
    if style == _COMPACT:
        return bool(tenant.open_status())
    return bool(tenant.opening_hours or tenant.open_status())


def contact_map(tenant, style: str = "") -> bool:
    """Проба M5e-2a (ревью 1 №4): карта — ссылка «Karte öffnen» (`map_url`, все виды) или
    встроенная карта по координатам (кроме «compact»)."""
    if tenant.map_url:
        return True
    return style != _COMPACT and bool(tenant.latitude and tenant.longitude)


def page_family(host) -> str:
    """FB-33 M5e-2a: семья страницы для `detail_sections.PAGE_SOURCES`: "home" — главная (хост
    ""), "catalog_list" — каталог и категории, "list" — другая страница с основным списком
    (`siteconfig.has_main_list`), "" — другая."""
    from apps.core import site_schema
    from apps.tenants import siteconfig

    if host == "":
        return "home"
    if not siteconfig.has_main_list(host):
        return ""
    # TODO(M5e-3): публичный `site_schema.main_list_source(host)` вместо частных имён
    if site_schema._main_list_host(host) in ("catalog", "category"):
        return "catalog_list"
    return "list"


def _list_source(host) -> str:
    """Источник основного списка хоста (как у `site_schema.main_list_name`); "" — нет."""
    from apps.core import site_schema
    from apps.tenants import siteconfig

    if not isinstance(host, str) or not siteconfig.has_main_list(host):
        return ""
    # TODO(M5e-3): публичный `site_schema.main_list_source(host)` вместо частных имён
    base = site_schema._main_list_host(host)
    return (
        site_schema._MAIN_LIST_SOURCES.get(base)
        or siteconfig.BUILTIN_LIST_SOURCES.get(base)
        or (base if base in siteconfig.LIST_SOURCES else "")
    )


def list_source_screen(source: str) -> str:
    """FB-33 M5e-2a: имя URL экрана, где правятся записи источника `siteconfig.LIST_SOURCES`:
    запись `nav_registry` (разделы `_LIST_HUBS`) с ключом источника — сначала с ТОЧНО его
    модулем, потом без модуля; иначе — единственный список объектов детали его карточек
    (`content_nav` раздела-поля; несколько разных — предупреждение, экрана нет). "" — нет."""
    from apps.core import detail_parts, detail_sections, nav_registry
    from apps.tenants import siteconfig

    spec = siteconfig.LIST_SOURCES.get(source)
    if not spec:
        return ""
    entries = [
        e
        for e in nav_registry.ENTRIES
        if e.hub in _LIST_HUBS and e.nav_key == source and not e.query
    ]
    for module in (spec["module"], None):
        entry = next((e for e in entries if e.module_key == module), None)
        if entry is not None:
            return entry.url_name
    module = detail_parts.SECTION_HOSTS.get(f"{spec.get('facets') or ''}_detail", "")
    screens = {
        s.content_nav
        for s in detail_sections.sections_for(module)
        if s.content_nav and s.source is not None and s.source.kind == "field"
    }
    if len(screens) > 1:
        logger.warning(
            "window_parts: list source %r has several object screens %s - no screen",
            source,
            sorted(screens),
        )
        return ""
    return next(iter(screens), "")


def main_list_screen(host) -> str:
    """FB-33 M5e-2a: экран ★ основного списка страницы `host` — экран его источника
    (`list_source_screen`); "" — у списка нет источника (Team, Galerie, Merkzettel, Lookbook)
    или у страницы нет списка."""
    source = _list_source(host)
    return list_source_screen(source) if source else ""


#: ревью M5: видно ли поле в форме объекта этого бизнеса — «вид → (модуль, функция(tenant,
#: имя поля, объект|None))»; вида нет в реестре — видны все поля
_FORM_GATES = {"product": ("apps.catalog.form_flags", "field_shown")}


def content_part(
    selected: dict | None,
    host: str,
    request,
    *,
    code: str = "",
    obj=None,
    back: dict | None = None,
    page_label: str = "",
) -> None:
    """Часть окна «Inhalt» у строки раздела: что блок показывает, откуда содержимое и где оно
    правится. Описание — в реестре (`DetailSection.content_nav` и `.source`, своих списков
    здесь нет): `selected["content"] = {summary, note, woher, filled, visibility, actions,
    fixed, link, more_links, reason, screen, sourced}`.

    Без `source` — неподвижная строка G2 (M5d-1): сводка — `summary` строки (пусто — подпись),
    ссылка `{"label", "url", "only_here"}` — запись `nav_registry`. С `source` (M5d-2,
    `sourced`) сводка — `source.shows`, иначе подпись раздела (не сводка строки: у объекта
    это её статус), а ссылка — по виду источника:
    - `setting` — запись реестра (+ `query`, подпись «… › sub»);
    - `field` у типа — запись списка объектов; у объекта — его форма (`back`, подпись — имя
      объекта) и `only_here`;
    - `page` — редактор страницы (`content_pages.edit_url_for_code(code)`), подпись
      «Seiten › <имя>»;
    - `auto` — без ссылки.
    M5d-2b: у строки ТИПА общего хоста двух видов (события и туры) раздел обоих видов даёт ещё
    ссылки `more_links` (`[{"label", "url"}]`, записи `source.more_nav`) — только открытые этому
    пользователю, закрытая — без причины. Раздел рисуется не у вида этой строки объекта
    (`source.kinds`) — одна фраза в `visibility`, без «Woher», ссылки и действий.
    Имя объекта и страницы в подписи — в `<span lang>`, когда язык содержимого не язык
    интерфейса. Видимость и действия — из флагов строки (`enabled`, `can_hide`, `can_up`,
    `can_down`, `pinned`) и её `summary` у объекта — без запросов; «bei allen …» — только у
    типа. `obj` и `back` — объект строки и ссылка
    на его форму, уже найденные экраном (один резолв); не переданы — ищем сами.

    Экран закрыт этому пользователю (право открыть — GET, модуль, пакет) — `link` None и
    причина `reason` (с `source` — ещё `screen`, чтобы причина читалась с контекстом). Записи
    нет, адрес не строится, объекта нет — ошибка в журнал, без ссылки и причины; сбой проверки
    доступа — `logger.exception`, окно без ссылки (экран не падает)."""
    if not selected or selected.get("cblock"):
        return
    from apps.core import detail_parts, detail_sections

    key = selected.get("key") or ""
    if host is None:
        # ревью 1 №6: None — не главная (её хост ""): без части, ошибка в журнал
        logger.error("window_parts: no host for the content of %r - no part", key)
        return
    module = detail_parts.module_of(detail_parts.shared_host(host))
    # M5e-2a: у страницы без модуля деталей — источники семьи (главная, листинги)
    family = "" if module else page_family(host)
    sections = (
        detail_sections.sections_for(module) if module else detail_sections.page_sources(family)
    )
    section = next((s for s in sections if s.key == key and (s.content_nav or s.source)), None)
    if section is None or selected.get("ref") != key:
        return
    if family in ("list", "catalog_list"):
        section = _list_section(section, host, request)
        if section is None:
            return
    source = section.source
    kind = detail_parts.object_kind(host)  # строка одного объекта
    if source is not None and source.object_only and not kind:
        return  # A1: у типа у этой строки своё окно
    content = {
        "summary": str(selected.get("summary") or selected.get("label") or section.label),
        "note": "",
        "woher": "",
        "woher_list": {},
        "filled": "",
        "visibility": "",
        "actions": "",
        "fixed": bool(selected.get("pinned")),
        "link": None,
        "more_links": [],
        "reason": "",
        "screen": "",
        "sourced": False,
    }
    if source is None:
        link, reason, _screen = _content_link(section, None, host, request, code, "", None, "")
        content.update(link=link, reason=reason)
        selected["content"] = content
        return
    try:
        _source_content(
            content, selected, section, host, request, code, kind, obj, back, page_label
        )
    except Exception:  # noqa: BLE001 — строка без окна «Inhalt» лучше упавшего экрана
        logger.exception("window_parts: content part of %s/%s failed - no part", host, key)
        return
    selected["content"] = content


def _list_section(section, host: str, request):
    """M5e-2a: строка листинга с именем по типу бизнеса: ★ — экран и имя её списка
    (`list_source_screen`, `site_schema.main_list_name`), «Kategorien»/«Sets & Menüs» — имя
    источника (`list_blocks.source_label`, у гастро «Menü-Pakete»). У ★ без источника части
    нет; источник есть, а экрана нет — предупреждение в журнал."""
    import dataclasses

    from apps.core import list_blocks, site_schema
    from apps.tenants import siteconfig

    tenant = getattr(request, "tenant", None)
    try:
        if section.key != siteconfig.MAIN_LIST_KEY:
            name = list_blocks.source_label(section.key, tenant)
            return dataclasses.replace(section, label=name or section.label)
        source = _list_source(host)
        if not source:
            return None
        screen = list_source_screen(source)
        if not screen:
            logger.warning(
                "window_parts: main list source %r of %s has no screen - no part", source, host
            )
            return None
        name = site_schema.main_list_name(host, tenant)
    except Exception:  # noqa: BLE001 — строка без окна «Inhalt» лучше упавшего экрана
        logger.exception("window_parts: list row %s/%s failed - no part", host, section.key)
        return None
    return dataclasses.replace(section, content_nav=screen, label=name or section.label)


def _source_content(
    content: dict,
    selected: dict,
    section,
    host: str,
    request,
    code: str,
    kind: str,
    obj,
    back,
    page_label: str,
) -> None:
    """Заполнить модель части по источнику раздела (`DetailSection.source`)."""
    from apps.core import detail_parts, site_schema

    source, key = section.source, section.key
    module = detail_parts.module_of(detail_parts.shared_host(host))
    if kind:
        if obj is not None and not site_schema.is_object_of(obj, kind, host):
            obj = back = None  # объект не от этой строки — не верим ни ему, ни ссылке
        if obj is None:
            obj = detail_parts.object_for_host(host)
            back = None
        if back is None and obj is not None:
            back = site_schema.object_back(f"{kind}@{host}", obj)
        if obj is None:
            logger.error("window_parts: no object for the content of %s/%s - no link", host, key)
    words = site_schema.object_words(host, section.only, source.kinds)
    # ревью M5d-2: сводка строки (`selected["summary"]`) здесь не годится — у строки объекта
    # это её статус («Standard: sichtbar», «nur hier ausgeblendet»)
    shows = str(source.shows or "")
    if shows:
        content["summary"] = shows % {"page": page_label} if "%(page)s" in shows else shows
    else:
        content["summary"] = str(section.label)
    content["note"] = str(source.note or "")
    content["sourced"] = True
    if kind and source.kinds and kind not in source.kinds:
        # M5d-2b: у этого вида объекта раздел не рисуется — править и скрывать здесь нечего
        if "all" not in words:
            logger.error("window_parts: no object words for %s/%s - no visibility", host, key)
            return
        content["visibility"] = _NOT_FOR_KIND % {"all": words["all"]}
        return
    tenant = getattr(request, "tenant", None)
    content["woher"], content["filled"], content["woher_list"] = _content_woher(
        source, host, key, kind, obj, words, tenant, style=_row_style(selected)
    )
    content["visibility"], content["actions"] = _content_visibility(
        selected, source, module, key, bool(kind), words, tenant
    )
    if source.kind == "field" and obj is not None and back is None:
        logger.error("window_parts: object of %s/%s has no form link - no link", host, key)
    content["link"], content["reason"], content["screen"] = _content_link(
        section, source, host, request, code, kind, back if obj is not None else None, page_label
    )
    if content["link"] is not None and source.link_text:
        content["link"]["text"] = str(source.link_text)  # M5e-2a: своё имя ссылки
    if not kind and not section.only and not source.kinds:
        content["more_links"] = _more_links(source, host, key, request)


def _row_style(selected: dict) -> str:
    """Вид блока строки — значение поля «style» её формы (тот же, что `section_row.style`
    витрины; с черновиком окна)."""
    return next(
        (
            str(f.get("value") or "")
            for f in selected.get("fields") or ()
            if isinstance(f, dict) and f.get("name") == "style"
        ),
        "",
    )


def _content_woher(
    source, host: str, key: str, kind: str, obj, words: dict, tenant=None, *, style: str = ""
) -> tuple[str, str, dict]:
    """(«Woher», «заполнено ли» у объекта, список полей). У поля — подпись поля и слово вида
    объекта; M5d-8: у раздела из нескольких полей (`SourceField`) — список (`_woher_list`),
    фраза тогда пустая."""
    from apps.core import site_schema

    only_if = str(source.only_if or "")
    if source.subject == "tenant":
        woher_list = _tenant_list(source, host, key, tenant, style)
        if woher_list:
            return "", "", woher_list
    if source.kind != "field":
        return " ".join(t for t in (str(source.woher or ""), only_if) if t), "", {}
    woher_list = _woher_list(source, host, key, kind, obj, words, tenant)
    if woher_list:
        return "", woher_list.pop("filled"), woher_list
    label = str(source.field_label or "") or site_schema.object_field_label(
        site_schema.word_kind(host), source.field
    )
    if not label or "every" not in words:
        logger.error(
            "window_parts: field source of %s/%s has no field label or object words", host, key
        )
        return str(source.woher or ""), "", {}
    if kind and "this" in words:
        base = _FIELD_THIS % {"field": label, "this": words["this"]}
        filled = _filled(obj, source.fields, host, key)
        return (f"{base} {filled}" if filled else f"{base}."), filled, {}
    woher = _FIELD_EVERY % {"field": label, "every": words["every"]}
    return " ".join(t for t in (woher, only_if) if t), "", {}


def _woher_list(source, host: str, key: str, kind: str, obj, words: dict, tenant) -> dict:
    """M5d-8: «Woher» раздела из нескольких полей — `{intro, items, after, filled}`, пункт —
    `{text, sub, icon}`. У типа — группы по вкладкам формы (у 3+ полей — `sub`, вложенный
    список), «когда появляется» — `after`; у объекта — каждое поле со словом «ausgefüllt» или
    «leer» и итог «N von M». Пункт есть, если поле видно в форме бизнеса или заполнено (§9 №6);
    пункт одного вида (`SourceField.kinds`) — только у него, у общего типа — с пометкой вида.
    Меньше двух пунктов или подписи нет — {} (прежняя фраза). Без запросов: поля объекта и
    бизнеса, пробы и гейт формы — лениво из закрытых реестров."""
    from apps.core import detail_sections

    fields = [f for f in source.fields if isinstance(f, detail_sections.SourceField)]
    is_object = bool(kind)
    if not fields or (is_object and obj is None):
        return {}
    if ("this" if is_object else "every") not in words:
        return {}
    shown = []
    for sf in fields:
        if is_object and sf.kinds and kind not in sf.kinds:
            continue
        text = _sf_text(sf, host, key, kind)
        if not text:
            return {}  # подписи нет — ошибка в журнале; прежняя фраза раздела
        state = _sf_state(obj, sf, host, key, tenant) if is_object else None
        if not state and not _form_shown(host, kind, tenant, sf, obj if is_object else None):
            continue
        if not is_object and len(sf.kinds) == 1:
            note = detail_sections.KIND_ONLY.get(sf.kinds[0], "")
            text = f"{text} {note}" if note else text
        shown.append((sf, text, state))
    if len(shown) < 2:
        return {}
    if not is_object:
        return {
            "intro": str(_LIST_EVERY % {"every": words["every"]}),
            "items": _type_items(shown),
            "after": str(source.only_if or ""),
            "filled": "",
        }
    known = [state for _sf, _text, state in shown if state is not None]
    n = sum(1 for state in known if state)
    return {
        "intro": str(_LIST_THIS % {"this": words["this"], "n": n, "m": len(known)}),
        "items": [_object_item(sf, text, state, host, key, kind) for sf, text, state in shown],
        "after": "",
        "filled": (str(_FILLED) if n else str(_EMPTY)) if known else "",
    }


def _tenant_list(source, host: str, key: str, tenant, style: str = "") -> dict:
    """M5e-2a: «Woher» из данных бизнеса (`ContentSource.subject == "tenant"`) — `{intro, items,
    after, filled}`: вводная — `source.woher`, пункт — «„X“ — ausgefüllt/leer» по пробе (гейт
    витрины), итог «N von M ausgefüllt» — в `after` (неизвестное не считается). Бизнеса нет или
    подписи нет — {} (в журнале)."""
    from apps.core import detail_sections

    fields = [f for f in source.fields if isinstance(f, detail_sections.SourceField)]
    if not fields:
        return {}
    if tenant is None:
        logger.error("window_parts: no tenant for the content of %s/%s - no list", host, key)
        return {}
    items, known = [], []
    for sf in fields:
        text = _sf_text(sf, host, key, "")
        if not text:
            return {}
        if sf.probe:
            state = _probe(sf.probe, tenant, tenant, host, key, sf.path, style=style)
        else:
            state = _sf_state(tenant, sf, host, key, tenant)
        if state is not None:
            known.append(state)
        items.append(_object_item(sf, text, state, host, key, ""))
    n = sum(1 for state in known if state)
    return {
        "intro": str(source.woher or ""),
        "items": items,
        "after": str(_N_OF_M % {"n": n, "m": len(known)}) if known else "",
        "filled": "",
    }


def _type_items(shown: list) -> list[dict]:
    """Пункты строки типа: поля одной вкладки и подраздела — одной группой («Formular, Reiter
    „…“, Abschnitt „…“:»), у 3+ полей — вложенным списком; поле без вкладки — само по себе."""
    items, groups = [], {}
    for sf, text, _state in shown:
        if not sf.tab:
            items.append({"text": text, "sub": [], "icon": ""})
            continue
        group_key = (str(sf.tab), str(sf.section or ""))
        if group_key not in groups:
            groups[group_key] = {"text": "", "sub": [], "icon": ""}
            items.append(groups[group_key])
        groups[group_key]["sub"].append(text)
    for (tab, part), group in groups.items():
        if part:
            head = str(_GROUP_SECTION % {"tab": tab, "section": part})
        else:
            head = str(_GROUP_TAB % {"tab": tab})
        if len(group["sub"]) < _NESTED_FROM:
            group["text"], group["sub"] = f"{head} {', '.join(group['sub'])}", []
        else:
            group["text"] = head
    return items


def _object_item(sf, text: str, state, host: str, key: str, kind: str) -> dict:
    """Пункт строки объекта: «„X“ — ausgefüllt» / «— leer» словом, значок — украшение;
    состояние неизвестно (ошибка в журнале) — подпись без слова и значка."""
    if state is None:
        return {"text": text, "sub": [], "icon": ""}
    icon = _ICONS[bool(state)]
    if sf.quote and sf.min_items <= 1 and not sf.args:
        word = _ITEM_FILLED if state else _ITEM_EMPTY
        return {
            "text": str(word % {"field": _sf_plain(sf, host, key, kind)}),
            "sub": [],
            "icon": icon,
        }
    # подпись-фраза («… — ab dem zweiten Foto», точка карты): слово — то же, что у раздела
    word = str(_FILLED if state else _EMPTY).rstrip(".")
    return {"text": f"{text} {word}", "sub": [], "icon": icon}


def _sf_plain(sf, host: str, key: str, kind: str) -> str:
    """Подпись поля без кавычек и добавок: `label` (словарь — по виду объекта, "" — у общего
    типа) либо подпись поля формы (`site_schema.object_field_label`); "" — подписи нет."""
    from apps.core import site_schema

    label = sf.label
    if isinstance(label, dict):
        label = label.get(kind or "", "")
    if not label and sf.field:
        label = site_schema.object_field_label(kind or site_schema.word_kind(host), sf.field)
    if not label:
        logger.error("window_parts: field %r of %s/%s has no label - no list", sf.path, host, key)
        return ""
    text = str(label)
    if sf.args:
        text = text % {name: str(value) for name, value in sf.args}
    return text


def _sf_text(sf, host: str, key: str, kind: str) -> str:
    """Подпись пункта: «„X“» (у общего типа подпись-описание из словаря — без кавычек),
    «… — ab dem zweiten Foto» у `min_items` 2, подпись-фраза (`quote=False`) — как есть."""
    from apps.core import detail_sections

    text = _sf_plain(sf, host, key, kind)
    if not text:
        return ""
    if sf.quote and not (isinstance(sf.label, dict) and not kind):
        text = str(_QUOTED % {"field": text})
    if sf.min_items > 1:
        text = str(detail_sections.FROM_SECOND_PHOTO % {"label": text})
    return text


def _form_shown(host: str, kind: str, tenant, sf, obj) -> bool:
    """Видно ли поле в форме объекта этого бизнеса (`_FORM_GATES`); вида в реестре нет или
    бизнеса нет — видно; сбой — видно (лишний пункт лучше пропавшего), ошибка в журнал."""
    import importlib

    from apps.core import site_schema

    spec = _FORM_GATES.get(kind or site_schema.word_kind(host))
    if spec is None or tenant is None:
        return True
    try:
        gate = getattr(importlib.import_module(spec[0]), spec[1])
        return bool(gate(tenant, sf.path.split(".")[0], obj))
    except Exception:  # noqa: BLE001 — окно со всеми полями лучше упавшего экрана
        logger.exception("window_parts: form gate for %r failed - field shown", sf.path)
        return True


def _probe(
    name: str, obj, tenant, host: str, key: str, path: str = "", *, style: str = ""
) -> bool | None:
    """Ревью M4: «заполнено ли» пробой из закрытого реестра `_PROBES`; незнакомое имя —
    ошибка в журнал и None («неизвестно») без импорта и вызова; сбой помощника — тоже None.
    `path` — путь пункта (у вида "field": голова — поле модели, хвост — ключи результата)."""
    import importlib

    spec = _PROBES.get(name)
    if spec is None:
        logger.error(
            "window_parts: unknown probe %r of %s/%s - filled state unknown", name, host, key
        )
        return None
    mode, module, attr = spec
    try:
        if mode == "property":
            if not isinstance(getattr(type(obj), attr, None), property):
                logger.error(
                    "window_parts: probe %r of %s/%s - %r is not a property - state unknown",
                    name,
                    host,
                    key,
                    attr,
                )
                return None
            return _has_content(getattr(obj, attr))
        helper = getattr(importlib.import_module(module), attr)
        if mode == "tenant":
            return bool(helper(obj, style))  # M5e-2a: бизнес и вид блока строки
        if mode == "object":
            return bool(helper(obj, tenant))
        head, *rest = path.split(".")
        ok, raw = _path_value(obj, head, host, key)
        if not ok:
            return None
        return _has_content(_walk(helper(raw), rest, path, host, key))
    except _Unknown:
        return None
    except Exception:  # noqa: BLE001 — окно без состояния пункта лучше упавшего экрана
        logger.exception("window_parts: probe %r of %s/%s failed - state unknown", name, host, key)
        return None


class _Unknown(Exception):
    """Ключ пути ждёт словарь, а там другое значение (уже в журнале)."""


def _walk(value, rest, path: str, host: str, key: str):
    for part in rest:
        if value is None:
            return None
        if not isinstance(value, dict):
            logger.error(
                "window_parts: %r of %s/%s - %r is not a dict - filled state unknown",
                path,
                host,
                key,
                part,
            )
            raise _Unknown
        value = value.get(part)
    return value


def _sf_state(obj, sf, host: str, key: str, tenant) -> bool | None:
    """Заполнено ли поле `sf` у объекта: проба, иначе значение пути (как `_filled`); у
    `min_items` > 1 — элементов списка не меньше (счёт как у витрины: `images|length`).
    None — неизвестно (в журнал)."""
    if sf.probe:
        return _probe(sf.probe, obj, tenant, host, key, sf.path)
    ok, value = _path_value(obj, sf.path, host, key)
    if not ok:
        return None
    if sf.min_items > 1:
        if value is None:
            return False
        if not isinstance(value, list | tuple):
            logger.error(
                "window_parts: %r of %s/%s is not a list - filled state unknown", sf.path, host, key
            )
            return None
        return len(value) >= sf.min_items
    return _has_content(value)


def _path_value(obj, path: str, host: str, key: str) -> tuple[bool, object]:
    """(прочитано ли, значение) пути `ContentSource.fields`: поле МОДЕЛИ и ключи его словаря
    через точку. Путь — не поле модели (метод, свойство, связь) или ключ ждёт словарь, а там
    другое значение — ошибка конфигурации, в журнал, (False, None)."""
    from django.core.exceptions import FieldDoesNotExist

    head, *rest = str(path).split(".")
    try:
        field = getattr(obj, "_meta", None).get_field(head)
    except (AttributeError, FieldDoesNotExist):
        field = None
    if field is None or field.is_relation:
        logger.error(
            "window_parts: %r of %s/%s is not a model field of the object - filled state unknown",
            head,
            host,
            key,
        )
        return False, None
    value = getattr(obj, field.attname)
    for part in rest:
        if value is None:
            break  # ключа нет (или поле пустое) — «leer»
        if not isinstance(value, dict):
            logger.error(
                "window_parts: %r of %s/%s - %r is not a dict - filled state unknown",
                path,
                host,
                key,
                part,
            )
            return False, None
        value = value.get(part)
    return True, value


def _has_content(value) -> bool:
    if isinstance(value, dict):
        return any(_has_content(v) for v in value.values())
    if isinstance(value, list | tuple):
        return any(_has_content(v) for v in value)
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value)


def _filled(obj, fields, host: str, key: str) -> str:
    """«— ausgefüllt.» / «— leer.» по полям объекта (`ContentSource.fields`: поле МОДЕЛИ и ключи
    его словаря через точку; хватает одного заполненного). Читаем только данные: методы и
    свойства не вызываем, по связям не ходим (запросов нет). Пусто — пустая строка, пустые
    список и словарь, None, False и 0 («0 = leer»: числовое поле с нулём — незаполненное).

    "" — сказать нечего: полей нет, объекта нет; путь — не поле модели (метод, свойство, связь)
    или ключ ждёт словарь, а там другое значение — ошибка конфигурации, в журнал."""
    if obj is None or not fields:
        return ""
    for path in fields:
        ok, value = _path_value(obj, str(path), host, key)
        if not ok:
            return ""
        if _has_content(value):
            return str(_FILLED)
    return str(_EMPTY)


def _content_visibility(
    selected: dict, source, module: str, key: str, is_object: bool, words: dict, tenant
) -> tuple[str, str]:
    """(«Auf der Seite», что можно сделать) — только из флагов и сводки строки, без запросов.
    Закреплённая строка — пусто (за неё говорит фраза «Er gehört fest…»)."""
    from apps.core import detail_parts

    if selected.get("pinned"):
        return "", ""
    enabled = bool(selected.get("enabled", True))
    can_hide = bool(selected.get("can_hide"))
    if not enabled:
        actions = str(_ACT_SHOW) if can_hide else ""
    elif can_hide and (selected.get("can_up") or selected.get("can_down")):
        actions = str(_ACT_HIDE_MOVE)
    elif can_hide:
        actions = str(_ACT_HIDE)
    else:
        actions = ""
    if key in detail_parts.food_locked(module, getattr(tenant, "business_type", None)):
        return str(_VISIBLE_LMIV), actions  # A7a: раньше сводки объекта
    if is_object and selected.get("summary"):
        return f"{selected['summary']}.", actions  # «nur hier ausgeblendet», «Standard: …»
    if not enabled:
        return str(_HIDDEN), actions
    if source.kind == "field" and "all" in words and not is_object:
        return _VISIBLE_ALL % {"all": words["all"]}, actions  # «bei allen …» — про тип
    return str(_VISIBLE), actions


def _more_links(source, host: str, key: str, request) -> list[dict]:
    """M5d-2b: ещё ссылки строки ТИПА общего хоста двух видов (`ContentSource.more_nav`) —
    `[{"label", "url"}]` по записям `nav_registry`. Экран закрыт этому пользователю — ссылки
    нет и причины нет (первая ссылка говорит сама за себя); записи нет или адрес не строится —
    ошибка в журнал."""
    from django.urls import NoReverseMatch, reverse

    from apps.core import nav_registry

    links = []
    for url_name in source.more_nav:
        entry = nav_registry.entry_by_url(url_name)
        if entry is None:
            logger.error(
                "window_parts: no nav entry %r for the content of %s/%s - no link",
                url_name,
                host,
                key,
            )
            continue
        try:
            if nav_registry.screen_closed(request, url_name):
                continue
            links.append({"label": str(entry.label), "url": reverse(entry.url_name) + entry.query})
        except NoReverseMatch:
            logger.error("window_parts: nav entry %r does not reverse - no content link", url_name)
        except Exception:  # noqa: BLE001 — окно без второй ссылки лучше упавшего экрана
            logger.exception(
                "window_parts: content link for %r failed (%s/%s) - no link", url_name, host, key
            )
    return links


def _closed_reason(closed: str, host: str, key: str) -> str:
    """Видимая причина по ответу `nav_registry.screen_closed`; кода нет в `_CLOSED_REASONS` —
    ссылки всё равно нет (экран закрыт), пустая причина — с ошибкой в журнале."""
    reason = _CLOSED_REASONS.get(closed)
    if reason is None:
        logger.error(
            "window_parts: unknown closed reason %r for %s/%s - no reason shown", closed, host, key
        )
        return ""
    return str(reason)


def _content_name(name, lang: str, foreign: bool):
    """Имя объекта или страницы в подписи ссылки: `<span lang>` — только когда язык
    содержимого не язык интерфейса."""
    from django.utils.html import format_html

    return format_html('<span lang="{}">{}</span>', lang, name) if foreign else str(name)


def _content_link(
    section, source, host: str, request, code: str, kind: str, back, page_label: str
) -> tuple[dict | None, str, str]:
    """(ссылка, причина, экран причины). Ссылка — `{"label", "url", "only_here"}`; имя объекта
    и страницы в подписи — на языке содержимого (`_content_name`, Y3)."""
    from django.conf import settings
    from django.urls import NoReverseMatch, reverse
    from django.utils import translation
    from django.utils.html import format_html

    from apps.core import content_pages, nav_registry

    mode = source.kind if source is not None else ""
    if mode == "auto":
        return None, "", ""
    key = section.key
    entry = nav_registry.entry_by_url(section.content_nav) if section.content_nav else None
    if entry is None:
        logger.error(
            "window_parts: no nav entry %r for the content of %s/%s - no link",
            section.content_nav,
            host,
            key,
        )
        return None, "", ""
    # a11y (ревью M5d-2): имя объекта и страницы — на языке содержимого; `lang` нужен, только
    # когда он не язык интерфейса (иначе читатель экрана зря переключает голос)
    lang = settings.LANGUAGE_CODE.split("-")[0]
    foreign = (translation.get_language() or lang).split("-")[0] != lang
    try:
        if source is None:
            # G2 (M5d-1): сам экран записи — прежняя проверка и прежняя подпись
            closed = nav_registry.screen_closed(request, section.content_nav)
            if closed:
                return None, _closed_reason(closed, host, key), ""
            url = reverse(entry.url_name) + entry.query
            return {"label": entry.label, "url": url, "only_here": False}, "", ""
        only_here = False
        if mode == "field" and kind:
            if back is None:
                return None, "", ""  # объекта нет — в журнале у вызывающего
            label = _content_name(back["label"], lang, foreign)
            url, only_here = back["url"], True
        elif mode == "page":
            url = content_pages.edit_url_for_code(code)
            if not url:
                logger.error(
                    "window_parts: no page editor for %r (%s/%s) - no link", code, host, key
                )
                return None, "", ""
            # имя системной страницы («Über uns», «Versand») — строка интерфейса, переведена;
            # заголовок своей страницы (`seite:<slug>`) — содержимое на языке сайта
            if page_label and foreign and host.startswith("seite:"):
                name = _content_name(page_label, lang, foreign)
                label = format_html("{} › {}", entry.label, name)
            elif page_label:
                label = f"{entry.label} › {page_label}"
            else:
                label = str(entry.label)
        else:
            url = reverse(entry.url_name) + (source.query or entry.query)
            label = f"{entry.label} › {source.sub}" if source.sub else str(entry.label)
        # A4: видимость модуля — по записи; пакет и право — по адресу цели
        closed = nav_registry.screen_closed(request, section.content_nav, target_url=url)
        if closed:
            return None, _closed_reason(closed, host, key), label
        return {"label": label, "url": url, "only_here": only_here}, "", ""
    except NoReverseMatch:
        logger.error(
            "window_parts: nav entry %r does not reverse - no content link", entry.url_name
        )
    except Exception:  # noqa: BLE001 — окно без ссылки лучше упавшего экрана
        logger.exception(
            "window_parts: content link for %r failed (%s/%s) - no link",
            section.content_nav,
            host,
            key,
        )
    return None, "", ""
