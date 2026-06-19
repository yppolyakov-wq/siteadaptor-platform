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
    # P4: «как мы работаем» (шаги) и команда — по умолчанию выключены.
    ("process", _("How it works"), False),
    ("team", _("Team"), False),
    # M20 ⑤a: контент-секции (по умолчанию выключены — легаси не затронут).
    ("cta", _("Call to action"), False),
    ("testimonials", _("Testimonials"), False),
    ("trust", _("Trust & credentials"), False),  # P3: рейтинг + знаки + «Seit …»
    ("faq", _("FAQ"), False),
    ("gallery", _("Photo gallery"), False),
    ("contact", _("Contact & opening hours"), True),
]
_MAX_MARKS = 8  # потолок знаков доверия
_MAX_GALLERY = 24  # потолок фото в галерее
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

# Шрифты витрины (P2a). ТОЛЬКО системные стеки — без загрузки веб-шрифтов
# (Google Fonts через CDN = риск GDPR в DE; self-host WOFF2 — отдельно, когда
# будут файлы). (body_stack, head_stack) для CSS-переменных --font-body/--font-head.
_SANS = (
    'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, '
    '"Helvetica Neue", Arial, sans-serif'
)
_SERIF = 'Georgia, Cambria, "Times New Roman", Times, serif'
_ROUNDED = 'ui-rounded, "SF Pro Rounded", "Hiragino Maru Gothic ProN", system-ui, sans-serif'
FONTS = {
    "system": (_SANS, _SANS),  # дефолт — как было
    "serif": (_SANS, _SERIF),  # элегантные serif-заголовки + sans-тело
    "rounded": (_ROUNDED, _ROUNDED),  # мягкий округлый
}


def font_stacks(font_key: str) -> tuple[str, str]:
    """(body_stack, head_stack) по ключу шрифта; неизвестный → system."""
    return FONTS.get(font_key, FONTS["system"])


_MAX_ITEMS = 12  # потолок строк для FAQ/Testimonials (анти-флуд)


def _s(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _clean_pairs(value, key_a: str, key_b: str) -> list[dict]:
    """Список dict'ов {key_a, key_b} из произвольного value — обе строки, первая
    непустая (иначе пропуск); максимум _MAX_ITEMS. Для FAQ/Testimonials."""
    out = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        a, b = _s(item.get(key_a)), _s(item.get(key_b))
        if a:
            out.append({key_a: a, key_b: b})
        if len(out) >= _MAX_ITEMS:
            break
    return out


def pairs_to_text(items, key_a: str, key_b: str) -> str:
    """Сериализация пар в textarea кабинета: «A | B» по строке."""
    return "\n".join(f"{i.get(key_a, '')} | {i.get(key_b, '')}".rstrip(" |") for i in items or [])


def text_to_pairs(text: str, key_a: str, key_b: str) -> list[dict]:
    """Парс textarea кабинета: строка «A | B» → {key_a, key_b} (первое « | » — разделитель)."""
    pairs = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        a, _sep, b = line.partition("|")
        pairs.append({key_a: a.strip(), key_b: b.strip()})
    return pairs[:_MAX_ITEMS]


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
    # Фон-фото hero (M20 demo): URL картинки-баннера; пусто → как раньше (accent/plain).
    normalized["hero_image"] = _s(config.get("hero_image"))
    # Шрифт витрины (P2a): системный стек по ключу; неизвестный → system.
    font = config.get("font")
    normalized["font"] = font if font in FONTS else "system"
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
    # Контент-секции (M20 ⑤a): FAQ, отзывы, CTA. Все опциональны; пустое — пропуск.
    normalized["faq"] = _clean_pairs(config.get("faq"), "q", "a")
    normalized["testimonials"] = _clean_pairs(config.get("testimonials"), "name", "text")
    # P4: шаги «как мы работаем» (заголовок|текст) и команда (имя/роль/фото).
    normalized["process"] = _clean_pairs(config.get("process"), "title", "text")
    team = []
    for item in config.get("team") or []:
        if not isinstance(item, dict):
            continue
        name = _s(item.get("name"))
        if name:
            team.append(
                {"name": name, "role": _s(item.get("role")), "photo": _s(item.get("photo"))}
            )
        if len(team) >= _MAX_ITEMS:
            break
    normalized["team"] = team
    # Знаки доверия (P3): год основания + список меток (Meisterbetrieb/Bio/TÜV…).
    trust_in = config.get("trust") if isinstance(config.get("trust"), dict) else {}
    marks = [_s(m) for m in (trust_in.get("marks") or []) if isinstance(m, str) and _s(m)]
    normalized["trust"] = {"since": _s(trust_in.get("since")), "marks": marks[:_MAX_MARKS]}
    cta = config.get("cta") if isinstance(config.get("cta"), dict) else {}
    normalized["cta"] = {
        "title": _s(cta.get("title")),
        "text": _s(cta.get("text")),
        "button_label": _s(cta.get("button_label")),
        "button_url": _s(cta.get("button_url")),
    }
    # Галерея (M20 ⑤b): список FileRef-dict'ов (как Product.images); грузятся
    # через apps.catalog.images.save_product_image, хранятся в site_config.
    gallery = []
    for ref in config.get("gallery") if isinstance(config.get("gallery"), list) else []:
        if isinstance(ref, dict) and ref.get("url"):
            gallery.append(ref)
        if len(gallery) >= _MAX_GALLERY:
            break
    normalized["gallery"] = gallery
    # T1: видео в галерее — один URL (YouTube/Vimeo/прямой файл). Рендерится
    # GDPR-дружелюбно (2-Klick / youtube-nocookie) в секции галереи.
    normalized["gallery_video"] = _s(config.get("gallery_video"))
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
