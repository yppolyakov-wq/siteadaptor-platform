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
SECTION_HOSTS = {"event_detail": "events"}
KAUF_KEY = "kauf"


def module_of(host: str) -> str:
    return SECTION_HOSTS.get(host, "")


def section_keys(host: str) -> tuple[str, ...]:
    return detail_sections.section_keys(module_of(host)) if module_of(host) else ()


def anchors(rows, host: str) -> dict:
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
    # после последней строки раздела — прежнее место (хвост страницы)
    out["tail"] = out["after"].pop(last, []) if last else []
    return out


def flow(rows, host: str, order: list[str], all_order: list[str] | None = None) -> list[dict]:
    """Поток тела: [{"section": k} | {"part": "ids:…"}] — видимые разделы в `order`, свои блоки
    между ними. `all_order` — полный порядок (со скрытыми): блоки скрытого раздела остаются
    на его месте. Пустой список — рисовать прежней разметкой."""
    a = anchors(rows, host)
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


def tail_part(rows, host: str) -> str:
    """`part` для тега блоков на прежнем месте хвоста ("after" — как раньше, все блоки)."""
    a = anchors(rows, host)
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
