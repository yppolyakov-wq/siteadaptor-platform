"""SEO-1: движок мета-заготовок (title/description) с плейсхолдерами.

Владелец задаёт per-тип шаблоны в ``site_config["seo"]["templates"][page_type]``;
резолвер подставляет плейсхолдеры (``{tenant}``/``{city}``/``{heading}``/``{name}``/
``{category}`` + суффиксы ``{tenant_sfx}``/``{city_sfx}``), фолбэк на архетип-дефолт,
клампит длину. Ничего не настроил → осмысленный дефолт (прогрессивность). БЕЗ миграции.
"""

import re

PAGE_TYPES = ("home", "listing", "detail", "category")

# Разумные дефолты per-тип. Суффиксы (…_sfx) вычисляются в resolve() и пусты, если
# источник пуст → без висячих разделителей. Плоские плейсхолдеры (owner-шаблоны) —
# подчищаются render_template (схлопывание разделителей).
DEFAULTS = {
    "home": {
        "title": "{tenant}{city_sfx}",
        "description": "{tenant}{city_sfx} — online ansehen, reservieren & bestellen.",
    },
    "listing": {
        "title": "{heading}{tenant_sfx}",
        "description": "{heading} bei {tenant}{city_sfx}.",
    },
    "detail": {
        "title": "{name}{tenant_sfx}",
        "description": "{name} bei {tenant}{city_sfx}.",
    },
    "category": {
        "title": "{category}{tenant_sfx}",
        "description": "{category} bei {tenant}{city_sfx}.",
    },
}

TITLE_MAX = 60
DESC_MAX = 155

_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_SEP = "·|,–—-"


def render_template(template: str, ctx: dict) -> str:
    """Подставить ``{key}`` из ctx (неизвестные/пустые → ''); подчистить разделители.

    Схлопывает лишние пробелы, убирает висячие/сдвоенные разделители (``·``/``|``),
    возникшие после удаления пустых плейсхолдеров."""
    if not template:
        return ""
    out = _PLACEHOLDER.sub(lambda m: str(ctx.get(m.group(1), "") or ""), template)
    out = re.sub(r"\s{2,}", " ", out)
    # сдвоенные разделители в середине («A ·  · B» → «A · B») и висячие по краям
    out = re.sub(r"\s*([" + _SEP + r"])\s*(?:[" + _SEP + r"]\s*)+", r" \1 ", out)
    out = re.sub(r"^[\s" + _SEP + r"]+|[\s" + _SEP + r"]+$", "", out)
    return out.strip()


def clamp(text: str, limit: int) -> str:
    """Обрезать до limit по границе слова с многоточием; ≤ limit — как есть."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    head = text[:limit].rsplit(" ", 1)[0].rstrip(" " + _SEP)
    return (head or text[:limit].rstrip()) + "…"


def resolve(tenant, page_type: str, ctx: dict | None = None) -> dict:
    """Разрешить title/description для (page_type, ctx).

    Приоритет шаблона: override в ctx (``title_override``/``desc_override``) →
    ``site_config["seo"]["templates"][page_type]`` → архетип-дефолт. Плейсхолдеры
    из tenant + ctx. Title всегда непустой (фолбэк — имя бизнеса)."""
    cfg = tenant.site_config if isinstance(getattr(tenant, "site_config", None), dict) else {}
    templates = ((cfg.get("seo") or {}).get("templates") or {}).get(page_type) or {}
    name = (tenant.name or "").strip()
    city = (getattr(tenant, "city", "") or "").strip()
    values = {
        "tenant": name,
        "city": city,
        "tenant_sfx": f" · {name}" if name else "",
        "city_sfx": f" · {city}" if city else "",
    }
    if ctx:
        values.update({k: v for k, v in ctx.items() if v not in (None, "")})

    defaults = DEFAULTS.get(page_type, DEFAULTS["home"])
    title_tpl = (ctx or {}).get("title_override") or templates.get("title") or defaults["title"]
    desc_tpl = (
        (ctx or {}).get("desc_override") or templates.get("description") or defaults["description"]
    )
    title = clamp(render_template(title_tpl, values), TITLE_MAX) or name
    description = clamp(render_template(desc_tpl, values), DESC_MAX)
    return {"title": title, "description": description}
