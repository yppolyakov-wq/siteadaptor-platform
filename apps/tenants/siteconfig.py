"""Конструктор витрины v1 (Track C2): схема и нормализация Tenant.site_config.

Главная витрины собирается из готовых секций; владелец управляет порядком,
видимостью и текстами hero/about в кабинете («Site»). Это сознательно НЕ
drag-and-drop конструктор страниц (vision Модуль 20, Phase 3+) — настройка
блоков поверх фиксированных шаблонов.

site_config = {
    "sections": [{"key": "promotions", "enabled": true}, ...],  # в порядке показа
    "hero_title": "...", "hero_text": "...",
    "about_title": "...", "about_text": "...",
}
"""

from django.utils.translation import gettext_lazy as _

# (key, подпись для кабинета, включена ли по умолчанию)
SECTIONS = [
    ("hero", _("Welcome banner"), False),
    ("promotions", _("Current offers"), True),
    ("products", _("Products"), True),
    ("about", _("About us"), False),
    ("contact", _("Contact & opening hours"), True),
]
_KNOWN = {key for key, _label, _on in SECTIONS}

TEXT_FIELDS = ["hero_title", "hero_text", "about_title", "about_text"]


def default_sections() -> list[dict]:
    return [{"key": key, "enabled": enabled} for key, _label, enabled in SECTIONS]


def normalize(config) -> dict:
    """Привести произвольный site_config к валидной схеме.

    Неизвестные секции отбрасываются, отсутствующие дописываются в конец со
    своим дефолтом — старые конфиги переживают добавление новых секций.
    """
    config = config if isinstance(config, dict) else {}
    seen = set()
    sections = []
    for item in config.get("sections", []):
        key = item.get("key") if isinstance(item, dict) else None
        if key in _KNOWN and key not in seen:
            sections.append({"key": key, "enabled": bool(item.get("enabled"))})
            seen.add(key)
    for key, _label, enabled in SECTIONS:
        if key not in seen:
            sections.append({"key": key, "enabled": enabled})

    normalized = {"sections": sections}
    for field in TEXT_FIELDS:
        value = config.get(field, "")
        normalized[field] = value.strip() if isinstance(value, str) else ""
    return normalized


def enabled_sections(tenant) -> list[str]:
    """Упорядоченные ключи включённых секций главной для витрины."""
    return [s["key"] for s in normalize(tenant.site_config)["sections"] if s["enabled"]]
