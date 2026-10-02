"""LB-1: блок «Liste» — выборка источника и действующий вид.

План — `docs/lb-list-blocks-plan-2026-10-02.md` §9 (решения владельца §8). Модуль без
разметки: тег `{% list_block %}` (siteui) зовёт `resolve`, строка редактора — `view_hint`.

Блок отвечает на два вопроса:

* **ЧТО** — источник (акции | товары) × фильтр × сортировка × лимит. Фильтры и
  сортировки берутся У ПРОВАЙДЕРА фасетов источника (`core.facets.provider_for`), а не
  заводятся заново: блок показывает ровно то, что показал бы основной список с тем же
  фильтром, и ссылка «Alle N →» ведёт туда же.
* **КАК** — сетка/лента, колонки, ряды, форма карточки. Пустая ось = «как у всех»:
  тип акции → вид страницы источника → дефолт секции главной. Своя форма у самого
  объекта (DL-19) и у его категории (STU-12j) по-прежнему сильнее блока — блок задаёт
  лишь «дефолт сайта» для своих карточек.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.core import card_forms
from apps.tenants import siteconfig

# Вид без каких-либо настроек — как у одноимённой секции главной (3 и 4 колонки).
_DEFAULTS = {
    "promotions": siteconfig.GRID_SECTION_DEFAULTS["promotions"],
    "products": siteconfig.GRID_SECTION_DEFAULTS["products"],
}


# Модуль, без которого источник не показывается: у выключенных акций нет ни страницы
# `/aktionen/`, ни карточек — блок с ними вёл бы в 404 (урок hero-плиток «Deals»).
SOURCE_MODULES = {"promotions": "promotions", "products": "catalog"}


_DEAL_MAX_COLS = 2  # «Deal» шириной меньше ~28rem нечитаем (см. effective_view)


def _source(data) -> str:
    source = (data or {}).get("source")
    return source if source in siteconfig.LIST_SOURCES else siteconfig.LIST_SOURCE_DEFAULT


def source_active(tenant, data) -> bool:
    """Включён ли у тенанта модуль источника блока (fail-closed без тенанта)."""
    if tenant is None:
        return False
    return bool(tenant.is_module_active(SOURCE_MODULES[_source(data)]))


def base_view(cfg: dict, data: dict) -> dict:
    """Вид, который блок получает, если своих осей не задал.

    Возвращает {layout, card, layout_from, card_from}; `*_from` — откуда пришло
    значение ("type" | "page" | "site" | "default"), его показывает строка редактора.
    """
    from apps.promotions import promo_types

    cfg = cfg or {}
    source = _source(data)
    site_defaults = cfg.get("site_defaults") or {}
    if source == "promotions":
        settings = {}
        if data.get("type"):
            settings = promo_types.settings_for(cfg.get("promo_groups"), data["type"])
        card, card_from = settings.get("card", ""), "type"
        if not card:
            card, card_from = site_defaults.get("promo_card", ""), "site"
        if settings.get("layout"):
            layout = siteconfig.normalize_layout(settings["layout"], _DEFAULTS[source])
            return {"layout": layout, "card": card, "layout_from": "type", "card_from": card_from}
        # Тот же путь, что у страницы акций (`_promo_output_ctx`): ось вывода страницы
        # + легаси-ключ `promo_layout`, который включает ленту (LAY-7c). Иначе блок
        # типа без своих настроек выглядел бы не так, как страница этого типа.
        page = siteconfig.optional_page_layout(cfg, "promo_index_layout")
        page = siteconfig.apply_legacy_promo_slider(page, cfg.get("promo_layout"))
        if page:
            layout = siteconfig.normalize_layout(page, _DEFAULTS[source])
            return {"layout": layout, "card": card, "layout_from": "page", "card_from": card_from}
        layout = siteconfig.normalize_layout(None, _DEFAULTS[source])
        return {"layout": layout, "card": card, "layout_from": "default", "card_from": card_from}
    card = site_defaults.get("card_style", "")
    catalog = cfg.get("catalog_layout")
    # Прайс-виды каталога (`preisliste*`) — не сетка: блок их не наследует.
    if isinstance(catalog, dict) and catalog.get("preset") in siteconfig.LAYOUT_PRESETS:
        layout = siteconfig.normalize_layout(catalog, _DEFAULTS[source])
        return {"layout": layout, "card": card, "layout_from": "page", "card_from": "site"}
    layout = siteconfig.normalize_layout(None, _DEFAULTS[source])
    return {"layout": layout, "card": card, "layout_from": "default", "card_from": "site"}


def effective_view(cfg: dict, data: dict) -> dict:
    """Действующий вид блока: база по наследованию + свои оси блока поверх."""
    base = base_view(cfg, data)
    source = _source(data)
    layout = dict(base["layout"])
    if data.get("out") == "slider":
        layout["scroll"] = True
    elif data.get("out") == "grid":
        layout.pop("scroll", None)
        layout.pop("balance", None)
    for axis in ("cols", "rows", "speed"):
        if data.get(axis):
            layout[axis] = data[axis]
    card = data.get("card") or base["card"]
    # «Deal» — строка «фото · текст · кнопка» (DL-19 N3): уже трёх колонок она
    # схлопывается до буквы (стенд LB-1). Колонки, которые блок УНАСЛЕДОВАЛ, для неё
    # ужимаются до двух, на телефоне — до одной; явный выбор владельца не трогаем.
    if card == "deal" and not layout.get("scroll"):
        if not data.get("cols") and int(layout.get("cols") or 0) > _DEAL_MAX_COLS:
            layout["cols"] = _DEAL_MAX_COLS
            layout.pop("tablet", None)
        layout["mobile"] = 1
    layout = siteconfig.normalize_layout(layout, _DEFAULTS[source])
    mode = siteconfig.output_mode(layout)
    # Сколько показать: явный «Höchstens» → свои ряды блока × колонки (только сетка:
    # у ленты «ряды» — строки в слайде) → дефолт. Наследованные ряды выдачу не режут:
    # на странице типа они значат «строк в слайде», а не «сколько показывать».
    if data.get("limit"):
        limit = data["limit"]
    elif mode == "grid" and data.get("rows"):
        limit = layout["cols"] * data["rows"]
    else:
        limit = siteconfig.LIST_LIMIT_DEFAULT
    return {
        "layout": layout,
        "grid": siteconfig.grid_class_string(layout),
        "mode": mode,
        "card": card,
        "limit": max(1, min(int(limit), siteconfig.LIST_LIMIT_MAX)),
    }


def _promotions(data: dict, limit: int):
    """Акции: тот же фильтрующий слой, что у `/aktionen/` (PromoFacets, SF-2)."""
    from apps.promotions.facets import PromoFacets
    from apps.promotions.models import Promotion
    from apps.promotions.public_views import _attach_lowest_30d

    provider = PromoFacets()
    items = (
        Promotion.objects.filter(status="active").select_related("product").order_by("-created_at")
    )
    items = provider.apply(
        items,
        {
            "gruppe": data.get("type", ""),
            "endet": data.get("endet", ""),
            "rabatt": data.get("rabatt") or 0,
        },
    )
    if data.get("sort"):
        # сортировки акций — in-memory (скидка живёт в свойствах, не в БД)
        items = provider.sort(items, data["sort"])
    shown, total = _cut(items, limit)
    # §11 PAngV: карточка со скидкой анонсирует снижение — низшая цена 30 дней рядом.
    # Блок PT-6 этого не делал, и строка на его карточках отсутствовала.
    return _attach_lowest_30d(shown), total


def _products(data: dict, limit: int):
    """Товары: тот же фильтрующий слой, что у каталога (CatalogFacets, UB2-1)."""
    from apps.catalog.facets import CatalogFacets
    from apps.catalog.models import Product
    from apps.promotions.price_layer import attach_promos

    provider = CatalogFacets()
    params = {}
    if data.get("category"):
        params["kategorie"] = data["category"]
    only = data.get("only")
    if only == "sale":
        params["sale"] = "1"
    elif only == "available":
        params["nur_verfuegbar"] = "1"
    # KAT-3: category — для SEO-адреса карточки (как секция главной и каталог).
    items = provider.apply(
        Product.objects.filter(is_active=True).select_related("category"), params
    )
    if only == "featured":
        items = items.filter(is_featured=True)
    sort = data.get("sort") or provider.default_sort
    if sort == "featured":
        # порядок секции товаров главной: избранные вперёд, затем новые
        items = items.order_by("-is_featured", "-created_at")
    else:
        items = provider.sort(items, sort)
    shown, total = _cut(items, limit)
    if shown:
        # рейтинг ★ и промо-цена — по одному bulk-запросу, как в каталоге
        from apps.reviews import services as review_services

        rating = review_services.bulk_summary("product", [p.pk for p in shown])
        for p in shown:
            row = rating.get(p.pk)
            p.review_avg = row["avg"] if row else None
            p.review_count = row["count"] if row else 0
        attach_promos(shown)
    return shown, total


def _cut(items, limit: int):
    """Первые `limit` и сколько всего; COUNT — только когда показаны не все."""
    if isinstance(items, list):
        return items[:limit], len(items)
    shown = list(items[: limit + 1])
    if len(shown) <= limit:
        return shown, len(shown)
    return shown[:limit], items.count()


def _all_url(data: dict) -> str:
    """Где виден ВЕСЬ список с тем же фильтром (решение N-4: тип → страница типа)."""
    source = _source(data)
    params = {}
    if source == "promotions":
        for key, param in (("type", "gruppe"), ("endet", "endet"), ("rabatt", "rabatt")):
            if data.get(key):
                params[param] = data[key]
        if data.get("sort"):
            params["sort"] = data["sort"]
        base = reverse("storefront-aktionen")
    else:
        base = (
            reverse("storefront-category", args=[data["category"]])
            if data.get("category")
            else reverse("storefront-products")
        )
        only = data.get("only")
        if only == "sale":
            params["sale"] = "1"
        elif only == "available":
            params["nur_verfuegbar"] = "1"
        # «featured» у каталога своего параметра нет; «newest» — его порядок по умолчанию
        if data.get("sort") in ("price_asc", "price_desc"):
            params["sort"] = data["sort"]
    return base + ("?" + urlencode(params) if params else "")


def _label(data: dict, items) -> str:
    """Заголовок: свой у блока, иначе по выборке (тип, фильтр, категория)."""
    if data.get("title"):
        return data["title"]
    if _source(data) == "promotions":
        if data.get("type"):
            from apps.promotions import promo_types

            own = {p.group: p.group_localized for p in items if p.group}
            return promo_types.label_for(data["type"], own)
        if data.get("endet") == "heute":
            return _("Endet heute")
        if data.get("endet") == "woche":
            return _("Endet diese Woche")
        return _("Aktionen")
    if data.get("category") and items:
        cat = getattr(items[0], "category", None)
        if cat is not None and getattr(cat, "slug", "") == data["category"]:
            return str(cat)
        parent = getattr(cat, "parent", None) if cat is not None else None
        if parent is not None and getattr(parent, "slug", "") == data["category"]:
            return str(parent)
    only = data.get("only")
    if only == "featured" or data.get("sort") == "featured":
        return _("Empfehlungen")
    if only == "sale":
        return _("Reduziert")
    if only == "available":
        return _("Sofort verfügbar")
    if data.get("sort") == "newest":
        return _("Neu im Sortiment")
    return _("Produkte")


def resolve(cfg: dict, data: dict) -> dict:
    """Всё, что нужно разметке блока: карточки + вид + заголовок + «Alle N →»."""
    data = data or {}
    source = _source(data)
    view = effective_view(cfg, data)
    if source == "products":
        items, total = _products(data, view["limit"])
    else:
        items, total = _promotions(data, view["limit"])
    return {
        "source": source,
        "items": items,
        "total": total,
        "more": total > len(items),
        "url": _all_url(data),
        "label": _label(data, items),
        "intro": data.get("intro", ""),
        "type": data.get("type", "") if source == "promotions" else "",
        # у блока ОДНОГО типа метка типа на карточке — шум (все одинаковые); у
        # смешанной выдачи она говорит, откуда акция (как в результатах, N-2)
        "in_group": bool(data.get("type")),
        **{k: view[k] for k in ("layout", "grid", "mode", "card")},
    }


_FROM_LABELS = {
    "type": gettext_lazy("wie der Typ"),
    "page": gettext_lazy("wie die Seite"),
    "site": gettext_lazy("wie die Website"),
    "default": gettext_lazy("Standard"),
}


def view_hint(cfg: dict, data: dict) -> dict:
    """Всё, что нужно строке редактора: подписи «пустых» пунктов вида (ОТКУДА придёт
    значение и какое) и наборы пунктов с отметкой источника.

    Без подписи «пусто» читалось бы как «ничего», хотя блок показывает вид своего
    типа или страницы — владелец не видел бы, что именно он наследует.
    """
    from apps.promotions.facets import DISCOUNT_PRESETS

    base = base_view(cfg, data)
    layout = base["layout"]
    source = _source(data)
    kind = siteconfig.LIST_SOURCES[source]["card"]
    mode_key = siteconfig.output_mode(layout)
    return {
        "layout_from": str(_FROM_LABELS[base["layout_from"]]),
        "card_from": str(_FROM_LABELS[base["card_from"]]),
        "mode_key": mode_key,
        "mode": _("Slider") if mode_key == "slider" else _("Raster"),
        "cols": layout["cols"],
        "rows": layout.get("rows") or "",
        "card": str(card_forms.label_for(base["card"], kind) or _("Standard")),
        "limit": siteconfig.LIST_LIMIT_DEFAULT,
        "discounts": DISCOUNT_PRESETS,
        "sorts": sort_options(),
        "cards": card_options(),
    }


def sort_options() -> list[tuple[str, str, str]]:
    """[(ключ, подпись, источники)] сортировок — подписи у провайдеров фасетов, те же,
    что видит посетитель на витрине. Сортировка провайдера по умолчанию = пустой ключ."""
    from apps.core.facets import provider_for

    merged: dict[str, list] = {}
    for source, spec in siteconfig.LIST_SOURCES.items():
        provider = provider_for(spec["facets"])
        options = list(provider.sort_options())
        if source == "products":
            options.insert(1, ("featured", _("Empfohlene zuerst")))
        for key, label in options:
            key = "" if key == provider.default_sort else key
            row = merged.setdefault(key, [str(label), []])
            row[1].append(source)
    return [(key, label, " ".join(srcs)) for key, (label, srcs) in merged.items()]


def card_options() -> list[tuple[str, str, str]]:
    """[(ключ, подпись, источники)] форм карточки — реестр `core.card_forms` (DL-19)."""
    out = []
    for key, label, _hint, kinds in card_forms.CARD_FORMS:
        if not key:
            continue
        srcs = [s for s, spec in siteconfig.LIST_SOURCES.items() if spec["card"] in kinds]
        if srcs:
            out.append((key, str(label), " ".join(srcs)))
    return out


# ─────────────────── LB-1b: пилюля охвата «Den ganzen Typ» ───────────────────
#
# План — `docs/lb-list-blocks-plan-2026-10-02.md` §10. Хранение не новое: тот же
# `promo_groups[тип].layout/card`, что пишут экран «Aktionstypen» и страница типа.

_VIEW_AXES = ("out", "cols", "rows", "speed", "card")
_LAYOUT_AXES = ("out", "cols", "rows", "speed")


def _list_blocks_of(cfg: dict) -> list[dict]:
    """Блоки «Liste» конфига в порядке обхода: главная, затем страницы."""
    found: list = []
    sections = cfg.get("sections")
    if isinstance(sections, list):
        found.extend(sections)
    pages = cfg.get("page_blocks")
    if isinstance(pages, dict):
        for rows in pages.values():
            if isinstance(rows, list):
                found.extend(rows)
    return [
        item
        for item in found
        if isinstance(item, dict)
        and siteconfig.cblock_type(item.get("key")) == "list"
        and isinstance(item.get("data"), dict)
    ]


def _axis_int(raw, low: int, high: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    return value if low <= value <= high else 0


def _type_layout(cfg: dict, data: dict) -> dict:
    """Раскладка типа из осей блока; {} — у типа своей раскладки нет.

    Слой раскладки у типа «всё или ничего»: `base_view` берёт раскладку типа ЦЕЛИКОМ
    и страницу уже не читает. Поэтому основа — действующая раскладка СТРАНИЦЫ, а оси
    блока ложатся поверх: пустое «Spalten» с подписью «wie die Seite: 4» обязано дать
    4, а не дефолт нормализации, и «Raster» поверх ленты страницы — сетку.
    """
    if not any(data.get(axis) for axis in _LAYOUT_AXES):
        return {}
    layout = dict(base_view(cfg, {"source": "promotions"})["layout"])
    if data.get("out") == "slider":
        layout["scroll"] = True
    elif data.get("out") == "grid":
        layout.pop("scroll", None)
        layout.pop("balance", None)
    cols = _axis_int(data.get("cols"), 1, 6)
    if cols:
        # как экран «Aktionstypen» (`promo_type_save`) — одно хранение, одна форма
        layout["preset"] = f"cols{cols}"
        layout["cols"] = cols
    for axis, low, high in (("rows", 1, 6), ("speed", 3, 15)):
        value = _axis_int(data.get(axis), low, high)
        if value:
            layout[axis] = value
    return layout


def apply_type_scope(cfg: dict) -> None:
    """LB-1b: блоки в режиме «Den ganzen Typ» отдают свой вид ТИПУ акции.

    Одна функция для Save билдера и для живого черновика — превью показывает ровно то,
    что сохранится. Для блока `list` с `scope="type"`, источником «Aktionen» и типом:
    оси вида уходят в `promo_groups[тип]` (пустые — тип снова наследует страницу), а у
    блока очищаются — он следует за типом, как все блоки этого типа. Шаблон страницы
    типа (`style`) и чужие типы не трогаются. `scope` — служебное поле формы и в
    конфиге не остаётся ни у одного блока. Два блока одного типа в этом режиме —
    побеждает последний по порядку обхода (главная, затем страницы).
    """
    if not isinstance(cfg, dict):
        return
    from apps.promotions import promo_types

    types = None
    for item in _list_blocks_of(cfg):
        data = item["data"]
        if data.pop("scope", None) != "type":
            continue
        kind = str(data.get("type") or "").strip()
        if _source(data) != "promotions" or not kind:
            continue
        if types is None:
            raw = cfg.get("promo_groups")
            types = dict(raw) if isinstance(raw, dict) else {}
        entry = dict(promo_types.settings_for(types, kind))
        layout = _type_layout(cfg, data)
        if layout:
            entry["layout"] = layout
        else:
            entry.pop("layout", None)
        card = str(data.get("card") or "").strip()
        if card and card in card_forms.keys_for(card_forms.PROMO):
            entry["card"] = card
        else:
            entry.pop("card", None)
        types[kind] = entry
        for axis in _VIEW_AXES:
            data.pop(axis, None)
    if types is not None:
        cfg["promo_groups"] = types


def type_views(cfg: dict, keys=()) -> dict:
    """LB-1b: карта для пилюли охвата в строке редактора (один JSON на страницу).

    `types` — что покажут контролы вида в режиме «Den ganzen Typ» (значения самого
    типа, пусто = тип наследует); `page` — подписи пустых пунктов в этом режиме: тип
    без своей оси берёт её у страницы акций.
    """
    from apps.promotions import promo_types

    cfg = cfg or {}
    per_type = cfg.get("promo_groups") if isinstance(cfg.get("promo_groups"), dict) else {}
    names = [*keys, *per_type, *(b["data"].get("type") for b in _list_blocks_of(cfg))]
    types: dict = {}
    for key in dict.fromkeys(str(k or "").strip() for k in names):
        if not key:
            continue
        settings = promo_types.settings_for(per_type, key)
        layout = settings.get("layout") or {}
        types[key] = {
            "out": ("slider" if layout.get("scroll") else "grid") if layout else "",
            "cols": str(layout.get("cols") or "") if layout else "",
            "rows": str(layout.get("rows") or ""),
            "speed": str(layout.get("speed") or ""),
            "card": settings.get("card", ""),
        }
    page = view_hint(cfg, {"source": "promotions"})
    return {
        "types": types,
        "page": {
            "out": f"{page['layout_from']}: {page['mode']}",
            "cols": f"{page['layout_from']}: {page['cols']}",
            "rows": (
                f"{page['layout_from']}: {page['rows']}" if page["rows"] else _("automatisch")
            ),
            "card": f"{page['card_from']}: {page['card']}",
            "mode": page["mode_key"],
        },
    }


def editor_options(data: dict, live_types=None, categories=None) -> dict:
    """Пункты селекторов строки, которых нет в живых списках (класс W0).

    Селектор типа строится из ЖИВЫХ типов, категорий — из активных. Без своего пункта
    значение блока не было бы выбрано, браузер отправил бы первый пункт («Alle»), и
    Save молча превратил бы блок «Räumung» в блок «все акции». Плюс подпись типа для
    пилюли охвата.
    """
    from apps.promotions import promo_types

    data = data if isinstance(data, dict) else {}
    out: dict = {}
    kind = str(data.get("type") or "")
    if kind:
        label = dict(live_types or []).get(kind)
        if label is None:
            # gettext — вне f-строки: xgettext выражения f-строк не извлекает (I18N-13)
            empty = _("derzeit leer")
            label = f"{promo_types.label_for(kind)} ({empty})"
            out["orphan_type"] = (kind, label)
        out["type_label"] = label
    category = str(data.get("category") or "")
    if category and category not in {slug for slug, _label in (categories or [])}:
        gone = _("nicht verfügbar")
        out["orphan_category"] = (category, f"{category} ({gone})")
    return out
