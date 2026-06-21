"""Структура «ретрит-лендинга» события (опциональные блоки).

`Event.details` — JSON со свободными секциями богатой страницы ретрита/события
(для кого, идея, что входит, расписание, проживание, питание, ведущие, что
взять, отзывы …). Всё опционально: пустой dict = старая короткая страница, без
регрессии. Здесь — канонический санитайз + парс/сериализация для формы кабинета
(построчный ввод «A | B»).
"""

_MAX_ITEMS = 30
_SEP = "|"


def _s(value, limit=2000) -> str:
    return str(value or "").strip()[:limit]


def _lines(value) -> list[str]:
    """Список строк из list или многострочного текста (непустые, с капом)."""
    if isinstance(value, str):
        value = value.splitlines()
    out = []
    for item in value or []:
        s = _s(item, 500)
        if s:
            out.append(s)
        if len(out) >= _MAX_ITEMS:
            break
    return out


def _records(value, keys) -> list[dict]:
    """Список dict'ов по ключам keys из list[dict] или строк «A | B | C»."""
    out = []
    for item in value or []:
        if isinstance(item, dict):
            parts = [item.get(k, "") for k in keys]
        elif isinstance(item, (list, tuple)):
            parts = list(item)
        else:
            parts = str(item).split(_SEP)
        rec = {k: _s(parts[i]) if i < len(parts) else "" for i, k in enumerate(keys)}
        if any(rec.values()):
            out.append(rec)
        if len(out) >= _MAX_ITEMS:
            break
    return out


# Схема: ключ → ("scalar" | "list" | (record-keys)).
_SCHEMA = {
    "promise": "scalar",
    "idea": "scalar",
    "for_whom": "list",
    "includes": ("title", "text"),
    "venue": "scalar",
    "accommodation": "list",
    "food": "scalar",
    "hosts": ("name", "role", "photo"),
    "price_includes": "list",
    "price_excludes": "list",
    "price_note": "scalar",
    "bring": "list",
    "faq": ("q", "a"),
    "testimonials": ("name", "city", "text"),
}


def normalize(raw) -> dict:
    """Привести Event.details к канону (безопасно к мусору)."""
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for key, kind in _SCHEMA.items():
        value = raw.get(key)
        if kind == "scalar":
            out[key] = _s(value)
        elif kind == "list":
            out[key] = _lines(value)
        else:
            out[key] = _records(value, kind)
    return out


def is_rich(details) -> bool:
    """Есть ли хоть один заполненный блок (нужен ли богатый рендер)."""
    d = normalize(details)
    return any(d.values())


# --- помощники формы кабинета (построчный ввод) ----------------------------
def list_to_text(value) -> str:
    return "\n".join(_lines(value))


def records_to_text(value, keys) -> str:
    rows = _records(value, keys)
    return "\n".join(f" {_SEP} ".join(r[k] for k in keys) for r in rows)
