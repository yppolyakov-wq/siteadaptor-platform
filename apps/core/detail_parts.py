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


def module_of(host: str) -> str:
    return SECTION_HOSTS.get(host, "")


def section_keys(host: str) -> tuple[str, ...]:
    return detail_sections.section_keys(module_of(host)) if module_of(host) else ()


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


def flow(rows, host: str, order: list[str], all_order: list[str] | None = None) -> list[dict]:
    """Поток тела: [{"section": k} | {"part": "ids:…"}] — видимые разделы в `order`, свои блоки
    между ними. `all_order` — полный порядок (со скрытыми): блоки скрытого раздела остаются
    на его месте. Пустой список — рисовать прежней разметкой."""
    a = anchors(rows, host, all_order or order)
    if not a["placed"]:
        return []
    visible = set(order)
    items: list[dict] = []
    if a["lead"]:
        items.append({"part": ids_part(a["lead"])})
    for key in all_order or order:
        if key in visible:
            items.append({"section": key})
        if a["after"].get(key):
            items.append({"part": ids_part(a["after"][key])})
    return items


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


def fixed_parts(rows, host: str) -> dict:
    """FB-31 P5: свои блоки товара/номера по местам постоянной страницы — {"lead": part перед
    телом (до отзывов), "mid": part после отзывов (до «Ähnliche»)}; пусто — прежняя разметка."""
    a = anchors(rows, host, list(section_keys(host)))
    if not a["placed"]:
        return {"lead": "", "mid": ""}
    lead = list(a["lead"])
    for key in FIRST_SCREEN.get(host, ()):
        lead += a["after"].get(key, [])
    mid = a["after"].get(BODY_LAST.get(host, ""), [])
    return {"lead": ids_part(lead) if lead else "", "mid": ids_part(mid) if mid else ""}


def page_ctx(cfg, host: str) -> dict:
    """Контекст витрины постоянной детали (товар, номер): места своих блоков и `part` хвоста."""
    from apps.tenants import siteconfig

    rows = (siteconfig.normalize(cfg).get("page_blocks") or {}).get(host) or []
    return {
        "detail_block_parts": fixed_parts(rows, host),
        "detail_tail_part": tail_part(rows, host, list(section_keys(host))),
    }
