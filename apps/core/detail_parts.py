"""FB-31 P5: детальная страница — разделы и свои блоки одной схемой
(`docs/fb31-p5-detail-plan-2026-11-16.md`).

Порядок и видимость разделов остаются там, где были (`<module>_detail.order/hidden`, Студия и
«Seitenaufbau» пишут их одним писателем). Строки разделов в `page_blocks[<host>]` (`{"key":
"<раздел>"}` без id) — только ЯКОРЯ: свой блок, стоящий после строки раздела, рисуется сразу
после этого раздела. Блоки после последней строки раздела — хвост на прежнем месте (решение
владельца: «после последнего раздела — как сейчас»). Строк разделов нет — все блоки в хвосте,
страница байт-в-байт прежняя.

Модуль чистый (без БД).
"""

from __future__ import annotations

import logging
import re

from apps.core import detail_sections

logger = logging.getLogger(__name__)

#: хост блоков детали → модуль реестра разделов (R3a: события и туры — цикл разделов;
#: услуга, товар, номер — следующими срезами)
SECTION_HOSTS = {
    "event_detail": "events",
    "service_detail": "booking",
    # товар и номер: разделы в двух полосах страницы — порядок постоянный (решение владельца)
    "product_detail": "catalog",
    "stay_detail": "stays",
    # FB-32 S4: корзина — один раздел «Passt gut dazu»
    "cart": "cart",
    # FB-32 S6a: «Über uns» (своя страница «Seite» — по префиксу хоста, `PAGE_PREFIX`)
    "info": "info",
    # FB-32 S6b
    "versand": "versand",
    # FB-32 S6c
    "message": "message",
    "anfrage": "anfrage",
    # FB-32 S6d
    "gift": "gift",
    "loyalty": "loyalty",
    # FB-32 S6e
    "blog_post": "blog_post",
    "finder": "finder",
    # FB-32 S6f
    "promo_detail": "promo",
    # FB-32 S6g-1
    "teachers": "teachers",
    "event_calendar": "event_calendar",
    "passes": "passes",
    # FB-32 S6g-2
    "booking_slots": "booking_slots",
    # FB-32 S6g-3
    "combo_detail": "combo",
}
#: FB-32 S6a: хосты своих страниц «Seite» (`seite:<slug>`) — модуль разделов «page»
PAGE_PREFIX = "seite:"
#: тот же вид хоста, что принимает нормализация (`siteconfig._CONTENT_PAGE_HOST_RE`) — иначе
#: черновик со строками раздела у кривого хоста принимался бы, но не сохранялся (ревью S6a)
_PAGE_HOST_RE = re.compile(r"^seite:[a-z0-9]+(?:-[a-z0-9]+)*$")
#: FB-32 S6a: модули страниц без покупки и с постоянным порядком разделов
#: страницы, где своя «Buchung»-строка не нужна (покупка ваучера — сама строка «form»)
_FORM_PAGES = frozenset(
    {
        "message",
        "anfrage",
        "gift",
        "loyalty",
        "blog_post",
        "finder",
        "teachers",
        "event_calendar",
        "passes",
        "booking_slots",
    }
)
NO_KAUF_MODULES = frozenset({"cart", "info", "page", "versand", "promo", "combo"}) | _FORM_PAGES
FIXED_ORDER_MODULES = frozenset({"info", "page", "versand", "promo", "combo"}) | _FORM_PAGES
#: FB-32 S6f: разделы, которые одновременно строки осей (P3): хранят свой вид (`style`), а
#: «поставлено» (`anchors.placed`) по ним не считается — старые `[offer(style), блоки]`
#: рисуются прежней разметкой (все блоки в хвосте)
AXIS_SECTIONS = {"promo_detail": frozenset({"offer"})}
#: FB-32 S6a: видимость раздела — прежний ключ конфига (False = скрыт), а не `<module>_detail`
VISIBILITY_KEYS = {
    "cart": {"upsell": "cart_show_upsell"},
    "info": {"contact": "about_contact"},
    "blog_post": {"more": "blog_show_more"},
    # FB-33 M2g: «Teilen» и визитка — внутри колонки «Angebot», скрываются на месте
    "promo": {
        "share": "promo_show_share",
        "card": "promo_show_card",
        "related": "promo_show_related",
    },
    "combo": {
        "reviews": "combo_show_reviews",
        "examples": "combo_show_examples",
        "cta": "combo_show_cta",
        "related": "combo_show_related",
    },
}
#: разделы первого экрана (рядом с покупкой): скрыть можно, блоки рядом с ними — перед телом
FIRST_SCREEN = {
    "product_detail": (
        "description",
        "info",
        # FB-33 M2f: колонка рядом с покупкой
        "sizes",
        "trust",
        "anprobe",
        "waitlist",
        "instore",
        "question",
    ),
    "stay_detail": ("description", "amenities"),
}
#: хосты с постоянным порядком разделов: строки разделов только скрываются
FIXED_ORDER = frozenset(FIRST_SCREEN)
#: раздел тела, после которого стоят «средние» блоки (дальше — широкая полоса «Ähnliche»)
BODY_LAST = {"product_detail": "reviews", "stay_detail": "reviews"}
#: FB-33 M2f: блоки между «Ähnliche» и «Zuletzt angesehen» (широкая полоса)
WIDE_LAST = {"product_detail": "related"}
#: FB-33 M2f (LMIV, решение владельца): раздел, который у еды скрыть нельзя
FOOD_LOCKED = {"catalog": frozenset({"info"})}
KAUF_KEY = "kauf"
KAUF_REF = "__kauf"  # строка схемы «Buchung» (не хранится)
#: где страница рисует покупку: у услуги — в первом экране, над разделами; у события — после
KAUF_FIRST = frozenset({"service_detail", "product_detail", "stay_detail"})
#: FB-32 S4: страницы с разделами, но без покупки (строки «Buchung» в схеме нет)


#: FB-31 P5 R8: вид объекта → общий хост его детали (у тура — страница событий)
OBJECT_SHARED = {
    "product": "product_detail",
    "service": "service_detail",
    "stay": "stay_detail",
    "event": "event_detail",
    "tour": "event_detail",
}


def module_of(host: str) -> str:
    """Модуль разделов ОБЩЕГО хоста детали (писатель порядка/видимости — только у него)."""
    if isinstance(host, str) and _PAGE_HOST_RE.match(host):
        return "page"
    return SECTION_HOSTS.get(host, "")


def has_kauf(host: str) -> bool:
    """Есть ли у страницы с разделами строка покупки «Buchung»/«Kaufen»."""
    module = module_of(shared_host(host or ""))
    return bool(module) and module not in NO_KAUF_MODULES


def fixed_order(host: str) -> bool:
    """Порядок разделов постоянный — строки разделов только скрываются (не двигаются)."""
    return shared_host(host) in FIXED_ORDER or module_of(host) in FIXED_ORDER_MODULES


def hideable(host: str, key: str, business_type: str | None = None) -> bool:
    """Можно ли скрыть раздел (у текста своей страницы — нельзя; у еды «Zutaten/Allergene» —
    нельзя: LMIV, FB-33 M2f). `business_type` — по умолчанию тип текущего сайта."""
    module = module_of(shared_host(host or ""))
    if key in FOOD_LOCKED.get(module, ()) and is_food(business_type):
        return False
    return next((s.hideable for s in detail_sections.sections_for(module) if s.key == key), True)


def is_food(business_type: str | None = None) -> bool:
    from apps.core.archetypes import FOOD_BUSINESS_TYPES

    if business_type is None:
        from django.db import connection

        business_type = getattr(getattr(connection, "tenant", None), "business_type", "")
    return business_type in FOOD_BUSINESS_TYPES


def food_locked(module: str, business_type: str | None) -> frozenset:
    """Разделы, которые у этого сайта показываются всегда (LMIV у еды)."""
    return FOOD_LOCKED.get(module, frozenset()) if is_food(business_type) else frozenset()


def object_kind(host) -> str:
    """R8: вид объекта по хосту его своих блоков (`<kind>:<hex>`), иначе ""."""
    if not isinstance(host, str) or ":" not in host:
        return ""
    kind = host.split(":", 1)[0]
    return kind if kind in OBJECT_SHARED else ""


def shared_host(host: str) -> str:
    """Общий хост детали для хоста объекта (сам хост — если он общий)."""
    return OBJECT_SHARED.get(object_kind(host), host)


def section_keys(host: str) -> tuple[str, ...]:
    """Разделы страницы: общего хоста детали и (R8) хоста одного объекта."""
    module = module_of(shared_host(host))
    return detail_sections.section_keys(module) if module else ()


def flow_section_keys(host: str) -> tuple[str, ...]:
    """FB-33 M2g: разделы страницы, которые двигаются и служат якорями (без разделов «на
    месте» — те только скрываются, страница рисует их там, где они были)."""
    module = module_of(shared_host(host))
    return detail_sections.flow_keys(module) if module else ()


def in_place_keys(host: str) -> tuple[str, ...]:
    """FB-33 M2g: разделы «на месте» страницы — в порядке реестра; у хоста объекта — только
    разделы его вида (у события нет приватного выезда, у тура — групп и серии)."""
    module = module_of(shared_host(host or ""))
    if not module:
        return ()
    keys = detail_sections.in_place_keys(module)
    kind = object_kind(host or "")
    return tuple(
        s.key
        for s in detail_sections.sections_for(module)
        if s.key in keys and (not kind or not s.only or s.only == kind)
    )


#: FB-33 M2g: строки «на месте» в схеме — сразу после этого раздела (иначе — после всех)
IN_PLACE_AFTER = {"promo_detail": "offer"}


def anchor_keys(host: str) -> frozenset:
    """Разделы, чьи голые строки — только якоря позиции (без строк осей, FB-32 S6f, и без
    разделов «на месте», FB-33 M2g)."""
    return frozenset(flow_section_keys(host)) - AXIS_SECTIONS.get(
        shared_host(host or ""), frozenset()
    )


def strip_in_place(host: str, rows) -> list:
    """FB-33 M2g: строки разделов «на месте» не хранятся в `page_blocks` (их место постоянно)."""
    keys = set(detail_sections.in_place_keys(module_of(shared_host(host or ""))))
    return [r for r in rows if not (r.get("key") in keys and not r.get("id"))]


def anchors(rows, host: str, order: list[str] | None = None) -> dict:
    """{"placed": bool, "lead": [id], "after": {раздел: [id]}, "tail": [id]} — где стоят свои
    блоки относительно разделов. Скрытые/мусорные строки не мешают: якорь — порядок строк.
    FB-33 M2g: строки разделов «на месте» — не якоря (блок после них — у соседнего раздела)."""
    keys = set(flow_section_keys(host))
    pure = anchor_keys(host)
    rows = [r for r in (rows if isinstance(rows, list) else []) if isinstance(r, dict)]
    placed = any(r.get("key") in pure and not r.get("id") for r in rows)
    out = {"placed": placed, "lead": [], "after": {}, "tail": []}
    if not placed:
        out["tail"] = [r["id"] for r in rows if r.get("id")]
        return out
    current, last = None, None
    for r in rows:
        if r.get("key") in keys and not r.get("id"):
            current = last = r["key"]
        elif r.get("id"):
            if current is None:
                out["lead"].append(r["id"])
            else:
                out["after"].setdefault(current, []).append(r["id"])
    # после последнего раздела (в ТЕКУЩЕМ порядке, ревью P5) — прежнее место, хвост страницы.
    # FB-33 M2f: у постоянного порядка — после последнего раздела, который ЕСТЬ в строках
    # (строки, сохранённые до нового раздела в конце, держат хвост там же)
    tail_key = (
        last if shared_host(host or "") in WIDE_LAST and last else (order[-1] if order else last)
    )
    out["tail"] = out["after"].pop(tail_key, []) if tail_key else []
    return out


def flow(
    rows, host: str, order: list[str], all_order: list[str] | None = None, own: dict | None = None
) -> list[dict]:
    """Поток тела: [{"section": k} | {"part": "ids:…", "host"?: хост}] — видимые разделы в
    `order`, свои блоки между ними. `all_order` — полный порядок (со скрытыми): блоки скрытого
    раздела остаются на его месте. `own` (R8) — якоря своих блоков объекта (`own_anchors`):
    у раздела сначала общие блоки, потом свои. Пустой список — рисовать прежней разметкой."""
    seq = all_order or order
    a = anchors(rows, host, seq)
    if not a["placed"] and not own:
        return []
    shared = a if a["placed"] else {"lead": [], "after": {}}
    visible = set(order)
    items: list[dict] = []

    def put(ids, target=None):
        if ids:
            items.append({"part": ids_part(ids), **({"host": target} if target else {})})

    put(shared["lead"])
    put((own or {}).get("lead"), (own or {}).get("host"))
    for key in seq:
        if key in visible:
            items.append({"section": key})
        put(shared["after"].get(key))
        put(((own or {}).get("after") or {}).get(key), (own or {}).get("host"))
    return items


def own_anchors(config, kind: str, obj, order: list[str]) -> dict | None:
    """R8: якоря своих блоков объекта ({"host", "lead", "after", "tail"}) — None, если строк
    разделов у объекта нет (свои блоки одним куском, как раньше: `object_blocks`)."""
    from apps.core import object_structure
    from apps.tenants import siteconfig

    host = object_structure.object_host(kind, obj)
    if not host or kind not in OBJECT_SHARED:
        return None
    # ревью R8: всегда по НОРМАЛИЗОВАННОМУ конфигу — вьюха и тег хвоста видят одни якоря
    # (сырой черновик хранит якоря, которые нормализация уплотняет)
    raw = (siteconfig.normalize(config).get("page_blocks") or {}).get(host)
    rows = [r for r in (raw if isinstance(raw, list) else []) if isinstance(r, dict)]
    a = anchors(rows, host, order)
    return {"host": host, **a} if a["placed"] else None


def object_order(config, kind: str, obj) -> list[str]:
    """R8: полный порядок разделов страницы объекта (со скрытыми) — у товара и номера
    постоянный, у прочих — свой порядок объекта поверх общего."""
    from apps.core import object_structure

    host = OBJECT_SHARED.get(kind, "")
    if host in FIXED_ORDER:
        return list(flow_section_keys(host))
    return object_structure.effective_full_order(config, module_of(host), obj)


def tail_part(rows, host: str, order: list[str] | None = None) -> str:
    """`part` для тега блоков на прежнем месте хвоста ("after" — как раньше, все блоки)."""
    a = anchors(rows, host, order)
    return ids_part(a["tail"]) if a["placed"] else "after"


def ids_part(ids) -> str:
    return "ids:" + ",".join(ids)


def full_order(config, module: str) -> list[str]:
    """Полный порядок разделов (со скрытыми): сохранённый + остальные по реестру. FB-33 M2g:
    без разделов «на месте» (они не двигаются)."""
    from apps.tenants import siteconfig

    keys = detail_sections.flow_keys(module)
    raw = (config or {}).get(siteconfig.detail_section_config_key(module))
    saved = siteconfig.normalize_detail_sections(raw, module).get("order", [])
    saved = [k for k in saved if k in keys]
    return saved + [k for k in keys if k not in saved]


# ───────── «Seitenaufbau»: строки разделов вперемешку со своими блоками ─────────


def edit_rows(config, host: str, rows, order=None, hidden=None) -> list[dict]:
    """Строки схемы детали для правки: свои блоки до разделов, каждый раздел (полный порядок,
    `enabled` — из скрытых) со своими блоками после него, хвост. Порядок разделов — из
    `<module>_detail.order`, видимость — из `hidden`: строки лишь показывают их на время правки.
    R8: `order`/`hidden` — порядок и скрытые одного объекта (`object_edit_rows`)."""
    from apps.tenants import siteconfig

    base = shared_host(host)
    module = module_of(base)
    full = order if order is not None else full_order(config, module)
    if hidden is None:
        hidden = siteconfig.detail_section_hidden(config, module)
    rows = [r for r in (rows if isinstance(rows, list) else []) if isinstance(r, dict)]
    a = anchors(rows, host, full)
    by_id = {r["id"]: r for r in rows if r.get("id")}
    first = FIRST_SCREEN.get(base, ())
    # блоки до первого раздела — первыми (так их рисует и страница: `fixed_parts`, ревью P5)
    seq = [by_id[i] for i in a["lead"] if i in by_id]
    for key in first:  # первый экран — над блоками «до отзывов» (так рисует страница)
        seq.append({"key": key, "enabled": key not in hidden})
        seq += [by_id[i] for i in a["after"].get(key, []) if i in by_id]
    axis = AXIS_SECTIONS.get(base, frozenset())
    # FB-33 M2g: строки «на месте» — сразу после своего раздела или после всех разделов
    places = [{"key": k, "enabled": k not in hidden} for k in in_place_keys(host)]
    after = IN_PLACE_AFTER.get(base)
    for key in full:
        if key in first:
            continue
        if key in axis:
            # FB-32 S6f: строка оси (вид «Angebot») — со своими полями, всегда видна
            stored = next((r for r in rows if r.get("key") == key and not r.get("id")), {})
            seq.append({**stored, "key": key, "enabled": True})
        else:
            seq.append({"key": key, "enabled": key not in hidden})
        if key == after:
            seq += places
            places = []
        seq += [by_id[i] for i in a["after"].get(key, []) if i in by_id]
    seq += places
    seq += [by_id[i] for i in a["tail"] if i in by_id]
    return seq


# ───────── R8: своя схема одного объекта ─────────


def object_for_host(host: str):
    """Объект хоста своих блоков (`<kind>:<hex>`) либо None (нет такого, чужой вид)."""
    kind = object_kind(host)
    if not kind:
        return None
    from apps.core import site_schema

    return site_schema._object_for(f"{kind}@{host}")


def object_edit_rows(config, host: str, rows) -> list[dict]:
    """Строки схемы ОДНОГО объекта: его разделы (свой порядок и видимость «nur hier») и
    свои блоки между ними. Объекта нет — прежний плоский список своих блоков."""
    from apps.core import object_structure

    obj = object_for_host(host)
    if obj is None:
        return [r for r in (rows if isinstance(rows, list) else []) if isinstance(r, dict)]
    kind = object_kind(host)
    module = module_of(OBJECT_SHARED[kind])
    order = object_order(config, kind, obj)
    hidden = object_structure.effective_hidden(config, module, obj)
    return edit_rows(config, host, rows, order, hidden)


def object_lift(
    config: dict, host: str, items: list[dict], obj=None
) -> tuple[list[dict], dict | None]:
    """Обратно из строк схемы объекта: (строки для `page_blocks[host]` — якоря и свои блоки,
    пусто, если своих блоков нет; состояние разделов {hidden, shown, order} для
    `page_override` объекта либо None — строк разделов нет, ничего не менять)."""
    from apps.core import object_structure
    from apps.tenants import siteconfig

    if obj is None:  # ревью R8: `commit` передаёт объект, заблокированный в транзакции
        obj = object_for_host(host)
    keys = set(section_keys(host))
    flow_keys = set(flow_section_keys(host))
    order = [r["key"] for r in items if r.get("key") in flow_keys and not r.get("id")]
    if obj is None or not order:
        return items, None  # старый черновик (до R8) — разделы объекта не трогаем
    module = module_of(OBJECT_SHARED[object_kind(host)])
    enabled = {
        r["key"]: r.get("enabled", True) is not False
        for r in items
        if r.get("key") in keys and not r.get("id")
    }
    prev = object_structure.clean(object_structure._raw(obj), module)
    shared_hidden = siteconfig.detail_section_hidden(config, module)
    was_hidden = (shared_hidden - set(prev.get("shown", []))) | set(prev.get("hidden", []))
    hidden, shown = [], []
    present = order + [k for k in in_place_keys(host) if k in enabled]
    for key in present:
        visible = enabled[key]
        if visible == (key not in was_hidden):
            # не трогали — прежний выбор объекта как был (явное «показать» не теряется)
            if key in prev.get("hidden", []):
                hidden.append(key)
            elif key in prev.get("shown", []):
                shown.append(key)
        elif visible and key in shared_hidden:
            shown.append(key)
        elif not visible and key not in shared_hidden:
            hidden.append(key)
    state: dict = {"hidden": hidden, "shown": shown}
    if module in object_structure.ORDERABLE_MODULES and order != full_order(config, module):
        state["order"] = order
    rows = [{"key": r["key"]} if r.get("key") in keys and not r.get("id") else r for r in items]
    rows = strip_in_place(host, rows)
    if not any(r.get("id") for r in rows):
        rows = []  # своих блоков нет — хост не пишется (лимит своих страниц не тратится)
    return rows, state


def lift(config: dict, host: str, items: list[dict]) -> list[dict]:
    """Обратно из строк правки: порядок и скрытые разделы — в `<module>_detail` (прежний
    писатель-ключ), в `page_blocks` — только якоря (позиция) и свои блоки. На месте `config`."""
    from apps.tenants import siteconfig

    module = module_of(host)
    keys = set(section_keys(host))
    flow_keys = set(flow_section_keys(host))
    order = [r["key"] for r in items if r.get("key") in flow_keys and not r.get("id")]
    if not [k for k in order if k in anchor_keys(host)]:
        # ревью P5: черновик без строк разделов (начат до P5) не трогает порядок и видимость;
        # ревью S6f: строка оси («Angebot») — ещё не строка раздела
        return items
    hidden = sorted(
        r["key"]
        for r in items
        if r.get("key") in keys
        and not r.get("id")
        and r.get("enabled") is False
        and hideable(host, r["key"])
    )
    # FB-33 M2g: раздел «на месте», которого нет в черновике (черновик начат до M2g), —
    # прежняя видимость (а не «показан»)
    present = {r.get("key") for r in items if not r.get("id")}
    before = siteconfig.detail_section_hidden(config, module)
    hidden = sorted(
        set(hidden)
        | {k for k in detail_sections.in_place_keys(module) if k not in present and k in before}
    )
    if module in VISIBILITY_KEYS or module in FIXED_ORDER_MODULES:
        return strip_in_place(host, _lift_flags(config, host, module, items, keys, hidden))
    cfg_key = siteconfig.detail_section_config_key(module)
    detail = dict(config.get(cfg_key) or {}) if isinstance(config.get(cfg_key), dict) else {}
    if order and order != full_order(config, module):
        detail["order"] = order
    if hidden or detail.get("hidden") or cfg_key in config or "order" in detail:
        detail["hidden"] = hidden
        config[cfg_key] = detail
    rows = [{"key": r["key"]} if r.get("key") in keys and not r.get("id") else r for r in items]
    return strip_in_place(host, rows)


def _lift_flags(
    config: dict, host: str, module: str, items: list[dict], keys: set, hidden: list
) -> list[dict]:
    """FB-32 S4/S6a: видимость разделов — в прежние ключи (`cart_show_upsell`,
    `about_contact`: один ключ на Студию и схему). Якоря хранятся, только когда свой блок стоит
    выше последнего раздела, — иначе страница рисуется прежней разметкой байт-в-байт."""
    from apps.tenants import siteconfig

    present = {r.get("key") for r in items if r.get("key") in keys and not r.get("id")}
    for key, flag in VISIBILITY_KEYS.get(module, {}).items():
        if key not in present:
            continue  # ревью S6f: строки раздела нет — его видимость не трогаем
        if key in hidden:
            config[flag] = False
        else:
            config.pop(flag, None)
    axis = AXIS_SECTIONS.get(shared_host(host), frozenset())
    rows = []
    for r in items:
        if r.get("key") in axis and not r.get("id"):
            # строка оси хранит свой вид; «enabled» у неё не хранится (не скрывается)
            rows.append({k: v for k, v in r.items() if k != "enabled"})
        elif r.get("key") in keys and not r.get("id"):
            rows.append({"key": r["key"]})
        else:
            rows.append(r)
    return siteconfig.compact_section_rows(rows, set(flow_section_keys(host)) - axis, axis)


def page_flow(config, host: str, *, normalized: bool = False) -> list[dict]:
    """Поток страницы с постоянными разделами (корзина, «Über uns», своя страница):
    [{"section": k} | {"part": "ids:…"}]; пусто — прежняя разметка (разделы, затем все блоки).
    `normalized` — конфиг уже нормализован (горячий путь не нормализует его второй раз)."""
    from apps.tenants import siteconfig

    norm = config if normalized else siteconfig.normalize(config)
    rows = siteconfig.page_rows(norm, host)
    keys = list(flow_section_keys(host))
    hidden = siteconfig.detail_section_hidden(norm, module_of(host))
    order = [k for k in keys if k not in hidden]
    return flow(rows, host, order, all_order=keys)


def flow_ctx(config, host: str, *, normalized: bool = False) -> dict:
    """FB-32 S6a: контекст витрины текстовой страницы — `page_flow` (пусто — прежняя
    разметка) и `tail_part` (блоки после последнего раздела)."""
    from apps.tenants import siteconfig

    if not normalized and not ((config or {}).get("page_blocks") or {}).get(host):
        # ревью S6b: своих блоков нет — прежняя разметка без второй нормализации на запрос
        return {"page_flow": [], "tail_part": "after"}
    norm = config if normalized else siteconfig.normalize(config)
    rows = siteconfig.page_rows(norm, host)
    keys = list(flow_section_keys(host))
    hidden = siteconfig.detail_section_hidden(norm, module_of(host))
    items = flow(rows, host, [k for k in keys if k not in hidden], all_order=keys)
    return {"page_flow": items, "tail_part": tail_part(rows, host, keys)}


def promo_slots(config) -> dict:
    """FB-32 S6f: места своих блоков детали акции — {"lead": над «Angebot», "mid": между ним и
    «Weitere Aktionen», "tail": хвост}; {} — прежняя разметка (все блоки на прежнем месте).
    Без своих блоков — без нормализации (горячий путь детали)."""
    from apps.tenants import siteconfig

    host = "promo_detail"
    raw = (config.get("page_blocks") or {}).get(host) if isinstance(config, dict) else None
    pure = anchor_keys(host)
    # ревью S6f: без якорей разделов (частый случай P3 — только `[offer(style)]`) — без
    # нормализации на каждый показ детали
    if not isinstance(raw, list) or not any(
        isinstance(r, dict) and r.get("key") in pure and not r.get("id") for r in raw
    ):
        return {}
    try:
        rows = siteconfig.page_rows(siteconfig.normalize(config), host)
    except Exception:  # noqa: BLE001 — ревью S6f: страница акции (деньги) не падает из-за блоков
        logger.warning("promo_slots: normalize failed", exc_info=True)
        return {}
    a = anchors(rows, host, list(flow_section_keys(host)))
    if not a["placed"]:
        return {}
    return {
        "lead": ids_part(a["lead"]) if a["lead"] else "",
        "mid": ids_part(a["after"].get("offer", [])) if a["after"].get("offer") else "",
        "tail": ids_part(a["tail"]),
    }


def cart_flow(config, *, normalized: bool = False) -> list[dict]:
    """Поток страницы корзины (FB-32 S4) — `page_flow` хоста `cart`."""
    return page_flow(config, "cart", normalized=normalized)


def _fixed(a: dict, host: str) -> tuple[list, list]:
    lead = list(a["lead"])
    for key in FIRST_SCREEN.get(host, ()):
        lead += a["after"].get(key, [])
    return lead, list(a["after"].get(BODY_LAST.get(host, ""), []))


def _wide(a: dict, host: str) -> list:
    return list(a["after"].get(WIDE_LAST.get(host, ""), []))


def fixed_parts(rows, host: str, own: dict | None = None) -> dict:
    """FB-31 P5: свои блоки товара/номера по местам постоянной страницы — {"lead": part перед
    телом (до отзывов), "mid": part после отзывов (до «Ähnliche»)}; пусто — прежняя разметка.
    R8: `own` — якоря своих блоков объекта → "lead_own"/"mid_own" (после общих)."""
    a = anchors(rows, host, list(flow_section_keys(host)))
    out = {"lead": "", "mid": "", "wide": ""}
    if a["placed"]:
        lead, mid = _fixed(a, host)
        wide = _wide(a, host)
        out = {
            "lead": ids_part(lead) if lead else "",
            "mid": ids_part(mid) if mid else "",
            "wide": ids_part(wide) if wide else "",
        }
    if own:
        lead, mid = _fixed(own, host)
        out["lead_own"] = ids_part(lead) if lead else ""
        out["mid_own"] = ids_part(mid) if mid else ""
        wide = _wide(own, host)  # FB-33 M2f (ревью): свои блоки объекта после «Ähnliche»
        out["wide_own"] = ids_part(wide) if wide else ""
        out["own_host"] = own["host"]
    return out


def page_ctx(cfg, host: str, kind: str = "", obj=None) -> dict:
    """Контекст витрины постоянной детали (товар, номер): места своих блоков и `part` хвоста;
    R8 — и своих блоков объекта `obj`, если они стоят между разделами."""
    from apps.tenants import siteconfig

    norm = siteconfig.normalize(cfg)
    rows = (norm.get("page_blocks") or {}).get(host) or []
    order = list(flow_section_keys(host))
    own = own_anchors(norm, kind, obj, order) if obj is not None else None
    return {
        "detail_block_parts": fixed_parts(rows, host, own),
        "detail_tail_part": tail_part(rows, host, order),
    }


def own_tail(config, kind: str, obj) -> str | None:
    """R8: `part` своих блоков объекта для хвоста страницы; None — якорей нет (рисовать
    одним куском, как раньше)."""
    if kind not in OBJECT_SHARED:  # акция и прочее — свои блоки одним куском, как раньше
        return None
    own = own_anchors(config, kind, obj, object_order(config, kind, obj))
    if own is None:
        return None
    return ids_part(own["tail"]) if own["tail"] else ""
