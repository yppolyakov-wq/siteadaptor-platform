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

from apps.core import detail_sections

#: хост блоков детали → модуль реестра разделов (R3a: события и туры — цикл разделов;
#: услуга, товар, номер — следующими срезами)
SECTION_HOSTS = {
    "event_detail": "events",
    "service_detail": "booking",
    # товар и номер: разделы в двух полосах страницы — порядок постоянный (решение владельца)
    "product_detail": "catalog",
    "stay_detail": "stays",
}
#: разделы первого экрана (рядом с покупкой): скрыть можно, блоки рядом с ними — перед телом
FIRST_SCREEN = {
    "product_detail": ("description", "info"),
    "stay_detail": ("description", "amenities"),
}
#: хосты с постоянным порядком разделов: строки разделов только скрываются
FIXED_ORDER = frozenset(FIRST_SCREEN)
#: раздел тела, после которого стоят «средние» блоки (дальше — широкая полоса «Ähnliche»)
BODY_LAST = {"product_detail": "reviews", "stay_detail": "reviews"}
KAUF_KEY = "kauf"
KAUF_REF = "__kauf"  # строка схемы «Buchung» (не хранится)
#: где страница рисует покупку: у услуги — в первом экране, над разделами; у события — после
KAUF_FIRST = frozenset({"service_detail", "product_detail", "stay_detail"})


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
    return SECTION_HOSTS.get(host, "")


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


def anchors(rows, host: str, order: list[str] | None = None) -> dict:
    """{"placed": bool, "lead": [id], "after": {раздел: [id]}, "tail": [id]} — где стоят свои
    блоки относительно разделов. Скрытые/мусорные строки не мешают: якорь — порядок строк."""
    keys = set(section_keys(host))
    rows = [r for r in (rows if isinstance(rows, list) else []) if isinstance(r, dict)]
    placed = any(r.get("key") in keys and not r.get("id") for r in rows)
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
    # после последнего раздела (в ТЕКУЩЕМ порядке, ревью P5) — прежнее место, хвост страницы
    tail_key = order[-1] if order else last
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
        return list(section_keys(host))
    return object_structure.effective_full_order(config, module_of(host), obj)


def tail_part(rows, host: str, order: list[str] | None = None) -> str:
    """`part` для тега блоков на прежнем месте хвоста ("after" — как раньше, все блоки)."""
    a = anchors(rows, host, order)
    return ids_part(a["tail"]) if a["placed"] else "after"


def ids_part(ids) -> str:
    return "ids:" + ",".join(ids)


def full_order(config, module: str) -> list[str]:
    """Полный порядок разделов (со скрытыми): сохранённый + остальные по реестру."""
    from apps.tenants import siteconfig

    keys = detail_sections.section_keys(module)
    raw = (config or {}).get(siteconfig.detail_section_config_key(module))
    saved = siteconfig.normalize_detail_sections(raw, module).get("order", [])
    return saved + [k for k in keys if k not in saved]


# ───────── «Seitenaufbau»: строки разделов вперемешку со своими блоками ─────────


def edit_rows(config, host: str, rows) -> list[dict]:
    """Строки схемы детали для правки: свои блоки до разделов, каждый раздел (полный порядок,
    `enabled` — из скрытых) со своими блоками после него, хвост. Порядок разделов — из
    `<module>_detail.order`, видимость — из `hidden`: строки лишь показывают их на время правки."""
    from apps.tenants import siteconfig

    module = module_of(host)
    rows = [r for r in (rows if isinstance(rows, list) else []) if isinstance(r, dict)]
    a = anchors(rows, host, full_order(config, module))
    by_id = {r["id"]: r for r in rows if r.get("id")}
    hidden = siteconfig.detail_section_hidden(config, module)
    first = FIRST_SCREEN.get(host, ())
    # блоки до первого раздела — первыми (так их рисует и страница: `fixed_parts`, ревью P5)
    seq = [by_id[i] for i in a["lead"] if i in by_id]
    for key in first:  # первый экран — над блоками «до отзывов» (так рисует страница)
        seq.append({"key": key, "enabled": key not in hidden})
        seq += [by_id[i] for i in a["after"].get(key, []) if i in by_id]
    for key in full_order(config, module):
        if key in first:
            continue
        seq.append({"key": key, "enabled": key not in hidden})
        seq += [by_id[i] for i in a["after"].get(key, []) if i in by_id]
    seq += [by_id[i] for i in a["tail"] if i in by_id]
    return seq


def lift(config: dict, host: str, items: list[dict]) -> list[dict]:
    """Обратно из строк правки: порядок и скрытые разделы — в `<module>_detail` (прежний
    писатель-ключ), в `page_blocks` — только якоря (позиция) и свои блоки. На месте `config`."""
    from apps.tenants import siteconfig

    module = module_of(host)
    keys = set(section_keys(host))
    order = [r["key"] for r in items if r.get("key") in keys and not r.get("id")]
    if not order:
        # ревью P5: черновик без строк разделов (начат до P5) не трогает порядок и видимость
        return items
    hidden = sorted(
        r["key"]
        for r in items
        if r.get("key") in keys and not r.get("id") and r.get("enabled") is False
    )
    cfg_key = siteconfig.detail_section_config_key(module)
    detail = dict(config.get(cfg_key) or {}) if isinstance(config.get(cfg_key), dict) else {}
    if order and order != full_order(config, module):
        detail["order"] = order
    if hidden or detail.get("hidden") or cfg_key in config or "order" in detail:
        detail["hidden"] = hidden
        config[cfg_key] = detail
    return [{"key": r["key"]} if r.get("key") in keys and not r.get("id") else r for r in items]


def _fixed(a: dict, host: str) -> tuple[list, list]:
    lead = list(a["lead"])
    for key in FIRST_SCREEN.get(host, ()):
        lead += a["after"].get(key, [])
    return lead, list(a["after"].get(BODY_LAST.get(host, ""), []))


def fixed_parts(rows, host: str, own: dict | None = None) -> dict:
    """FB-31 P5: свои блоки товара/номера по местам постоянной страницы — {"lead": part перед
    телом (до отзывов), "mid": part после отзывов (до «Ähnliche»)}; пусто — прежняя разметка.
    R8: `own` — якоря своих блоков объекта → "lead_own"/"mid_own" (после общих)."""
    a = anchors(rows, host, list(section_keys(host)))
    out = {"lead": "", "mid": ""}
    if a["placed"]:
        lead, mid = _fixed(a, host)
        out = {"lead": ids_part(lead) if lead else "", "mid": ids_part(mid) if mid else ""}
    if own:
        lead, mid = _fixed(own, host)
        out["lead_own"] = ids_part(lead) if lead else ""
        out["mid_own"] = ids_part(mid) if mid else ""
        out["own_host"] = own["host"]
    return out


def page_ctx(cfg, host: str, kind: str = "", obj=None) -> dict:
    """Контекст витрины постоянной детали (товар, номер): места своих блоков и `part` хвоста;
    R8 — и своих блоков объекта `obj`, если они стоят между разделами."""
    from apps.tenants import siteconfig

    norm = siteconfig.normalize(cfg)
    rows = (norm.get("page_blocks") or {}).get(host) or []
    order = list(section_keys(host))
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
