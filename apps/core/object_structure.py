"""FB-29.4b: своя структура страницы у объекта (товар, услуга) поверх общей.

Общий вид страницы задаёт «Website › Seitenaufbau» (`site_config["<kind>_detail"]`:
скрытые разделы и шаблон). Объект хранит только ОТЛИЧИЯ — поле `page_override`:

    {"hidden": [...], "shown": [...], "layout": "tabs" | "breit" | "standard"}

`hidden` — раздел скрыт только у этого объекта; `shown` — показан, хотя у всех скрыт;
`layout` — свой шаблон страницы (`standard` — обычный вид, даже если у сайта другой).
Пустое поле = объект выглядит как все. Единственный читатель и чистильщик поля — здесь.
"""

from __future__ import annotations

from apps.core import detail_sections

#: Свой выбор «обычный вид» (у общих настроек обычный вид — пустая строка).
LAYOUT_STANDARD = "standard"

#: Вид сущности → модуль реестра разделов (`detail_sections`).
MODULES = {"product": "catalog", "service": "booking"}


def _raw(obj) -> dict:
    value = getattr(obj, "page_override", None)
    return value if isinstance(value, dict) else {}


def _keys(value, known) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    seen: list[str] = []
    for key in value:
        if isinstance(key, str) and key in known and key not in seen:
            seen.append(key)
    return seen


def clean(raw, module: str) -> dict:
    """Сырое значение → то, что хранится: только известные разделы модуля, раздел не
    может быть и показан, и скрыт (скрытие главнее), ключи — только с содержимым."""
    from apps.tenants import siteconfig

    raw = raw if isinstance(raw, dict) else {}
    known = detail_sections.section_keys(module)
    hidden = _keys(raw.get("hidden"), known)
    shown = [k for k in _keys(raw.get("shown"), known) if k not in hidden]
    out: dict = {}
    if hidden:
        out["hidden"] = hidden
    if shown:
        out["shown"] = shown
    layout = raw.get("layout")
    if layout == LAYOUT_STANDARD or layout in siteconfig.DETAIL_LAYOUTS:
        out["layout"] = layout
    return out


def effective_hidden(config, module: str, obj) -> set:
    """Скрытые разделы страницы объекта: общие, минус показанные у него, плюс его скрытые."""
    from apps.tenants import siteconfig

    own = clean(_raw(obj), module)
    shared = siteconfig.detail_section_hidden(config, module)
    return (shared - set(own.get("shown", []))) | set(own.get("hidden", []))


def effective_layout(config, kind: str, obj) -> str:
    """Шаблон страницы объекта: свой, иначе общий ("" | "tabs" | "breit")."""
    from apps.tenants import siteconfig

    own = clean(_raw(obj), MODULES.get(kind, "")).get("layout")
    if own == LAYOUT_STANDARD:
        return ""
    return own or siteconfig.detail_layout(config, kind)


def deviations(obj, module: str) -> int:
    """Сколько отличий от общего вида у объекта (плашка «N Abweichungen»)."""
    own = clean(_raw(obj), module)
    return len(own.get("hidden", [])) + len(own.get("shown", [])) + (1 if "layout" in own else 0)
