"""FB-27 R3b-2: настройки блока «Liste» в панели «Seitenaufbau» —
«Was zeigen · Welche · Wie».

Решение владельца (2026-11-11): у блока выбирают, ЧТО показать (товары, акции,
услуги…), КАКИЕ именно (правило: категория, подборка, «только со скидкой», порядок,
сколько) и КАК (сетка или лента, колонки, форма карточки).

Поля — те же, что у строки блока в Студии (`_LIST_BLOCK_FIELDS`), и проверяет их тот же
`siteconfig._clean_list_block`; здесь только состав панели. Отличие от Студии: панель
рисует сервер и показывает поля ТОЛЬКО выбранного источника — без JS-переключения.
Источник сменили → после «Übernehmen» панель перерисована под него.
"""

from __future__ import annotations

from django.utils.translation import gettext as _

#: Поля, которые панель вправе менять у блока «Liste» (остальное — `speed`, охват
#: вида — остаётся как было: запись — патч).
NAMES = (
    "source",
    "title",
    "intro",
    "type",
    "ziel",
    "endet",
    "rabatt",
    "category",
    "collection",
    "event_category",
    "country",
    "entity",
    "stars",
    "only",
    "sort",
    "limit",
    "style",
    "out",
    "cols",
    "rows",
    "card",
)


def _select(name, label, value, options, hint="") -> dict:
    """Селект панели. Значение блока, которого нет среди пунктов (категорию удалили,
    модуль выключили), остаётся отдельным выбранным пунктом — иначе браузер прислал бы
    первый пункт, и «Übernehmen» молча сменило бы выбор (W0)."""
    value = "" if value is None else str(value)
    options = [(str(v), str(lab)) for v, lab in options]
    if value and value not in {v for v, _lab in options}:
        gone = _("nicht verfügbar")
        options.append((value, f"{value} ({gone})"))
    return {
        "name": name,
        "label": str(label),
        "kind": "select",
        "value": value,
        "options": options,
        "hint": str(hint),
    }


def _line(name, label, value, kind="line") -> dict:
    return {
        "name": name,
        "label": str(label),
        "kind": kind,
        "value": "" if value is None else str(value),
        "options": [],
        "hint": "",
    }


def _only_options(source: str) -> list[tuple[str, str]]:
    labels = {
        "featured": _("Nur Empfehlungen"),
        "sale": _("Nur reduzierte"),
        "available": _("Nur verfügbare"),
        "video": _("Nur Video-Beratung"),
        "soon": _("In den nächsten 14 Tagen"),
        "text": _("Nur mit Text"),
    }
    from apps.tenants import siteconfig

    return [("", _("Alle"))] + [(k, labels.get(k, k)) for k in siteconfig.LIST_ONLY.get(source, ())]


def _which_fields(source: str, data: dict, lists: dict) -> list[dict]:
    """Фильтры «Welche» — только те, что есть у источника (реестр `LIST_SOURCES`)."""
    from apps.tenants import siteconfig

    filters = siteconfig.LIST_SOURCES[source]["filters"]
    out = []
    if "type" in filters:
        out.append(
            _select(
                "type",
                _("Aktionstyp"),
                data.get("type"),
                [("", _("Alle Aktionen")), *lists["promo_types_for_blocks"]],
            )
        )
    if "ziel" in filters and lists["promo_targets_for_blocks"]:
        out.append(
            _select(
                "ziel",
                _("Gilt für"),
                data.get("ziel"),
                [("", _("Alle")), *lists["promo_targets_for_blocks"]],
            )
        )
    if "endet" in filters:
        # «Demnächst» хранится ключом `phase`, но выбирается тем же селектом, что срок.
        out.append(
            _select(
                "endet",
                _("Zeitraum"),
                data.get("phase") or data.get("endet"),
                [
                    ("", _("Alle")),
                    ("heute", _("Endet heute")),
                    ("woche", _("Endet diese Woche")),
                    ("upcoming", _("Demnächst")),
                ],
            )
        )
    if "rabatt" in filters:
        from apps.promotions.facets import DISCOUNT_PRESETS

        out.append(
            _select(
                "rabatt",
                _("Mindestrabatt"),
                data.get("rabatt"),
                [("", _("beliebig")), *[(n, f"−{n} %") for n in DISCOUNT_PRESETS]],
            )
        )
    if "category" in filters:
        first = _("Hauptkategorien") if source == "categories" else _("Alle Kategorien")
        out.append(
            _select(
                "category",
                _("Kategorie"),
                data.get("category"),
                [("", first), *lists["list_categories_for_blocks"]],
            )
        )
    if "collection" in filters:
        mine = [
            (slug, label)
            for slug, label, srcs in lists["list_collections_for_blocks"]
            if source in srcs.split()
        ]
        if mine or data.get("collection"):
            out.append(
                _select(
                    "collection",
                    _("Sammlung"),
                    data.get("collection"),
                    [("", _("All collections")), *mine],
                )
            )
    if "event_category" in filters:
        out.append(
            _select(
                "event_category",
                _("Thema"),
                data.get("event_category"),
                [("", _("Alle Themen")), *lists["event_categories_for_blocks"]],
            )
        )
    if "country" in filters:
        out.append(
            _select(
                "country",
                _("Land"),
                data.get("country"),
                [("", _("Alle Länder")), *lists["tour_countries_for_blocks"]],
            )
        )
    if "entity" in filters:
        out.append(
            _select(
                "entity",
                _("Bewertungen zu"),
                data.get("entity"),
                [("", _("Alles")), *lists["review_kinds_for_blocks"]],
            )
        )
    if "stars" in filters:
        out.append(
            _select(
                "stars",
                _("Mindestbewertung"),
                data.get("stars"),
                [("", _("beliebig")), *[(n, f"{n} ★") for n in siteconfig.LIST_REVIEW_STARS]],
            )
        )
    if siteconfig.LIST_ONLY.get(source):
        out.append(_select("only", _("Auswahl"), data.get("only"), _only_options(source)))
    return out


#: FB-27 V2 (макет Main): способ «Welche» — три кнопки. Поля способа «Kategorie».
CATEGORY_FIELDS = frozenset({"category", "collection", "event_category", "country"})
WHICH_MODES = ("regel", "kategorie", "einzeln")

# FB-27 (макет Main): «Produkte bearbeiten → Sortiment» — экран кабинета, где правятся
# записи источника. Маршрут, которого у бизнеса нет, ссылки не даёт.
SOURCE_SCREENS = {
    "products": "catalog:product-list",
    "categories": "catalog:category-list",
    "combos": "catalog:combo-list",
    "services": "booking:services",
    "stays": "stays:units",
    "events": "events:list",
    "tours": "events:tour-list",
    "reviews": "reviews:list",
    "blog": "blog-list",
    "promotions": "promotions:promotion-list",
}


def source_link(data: dict) -> dict:
    """{source_url, source_label} для блока «Liste» либо пусто."""
    from django.urls import NoReverseMatch, reverse

    from apps.tenants import siteconfig

    source = (data or {}).get("source")
    if source not in siteconfig.LIST_SOURCES:
        source = siteconfig.LIST_SOURCE_DEFAULT
    name = SOURCE_SCREENS.get(source)
    if not name:
        return {}
    try:
        url = reverse(name)
    except NoReverseMatch:
        return {}
    label = _("%(what)s bearbeiten") % {"what": siteconfig.LIST_SOURCES[source]["label"]}
    return {"source_url": url, "source_label": label}


def which_mode(source: str, data: dict, wanted: str = "") -> tuple[str, list[dict]]:
    """Какой способ «Welche» открыт и какие способы есть у источника:
    (ключ, [{key, label, active}]). Без выбора в адресе: «Einzeln» — пока есть ручной
    состав, «Kategorie» — пока задана категория/подборка, иначе «Regel»."""
    from apps.tenants import siteconfig

    filters = set(siteconfig.LIST_SOURCES[source]["filters"])
    modes = [("regel", _("Regel"))]
    if filters & CATEGORY_FIELDS:
        modes.append(("kategorie", _("Kategorie")))
    if source in siteconfig.LIST_PICK_SOURCES:
        modes.append(("einzeln", _("Einzeln")))
    keys = [k for k, _lab in modes]
    if wanted in keys:
        mode = wanted
    elif data.get("pick") and "einzeln" in keys:
        mode = "einzeln"
    elif "kategorie" in keys and any(data.get(f) for f in CATEGORY_FIELDS):
        mode = "kategorie"
    else:
        mode = "regel"
    return mode, [{"key": k, "label": str(lab), "active": k == mode} for k, lab in modes]


def builtin_groups(request, cfg: dict, key: str, data: dict, mode: str = "") -> list[dict]:
    """Панель встроенного списка главной: те же «Welche · Wie», что у блока «Liste», без
    того, чего у секции нет — источник закреплён ключом, заголовок правится на странице,
    ручного состава и наследования вида нет (вид секции — её собственный)."""
    from apps.tenants import siteconfig

    data = {k: v for k, v in (data or {}).items() if k != "pick"}
    out = []
    for g in groups(request, cfg, data, "" if mode == "einzeln" else mode):
        if g["key"] == "was":
            continue
        g = dict(g)
        fields = [f for f in g["fields"] if f["name"] != "style"]
        if g["key"] == "welche":
            g["modes"] = [m for m in g["modes"] if m["key"] != "einzeln"]
            g["overridden"] = False
            if key not in siteconfig.GRID_SECTION_LIMITS:
                fields = [f for f in fields if f["name"] != "limit"]
            for f in fields:
                if f["name"] == "limit":
                    f["hint"] = _(
                        "Höchstens %(max)s. Sind Reihen gewählt, zählt Spalten × Reihen."
                    ) % {"max": siteconfig._SECTION_LIMIT_MAX}
        else:
            for f in fields:
                if f["name"] in ("out", "cols"):  # у секции свой вид — «как у страницы» нет
                    f["options"] = [(v, lab) for v, lab in f["options"] if v != ""]
        g["fields"] = fields
        out.append(g)
    return out


def groups(request, cfg: dict, data: dict, mode: str = "") -> list[dict]:
    """Три группы полей панели для блока «Liste»: [{key, title, fields}]. У группы
    «Welche» — ещё `mode` и `modes` (способ отбора; показываются поля только его)."""
    from apps.core import list_blocks
    from apps.core.views import _cblock_row_lists
    from apps.tenants import siteconfig

    data = data if isinstance(data, dict) else {}
    source = data.get("source")
    if source not in siteconfig.LIST_SOURCES:
        source = siteconfig.LIST_SOURCE_DEFAULT
    lists = _cblock_row_lists(request)
    hint = list_blocks.view_hint(cfg, {**data, "source": source})
    sources = list(lists["list_sources_for_blocks"])
    if source not in {k for k, _lab in sources}:
        # Модуль источника выключили: пункт остаётся, чтобы выбор не сменился молча.
        off = _("derzeit aus")
        sources.append((source, f"{siteconfig.LIST_SOURCES[source]['label']} ({off})"))

    what = [
        _select(
            "source",
            _("Was wird gezeigt"),
            source,
            sources,
            # Поля ниже рисует сервер: без подсказки смена источника выглядела бы
            # сломанной — ничего не меняется до «Übernehmen».
            hint=_("Die weiteren Felder passen sich nach „Übernehmen“ an."),
        ),
        _line("title", _("Überschrift"), data.get("title")),
        # многострочное: в однострочном поле браузер склеил бы переводы строк, и
        # «Übernehmen» без правок изменило бы текст
        _line("intro", _("Einleitung"), data.get("intro"), kind="area"),
    ]

    manual = bool(data.get("pick")) and source in siteconfig.LIST_PICK_SOURCES
    mode, modes = which_mode(source, data, mode)
    # FB-27 V2: показываются поля только открытого способа. Запись — патч: поля других
    # способов не шлются и остаются в данных (W0). В «Einzeln» полей правила нет вовсе.
    hide_rule = mode == "einzeln"
    which = [
        f
        for f in ([] if hide_rule else _which_fields(source, data, lists))
        if (f["name"] in CATEGORY_FIELDS) == (mode == "kategorie")
    ]
    sorts = [(k, lab) for k, lab, srcs in hint["sorts"] if source in srcs.split()]
    if not hide_rule and siteconfig.list_sort_keys(source) and sorts:
        stored = data.get("sort") or ""
        if stored and stored not in {k for k, _lab in sorts}:
            # Явно записанный ключ сортировки по умолчанию («newest» у товаров) — тот же
            # пункт, что пустой: пункт получает сохранённое значение, чтобы «Übernehmen»
            # без правок вернуло ровно его.
            from apps.core.facets import provider_for

            facets = siteconfig.LIST_SOURCES[source]["facets"]
            if facets and stored == provider_for(facets).default_sort:
                sorts = [(stored if k == "" else k, lab) for k, lab in sorts]
        which.append(_select("sort", _("Sortierung"), stored, sorts))
    limit = _line("limit", _("Höchstens"), data.get("limit"), kind="number")
    limit["hint"] = _("Leer = %(n)s. Höchstens %(max)s.") % {
        "n": hint["limit"],
        "max": siteconfig.LIST_LIMIT_MAX,
    }
    if not hide_rule:
        which.append(limit)

    how = []
    styles = [(k, lab) for k, lab, src in hint["styles"] if src == source]
    if styles:
        how.append(
            _select(
                "style",
                _("Display style"),
                data.get("style"),
                [("", _("Standard (grid)")), *styles],
            )
        )
    inherit = f"{hint['layout_from']}: "
    how.append(
        _select(
            "out",
            _("Ausgabe"),
            data.get("out"),
            [("", inherit + hint["mode"]), ("grid", _("Raster")), ("slider", _("Slider"))],
        )
    )
    how.append(
        _select(
            "cols",
            _("Spalten"),
            data.get("cols"),
            [("", f"{inherit}{hint['cols']}"), *[(n, n) for n in range(1, 7)]],
        )
    )
    how.append(
        _select(
            "rows",
            _("Reihen"),
            data.get("rows"),
            [("", _("automatisch")), *[(n, n) for n in range(1, 7)]],
        )
    )
    cards = [(k, lab) for k, lab, srcs in hint["cards"] if source in srcs.split()]
    if siteconfig.LIST_SOURCES[source]["card"] and cards:
        how.append(
            _select(
                "card",
                _("Kartenform"),
                data.get("card"),
                [("", f"{hint['card_from']}: {hint['card']}"), *cards],
            )
        )
    return [
        {"key": "was", "title": _("Was zeigen"), "fields": what},
        {
            "key": "welche",
            "title": _("Welche"),
            "fields": which,
            "mode": mode,
            "modes": modes,
            # ручной состав выбран, а открыт другой способ — его поля пока не действуют
            "overridden": manual and mode != "einzeln",
        },
        {"key": "wie", "title": _("Wie"), "fields": how},
    ]


def result(request, cfg: dict, data: dict) -> dict | None:
    """Что блок покажет СЕЙЧАС: {"shown", "total"}. Пустой блок на сайте не выводится
    вовсе — без этой строки владелец сохранил бы его и не нашёл на странице.
    Fail-safe: ошибка выборки = «не знаем» (None), строка в панели не рисуется."""
    from apps.core import list_blocks

    try:
        res = list_blocks.resolve_for(request, cfg, data if isinstance(data, dict) else {})
        return {"shown": len(res["items"]), "total": int(res["total"])}
    except Exception:  # noqa: BLE001
        return None


def pick_state(request, data: dict) -> dict | None:
    """FB-27 R5: ручной состав блока для панели — выбранное, предложения, строка поиска.
    None — у источника ручного выбора нет (отзывы, блог, наборы)."""
    from apps.core import list_blocks
    from apps.tenants import siteconfig

    data = data if isinstance(data, dict) else {}
    source = data.get("source")
    if source not in siteconfig.LIST_SOURCES:
        source = siteconfig.LIST_SOURCE_DEFAULT
    if source not in siteconfig.LIST_PICK_SOURCES:
        return None
    pick = siteconfig.clean_pick(data.get("pick"))
    lookup = (request.GET.get("lookup") or "").strip()[:80]
    full = len(pick) >= siteconfig.LIST_LIMIT_MAX
    try:
        entries = list_blocks.pick_entries(source, pick)
        offers = [] if full else list_blocks.pick_offers(source, lookup, exclude=pick)
    except Exception:  # noqa: BLE001 — панель не должна падать из-за выборки
        return None
    return {"entries": entries, "offers": offers, "lookup": lookup, "full": full}
