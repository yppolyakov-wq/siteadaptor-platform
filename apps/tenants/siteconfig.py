"""Конструктор витрины v1 (Track C2): схема и нормализация Tenant.site_config.

Главная витрины собирается из готовых секций; владелец управляет порядком,
видимостью и текстами hero/about в кабинете («Site»). Это сознательно НЕ
drag-and-drop конструктор страниц (vision Модуль 20, Phase 3+) — настройка
блоков поверх фиксированных шаблонов.

site_config = {
    "sections": [{"key": "promotions", "enabled": true}, ...],  # в порядке показа
    "hero_title": "...", "hero_text": "...",
    "about_title": "...", "about_text": "...",
    "onboarding": {...},  # состояние Onboarding-Wizard (D0c, apps.tenants.onboarding)
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

# Стиль hero-баннера: plain — белая карточка (дефолт, как было), accent —
# фон акцентным цветом (Tenant.primary_color). Гейтим цветной фон флагом, а не
# самим primary_color: у легаси-тенантов он "#000000" и без флага витрина
# выглядит как раньше.
HERO_STYLES = ("plain", "accent")

# Навигация витрины (M20 ④): пункты шапки, их порядок и стиль.
# (key, подпись, url_name, требуемый модуль | None). offers/products — всегда
# доступны; остальные показываются только при активном модуле.
NAV_ITEMS = [
    ("offers", _("Offers"), "storefront-home", None),
    ("products", _("Products"), "storefront-products", None),
    ("booking", _("Book"), "storefront-termin", "booking"),
    ("stays", _("Stay"), "storefront-unterkunft", "stays"),
    ("events", _("Events"), "storefront-events", "events"),
    ("jobs", _("Request a quote"), "storefront-anfrage", "jobs"),
    ("inbox", _("Ask a question"), "storefront-message", "inbox"),
]
_NAV_KNOWN = {key for key, _l, _u, _m in NAV_ITEMS}
# Стиль шапки: classic (лого слева + ссылки справа, как было), centered (лого
# по центру, ссылки под ним), minimal (только лого, всё меню в бургере).
NAV_STYLES = ("classic", "centered", "minimal")


def default_nav() -> dict:
    return {
        "style": "classic",
        "sticky": True,
        "items": [{"key": key, "enabled": True} for key, _l, _u, _m in NAV_ITEMS],
    }


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
    hero_style = config.get("hero_style")
    normalized["hero_style"] = hero_style if hero_style in HERO_STYLES else "plain"
    # Навигация витрины (M20 ④): стиль + sticky + пункты (порядок владельца,
    # неизвестные отброшены, недостающие дописаны включёнными). Легаси без nav →
    # дефолт (classic/sticky/все включены) = текущее поведение, без регрессии.
    nav_in = config.get("nav") if isinstance(config.get("nav"), dict) else {}
    nav_items, nav_seen = [], set()
    for item in nav_in.get("items", []):
        key = item.get("key") if isinstance(item, dict) else None
        if key in _NAV_KNOWN and key not in nav_seen:
            nav_items.append({"key": key, "enabled": bool(item.get("enabled"))})
            nav_seen.add(key)
    for key, _l, _u, _m in NAV_ITEMS:
        if key not in nav_seen:
            nav_items.append({"key": key, "enabled": True})
    nav_style = nav_in.get("style")
    normalized["nav"] = {
        "style": nav_style if nav_style in NAV_STYLES else "classic",
        "sticky": bool(nav_in.get("sticky", True)),
        "items": nav_items,
    }
    # Состояние Onboarding-Wizard (D0c) живёт в том же JSON — сохранение
    # конструктора не должно его затирать.
    if isinstance(config.get("onboarding"), dict):
        normalized["onboarding"] = config["onboarding"]
    # Реестр id демо-контента (M20, apps.tenants.demo) — чтобы «Demo löschen»
    # удалил ровно созданное. Тоже переживает сохранение конструктора.
    if isinstance(config.get("demo"), dict):
        normalized["demo"] = config["demo"]
    return normalized


def enabled_sections(tenant) -> list[str]:
    """Упорядоченные ключи включённых секций главной для витрины."""
    return [s["key"] for s in normalize(tenant.site_config)["sections"] if s["enabled"]]
