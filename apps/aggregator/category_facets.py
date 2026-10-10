"""T-8.13a: чипы категорий и признаков каталога города (портал и /entdecken/).

Показываем только то, где есть карточки (пустой чип = разочарование); раздел раскрывается
в свои категории. Параметры — `?kat=<раздел|категория>` и `?merkmal=<признак>`: путь
`/<facet>/` и `stadtteil/` уже заняты, параметры с ними не конфликтуют.
"""

from __future__ import annotations

from urllib.parse import urlencode

from apps.core import city_categories as cc

_TAG_SCAN_LIMIT = 2000  # пилотный пул небольшой; страховка от полного прохода


def selected(request) -> tuple[str, str]:
    """(kat, merkmal) из запроса — только известные справочнику значения."""
    kat = (request.GET.get("kat") or "").strip()
    tag = (request.GET.get("merkmal") or "").strip()
    if not cc.keys_for_filter(kat):
        kat = ""
    if not cc.normalize_tags([tag]):
        tag = ""
    return kat, tag


def _url(path: str, kat: str, tag: str, extra: dict | None = None) -> str:
    params = [(k, v) for k, v in (extra or {}).items() if v]
    params += [(k, v) for k, v in (("kat", kat), ("merkmal", tag)) if v]
    return f"{path}?{urlencode(params)}" if params else path


def chips(base_qs, path: str, kat: str, tag: str, extra: dict | None = None) -> dict:
    """Разделы/категории/признаки, присутствующие в `base_qs` (пул без этих фильтров)."""
    present = {k for k in base_qs.exclude(city_category="").values_list("city_category", flat=True)}
    present_sections = {cc.category(k).section for k in present if cc.category(k)}
    if cc.section(kat):
        open_section = kat
    elif cc.category(kat):
        open_section = cc.category(kat).section
    else:
        open_section = ""
    sections = [
        {
            "key": s.key,
            "label": f"{s.icon} {s.label}",
            "url": _url(path, "" if s.key == open_section else s.key, tag, extra),
            "active": s.key == open_section,
        }
        for s in cc.SECTIONS
        if s.key in present_sections
    ]
    categories = [
        {
            "key": c.key,
            "label": str(c.label),
            "url": _url(path, open_section if c.key == kat else c.key, tag, extra),
            "active": c.key == kat,
        }
        for c in cc.CATEGORIES
        if c.section == open_section and c.key in present
    ]
    found: set[str] = set()
    for tags in base_qs.values_list("city_tags", flat=True)[:_TAG_SCAN_LIMIT]:
        found.update(tags or [])
    tag_chips = [
        {
            "key": key,
            "label": str(label),
            "url": _url(path, kat, "" if key == tag else key, extra),
            "active": key == tag,
        }
        for key, label in cc.TAGS
        if key in found
    ]
    return {
        "sections": sections,
        "categories": categories,
        "tags": tag_chips,
        "any": bool(kat or tag),
        "clear_url": _url(path, "", "", extra),
        "label": " · ".join(x for x in (cc.label(kat), cc.tag_label(tag)) if x),
    }
