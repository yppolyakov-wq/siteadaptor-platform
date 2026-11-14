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


# ───────── кабинет: вкладка «Seitenaufbau» объекта ─────────

_STATES = {"hide": "hidden", "show": "shown"}


def from_post(post, module: str) -> dict | None:
    """Значение поля из формы вкладки. Нет сентинела `page_override_present` — None:
    форму прислало другое место кабинета, поле не трогаем (W0). Кнопка «Zurück zum
    Standard» (`ps_reset`) — пустое значение."""
    if not post.get("page_override_present"):
        return None
    if post.get("ps_reset"):
        return {}
    raw: dict = {"hidden": [], "shown": [], "layout": post.get("ps_layout") or ""}
    for key in detail_sections.section_keys(module):
        target = _STATES.get(post.get(f"ps_{key}") or "")
        if target:
            raw[target].append(key)
    return clean(raw, module)


def apply_post(obj, kind: str, post) -> list[str]:
    """Записать вкладку в объект (без сохранения); вернуть изменённые поля. Сброс
    возвращает и форму карточки к общей."""
    module = MODULES[kind]
    value = from_post(post, module)
    if value is None:
        return []
    changed = []
    if value != _raw(obj):
        obj.page_override = value
        changed.append("page_override")
    if post.get("ps_reset"):
        if getattr(obj, "card_style", ""):
            obj.card_style = ""
            changed.append("card_style")
        drop_blocks(kind, obj)  # и свои блоки объекта
    return changed


def panel(config, kind: str, obj) -> dict:
    """Данные вкладки: разделы с общим состоянием и выбором объекта, шаблоны страницы."""
    from django.utils.translation import gettext_lazy as _

    from apps.core import page_settings
    from apps.tenants import siteconfig

    module = MODULES[kind]
    own = clean(_raw(obj), module)
    shared_hidden = siteconfig.detail_section_hidden(config, module)
    rows = []
    for section in detail_sections.sections_for(module):
        state = (
            "hide"
            if section.key in own.get("hidden", [])
            else "show"
            if section.key in own.get("shown", [])
            else "standard"
        )
        rows.append(
            {
                "key": section.key,
                "label": section.label,
                "shared_visible": section.key not in shared_hidden,
                "state": state,
            }
        )
    shared_layout = siteconfig.detail_layout(config, kind)
    labels = dict(page_settings.DETAIL_LAYOUT_OPTIONS)
    current = own.get("layout", "")
    layouts = [{"value": "", "label": _("Wie alle"), "hint": labels.get(shared_layout, "")}]
    for value, label in page_settings.DETAIL_LAYOUT_OPTIONS:
        layouts.append({"value": value or LAYOUT_STANDARD, "label": label, "hint": ""})
    for option in layouts:
        option["checked"] = option["value"] == current
    from django.urls import reverse

    code = schema_code(kind, obj)
    return {
        "rows": rows,
        "layouts": layouts,
        "deviations": deviations(obj, module),
        "kind": kind,
        # свои блоки объекта: сколько их и где править (экран «Seitenaufbau»)
        "own_blocks": len(own_blocks(config, kind, obj)),
        "blocks_url": f"{reverse('site-schema')}?seite={code}" if code else "",
    }


# ───────── свои блоки объекта (только на его странице) ─────────


def object_host(kind: str, obj) -> str:
    """Хост своих блоков объекта в `site_config["page_blocks"]` ("" — нет такого)."""
    pk = getattr(obj, "pk", None)
    hexed = getattr(pk, "hex", "")
    return f"{kind}:{hexed}" if kind in MODULES and hexed else ""


def schema_code(kind: str, obj) -> str:
    """Код строки экрана «Seitenaufbau» для своих блоков объекта."""
    host = object_host(kind, obj)
    return f"{kind}@{host}" if host else ""


def own_blocks(config, kind: str, obj) -> list:
    host = object_host(kind, obj)
    blocks = ((config or {}).get("page_blocks") or {}).get(host) if host else None
    return [b for b in blocks or [] if isinstance(b, dict) and b.get("id")]


def drop_blocks(kind: str, obj) -> bool:
    """Убрать свои блоки объекта вместе с переводами (удаление объекта, сброс)."""
    from apps.core import content_pages

    pk = getattr(obj, "pk", None)
    hexed = getattr(pk, "hex", "")
    if kind not in MODULES or not hexed:
        return False
    return content_pages.move_page_blocks(hexed, None, prefix=f"{kind}:")


def reset(obj, kind: str) -> list[str]:
    """«Zurück zum Standard» целиком: отличия, форма карточки и свои блоки. Возвращает
    изменённые поля объекта (сохраняет вызывающий)."""
    changed = []
    if _raw(obj):
        obj.page_override = {}
        changed.append("page_override")
    if getattr(obj, "card_style", ""):
        obj.card_style = ""
        changed.append("card_style")
    drop_blocks(kind, obj)
    return changed
