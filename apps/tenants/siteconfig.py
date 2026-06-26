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

import uuid

from django.utils.translation import gettext_lazy as _

# (key, подпись для кабинета, включена ли по умолчанию)
SECTIONS = [
    ("hero", _("Welcome banner"), False),
    # A.3 (T-B): тонкая «полоса доверия» под hero — иконка+подпись (Versand/Widerruf/
    # sichere Zahlung/Meisterbetrieb…). Выкл по умолчанию; показываем при наличии пунктов.
    ("usp_bar", _("Trust bar"), False),
    # H2: быстрый поиск размещения по датам (для отелей/пансионов). По умолчанию
    # выкл — показывается, только если включён и активен модуль stays.
    ("stay_search", _("Booking search (stays)"), False),
    # Карточки номеров прямо на главной (для отелей/пансионов). По умолчанию
    # выкл — показывается, только если включён и активен модуль stays.
    ("stay_rooms", _("Rooms (stays)"), False),
    # A3: блок «Leistungen & Preise» — услуги с ценой/длительностью (primary item
    # архетипа booking). Выкл по умолчанию — показываем при активном модуле booking
    # и наличии услуг (Service). Карточка ведёт к выбору времени.
    ("services", _("Services & prices"), False),
    ("promotions", _("Current offers"), True),
    # M20U-2: сетка категорий каталога (товары). Выкл по умолчанию — показываем,
    # только если включена и есть активные категории.
    ("categories", _("Categories"), False),
    ("products", _("Products"), True),
    # M20U-2: ближайшие мероприятия/ретриты (primary items архетипа events).
    # Выкл по умолчанию; показываем при активном модуле events и наличии событий.
    ("events", _("Events"), False),
    # S2: сетка тизеров активных архетипов («Наши разделы / Unsere Bereiche»).
    # По умолчанию выкл — легаси-витрины не затронуты; включают в кабинете/демо.
    ("archetypes", _("Our offerings"), False),
    ("about", _("About us"), False),
    # P4: «как мы работаем» (шаги) и команда — по умолчанию выключены.
    ("process", _("How it works"), False),
    ("team", _("Team"), False),
    # M20 ⑤a: контент-секции (по умолчанию выключены — легаси не затронут).
    ("cta", _("Call to action"), False),
    ("testimonials", _("Testimonials"), False),
    ("trust", _("Trust & credentials"), False),  # P3: рейтинг + знаки + «Seit …»
    # G8/#6: блок отзывов клиентов (читается из SHARED BusinessReview). По
    # умолчанию выключен — показываем, только если у бизнеса есть отзывы.
    ("reviews", _("Customer reviews"), False),
    ("faq", _("FAQ"), False),
    ("gallery", _("Photo gallery"), False),
    # A7: «Vorher / Nachher» — интерактивный слайдер кейсов санации (Handwerker/
    # Werkstatt/Studios). Выкл по умолчанию; показываем при наличии before_after.
    ("before_after", _("Before & after"), False),
    ("contact", _("Contact & opening hours"), True),
]
_MAX_MARKS = 8  # потолок знаков доверия
_MAX_USP = 6  # потолок пунктов полосы доверия (usp_bar)

# A.3 (T-B): набор предустановленных иконок полосы доверия. Ключ → emoji (как в
# нижнем таб-баре витрины — без внешних ресурсов, GDPR-safe). Произвольный ключ →
# фолбэк "check". Single source of truth для шаблона `_usp_bar.html` и билдера.
USP_ICONS = {
    "shipping": "🚚",  # Versand / Lieferung
    "returns": "↩️",  # Widerruf / Rückgabe
    "payment": "💳",  # sichere Zahlung
    "secure": "🔒",  # SSL / Datenschutz
    "local": "📍",  # regional / vor Ort
    "meister": "🛠️",  # Meisterbetrieb / Handwerk
    "support": "💬",  # persönlicher Service
    "quality": "✅",  # geprüfte Qualität
    "bio": "🌿",  # Bio / nachhaltig
    "clock": "⏰",  # schnell / Öffnungszeiten
    "check": "✓",  # фолбэк / generisch
}
USP_ICON_KEYS = list(USP_ICONS)


def usp_icon(token: str) -> str:
    """Emoji-символ пункта полосы доверия по токену (фолбэк — «✓»)."""
    return USP_ICONS.get(token, USP_ICONS["check"])


_MAX_GALLERY = 24  # потолок фото в галерее
_MAX_ARCHETYPES = 30  # потолок пер-архетипных оверрайдов тизеров (S2)
_MAX_COVER_GALLERY = 12  # потолок фото в галерее раздела (S3b)
_KNOWN = {key for key, _label, _on in SECTIONS}

# D.2 (анти-Битрикс Phase 2): повторяемые «простые блоки» (C-блоки) — НЕ в SECTIONS
# (множественные, с собственным `id` и `data`). Владелец собирает из них контент
# («собрать сайт из кубиков»). Живут в той же `site_config["sections"]`.
REPEATABLE_BLOCKS = ("text", "image", "image_text", "button", "spacer")
_MAX_CBLOCKS = 30


def _clean_cblock_data(key: str, raw) -> dict:
    """Санитизация данных C-блока по типу (строки; неизвестные ключи отброшены)."""
    d = raw if isinstance(raw, dict) else {}
    if key == "text":
        return {"title": _s(d.get("title")), "body": _s(d.get("body"))}
    if key == "image":
        return {"url": _s(d.get("url")), "caption": _s(d.get("caption"))}
    if key == "image_text":
        side = d.get("side")
        return {
            "url": _s(d.get("url")),
            "title": _s(d.get("title")),
            "body": _s(d.get("body")),
            "side": side if side in ("left", "right") else "left",
        }
    if key == "button":
        return {"label": _s(d.get("label")), "url": _s(d.get("url"))}
    return {}  # spacer — без данных


def _clean_cblock(item: dict) -> dict:
    """C-блок → {key, id, enabled, data}. id сохраняется (или генерится)."""
    key = item["key"]
    bid = _s(item.get("id")) or uuid.uuid4().hex[:12]
    return {
        "key": key,
        "id": bid,
        "enabled": bool(item.get("enabled", True)),
        "data": _clean_cblock_data(key, item.get("data")),
    }


# M20R-1: универсальный layout-движок секций-сеток. Пресет = быстрый выбор
# раскладки (анти-Битрикс), `cols/mobile/gap/width` — ручной override («Дополнительно»).
LAYOUT_PRESETS = {
    "list": {"cols": 1, "mobile": 1, "gap": "md"},  # вертикальный список
    "cols2": {"cols": 2, "mobile": 1, "gap": "md"},
    "cols3": {"cols": 3, "mobile": 2, "gap": "md"},
    "cols4": {"cols": 4, "mobile": 2, "gap": "md"},
    "gallery": {"cols": 4, "mobile": 2, "gap": "sm"},  # плотная сетка
}
LAYOUT_PRESET_KEYS = list(LAYOUT_PRESETS)
_LAYOUT_WIDTHS = ("contained", "full")
_LAYOUT_GAPS = ("sm", "md", "lg")

# Секции-сетки → дефолтная раскладка (воспроизводит текущие захардкоженные гриды,
# чтобы M20R-1 не дал визуальной регрессии). Прочие секции layout не несут.
GRID_SECTION_DEFAULTS = {
    "categories": {"preset": "cols4"},  # M20U-2: карточки категорий
    "events": {"preset": "cols3"},  # M20U-2: карточки ближайших мероприятий
    "services": {"preset": "cols2"},  # A3: услуги (как service_index sm:grid-cols-2)
    "products": {"preset": "cols4"},  # было grid-cols-2 lg:grid-cols-4 (mobile 2)
    "stay_rooms": {"preset": "cols3", "mobile": 1},  # было grid-cols-1 sm:2 lg:3
    "promotions": {"preset": "cols3"},  # было 2 mobile / 3 lg
    "archetypes": {"preset": "cols3", "mobile": 1},  # было grid-cols-1 sm:2 lg:3
    "team": {"preset": "cols4"},  # было grid-cols-2 sm:3 lg:4
    "testimonials": {"preset": "cols2"},  # было grid-cols-1 sm:2 (mobile 1)
    "reviews": {"preset": "cols3", "mobile": 1},  # было sm:2 lg:3
    "gallery": {"preset": "gallery"},  # было grid-cols-2 sm:3 lg:4
}

# M20U-7: секции-превью на главной с настраиваемым числом элементов (source.limit).
# Ключ → дефолт (воспроизводит текущее поведение storefront_home). Прочие секции-
# сетки (categories/stay_rooms/team/…) показывают всё — лимит к ним не применяем.
GRID_SECTION_LIMITS = {"products": 8, "events": 6}
_SECTION_LIMIT_MAX = 24

# M20U-7: источник товаров секции products. featured_first — текущее поведение
# (избранные вперёд, затем новые); newest — только по дате; featured_only —
# только избранные.
PRODUCT_SOURCES = ("featured_first", "newest", "featured_only")
PRODUCT_SOURCE_DEFAULT = "featured_first"

# Purge-safe статические таблицы Tailwind-классов (динамические строки нельзя —
# их вырежет purge). mobile=база, sm=планшет (капд до 3), lg=десктоп.
_GRID_MOBILE = {1: "grid-cols-1", 2: "grid-cols-2"}
_GRID_SM = {1: "sm:grid-cols-1", 2: "sm:grid-cols-2", 3: "sm:grid-cols-3"}
_GRID_LG = {
    1: "lg:grid-cols-1",
    2: "lg:grid-cols-2",
    3: "lg:grid-cols-3",
    4: "lg:grid-cols-4",
    5: "lg:grid-cols-5",
}
_GRID_GAP = {"sm": "gap-3", "md": "gap-4 md:gap-6", "lg": "gap-6 md:gap-8"}
# Планшетный (sm) шаг по числу колонок десктопа — плавный спуск вниз.
_SM_FROM_COLS = {1: 1, 2: 2, 3: 2, 4: 3, 5: 3}


def _clamp(value, lo, hi, default):
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def normalize_layout(raw, default=None) -> dict:
    """Привести layout секции к канону {preset, width, cols, mobile, gap}.

    Старт — пресет (из default или raw), затем ручные override. Значения клампятся;
    мусор → дефолт. Back-compat: пустой raw → раскладка из default-пресета секции.
    """
    default = default or {"preset": "cols3"}
    base_preset = default.get("preset", "cols3")
    raw = raw if isinstance(raw, dict) else {}
    preset = raw.get("preset", base_preset)
    if preset not in LAYOUT_PRESETS:
        preset = base_preset
    eff = {**LAYOUT_PRESETS[preset], **{k: v for k, v in default.items() if k != "preset"}}
    cols = _clamp(raw.get("cols", eff["cols"]), 1, 5, eff["cols"])
    mobile = _clamp(raw.get("mobile", eff["mobile"]), 1, 2, eff["mobile"])
    gap = raw.get("gap", eff.get("gap", "md"))
    if gap not in _LAYOUT_GAPS:
        gap = "md"
    width = raw.get("width", "contained")
    if width not in _LAYOUT_WIDTHS:
        width = "contained"
    return {"preset": preset, "width": width, "cols": cols, "mobile": mobile, "gap": gap}


def grid_class_string(layout) -> str:
    """Готовая Tailwind-строка грида из layout (purge-safe, из статических таблиц)."""
    lay = normalize_layout(layout if isinstance(layout, dict) else None)
    cols, mobile, gap = lay["cols"], lay["mobile"], lay["gap"]
    sm = max(mobile, _SM_FROM_COLS[cols])
    return " ".join(["grid", _GRID_MOBILE[mobile], _GRID_SM[sm], _GRID_LG[cols], _GRID_GAP[gap]])


def section_layout(config, key) -> dict:
    """Layout секции `key` из нормализованного config (или дефолт секции)."""
    default = GRID_SECTION_DEFAULTS.get(key)
    for item in (config or {}).get("sections", []):
        if (
            isinstance(item, dict)
            and item.get("key") == key
            and isinstance(item.get("layout"), dict)
        ):
            return item["layout"]
    return normalize_layout(None, default)


def section_limit(config, key) -> int:
    """M20U-7: сколько элементов выводит секция-превью `key` (клампится 1..MAX).

    Берётся из конфига секции, иначе дефолт `GRID_SECTION_LIMITS`. Для секций без
    настраиваемого лимита возвращает дефолт 8 (на всякий случай)."""
    default = GRID_SECTION_LIMITS.get(key, 8)
    for item in (config or {}).get("sections", []):
        if isinstance(item, dict) and item.get("key") == key:
            return _clamp(item.get("limit"), 1, _SECTION_LIMIT_MAX, default)
    return default


# M20U-7: секции главной с настраиваемым владельцем заголовком (иначе шаблон берёт
# дефолтный {% trans %}). Хранится в config["section_titles"][key].
SECTION_TITLE_KEYS = {"promotions", "categories", "products", "events", "stay_rooms", "services"}
_SECTION_TITLE_MAX = 80

# M20U-7: секции с ссылкой «View all» → её можно скрыть (show_all=False).
SECTION_VIEWALL_KEYS = {"categories", "products", "events", "stay_rooms", "services"}


def section_title(config, key) -> str:
    """Кастомный заголовок секции `key` (или "" → шаблон выводит дефолт)."""
    titles = (config or {}).get("section_titles")
    if isinstance(titles, dict):
        return _s(titles.get(key))[:_SECTION_TITLE_MAX]
    return ""


def product_source(config) -> str:
    """M20U-7: источник товаров секции-превью products (PRODUCT_SOURCES)."""
    for item in (config or {}).get("sections", []):
        if isinstance(item, dict) and item.get("key") == "products":
            src = item.get("source")
            return src if src in PRODUCT_SOURCES else PRODUCT_SOURCE_DEFAULT
    return PRODUCT_SOURCE_DEFAULT


def section_show_all(config, key) -> bool:
    """M20U-7: показывать ли ссылку «View all» секции `key` (по умолчанию True)."""
    for item in (config or {}).get("sections", []):
        if isinstance(item, dict) and item.get("key") == key:
            return bool(item.get("show_all", True))
    return True


# M20U-4: тематические секции детальной события — дефолтный порядок (как в
# шаблоне event_detail.html). Владелец может переупорядочить/скрыть через
# config["event_detail"] = {"order": [...], "hidden": [...]}.
EVENT_DETAIL_SECTION_KEYS = (
    "for_whom",
    "idea",
    "includes",
    "program",
    "venue",
    "accommodation",
    "food",
    "hosts",
    "price",
    "bring",
    "faq",
    "testimonials",
    "before_after",
    "certifications",
)


def normalize_event_detail(raw) -> dict:
    """Привести config['event_detail'] к {order:[known], hidden:[known]}."""
    ed = raw if isinstance(raw, dict) else {}
    order, seen = [], set()
    for k in ed.get("order") or []:
        if k in EVENT_DETAIL_SECTION_KEYS and k not in seen:
            order.append(k)
            seen.add(k)
    hidden = [k for k in (ed.get("hidden") or []) if k in EVENT_DETAIL_SECTION_KEYS]
    return {"order": order, "hidden": sorted(set(hidden))}


def event_detail_order(config) -> list[str]:
    """Порядок ВИДИМЫХ тематических секций детальной события.

    Сохранённый order (известные ключи) + недостающие в дефолтном порядке реестра,
    минус hidden. Пустой/мусорный config → полный список в порядке реестра."""
    ed = normalize_event_detail((config or {}).get("event_detail"))
    hidden = set(ed["hidden"])
    seen = set(ed["order"])
    order = ed["order"] + [k for k in EVENT_DETAIL_SECTION_KEYS if k not in seen]
    return [k for k in order if k not in hidden]


TEXT_FIELDS = ["hero_title", "hero_text", "about_title", "about_text"]

# M20: вложенные текстовые поля секций, редактируемые инлайн (dotted path
# "<секция>.<поле>"). Белый список — защита от записи произвольных ключей.
NESTED_TEXT_FIELDS = ["cta.title", "cta.text"]

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

# S7: многоуровневое меню. Узел = {label, type, target, enabled, icon, children}.
# type определяет, как строится ссылка (резолв — apps.tenants.menu):
#   archetype  → target = ключ модуля (catalog/booking/…), ссылка из реестра;
#   category   → target = slug категории каталога (/sortiment/?kategorie=…);
#   promo_group→ target = группа акций (S6; до S6 ссылки нет);
#   page       → target = спец-страница витрины (home/offers; loyalty — S5);
#   url        → target = произвольный URL (внешний/относительный);
#   anchor     → target = якорь секции главной (#aktionen);
#   group      → без своей ссылки, только родитель выпадающего подменю.
MENU_NODE_TYPES = ("archetype", "category", "promo_group", "page", "url", "anchor", "group")
_MAX_MENU_ITEMS = 20  # потолок пунктов на уровень
_MENU_MAX_DEPTH = 2  # глубина вложенности (родитель + дети)
# Соответствие легаси-пунктов nav → узлы меню (для вывода menus.top из nav).
_NAV_KEY_TO_NODE = {
    "offers": ("page", "home"),
    "products": ("archetype", "catalog"),
    "booking": ("archetype", "booking"),
    "stays": ("archetype", "stays"),
    "events": ("archetype", "events"),
    "jobs": ("archetype", "jobs"),
    "inbox": ("archetype", "inbox"),
}


def _clean_menu_node(raw, depth: int):
    """Узел меню из произвольного value; None — если без подписи. Глубина
    ограничена _MENU_MAX_DEPTH (дети дальше не разбираются)."""
    if not isinstance(raw, dict):
        return None
    label = _s(raw.get("label"))
    if not label:
        return None
    ntype = raw.get("type") if raw.get("type") in MENU_NODE_TYPES else "url"
    node = {
        "label": label,
        "type": ntype,
        "target": _s(raw.get("target")),
        "enabled": bool(raw.get("enabled", True)),
        "icon": _s(raw.get("icon"))[:8],
        "children": [],
    }
    if depth < _MENU_MAX_DEPTH and isinstance(raw.get("children"), list):
        for child in raw["children"][:_MAX_MENU_ITEMS]:
            cleaned = _clean_menu_node(child, depth + 1)
            if cleaned is not None:
                node["children"].append(cleaned)
    return node


def _clean_menu_items(raw):
    out = []
    if isinstance(raw, list):
        for item in raw[:_MAX_MENU_ITEMS]:
            node = _clean_menu_node(item, 1)
            if node is not None:
                out.append(node)
    return out


def _nav_to_menu_nodes(nav: dict) -> list[dict]:
    """Вывести узлы top-меню из легаси-nav (та же плоская шапка)."""
    labels = {key: label for key, label, _u, _m in NAV_ITEMS}
    nodes = []
    for item in nav["items"]:
        mapping = _NAV_KEY_TO_NODE.get(item["key"])
        if mapping is None:
            continue
        ntype, target = mapping
        nodes.append(
            {
                "label": str(labels.get(item["key"], item["key"])),
                "type": ntype,
                "target": target,
                "enabled": bool(item["enabled"]),
                "icon": "",
                "children": [],
            }
        )
    return nodes


def _normalize_menus(raw, nav: dict) -> dict:
    """top/bottom меню. Нет `menus` → top из nav, bottom выключен (авто таб-бар)."""
    if not isinstance(raw, dict):
        return {
            "top": {
                "style": nav["style"],
                "sticky": nav["sticky"],
                "items": _nav_to_menu_nodes(nav),
            },
            "bottom": {"enabled": False, "items": []},
        }
    top = raw.get("top") if isinstance(raw.get("top"), dict) else {}
    bottom = raw.get("bottom") if isinstance(raw.get("bottom"), dict) else {}
    top_style = top.get("style")
    return {
        "top": {
            "style": top_style if top_style in NAV_STYLES else nav["style"],
            "sticky": bool(top.get("sticky", nav["sticky"])),
            "items": _clean_menu_items(top.get("items")),
        },
        "bottom": {
            "enabled": bool(bottom.get("enabled", False)),
            "items": _clean_menu_items(bottom.get("items")),
        },
    }


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


_MAX_HEROES = 6  # потолок слайдов баннера-слайдера (M20U-2)


def normalize_heroes(raw) -> list[dict]:
    """M20U-2: слайды баннера → [{image, title, text, button_label, button_url}].

    Пустые (без image/title/text) отбрасываются; кап _MAX_HEROES. Back-compat:
    отсутствие/мусор → [], тогда витрина показывает одиночный hero_* как раньше.
    """
    out = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        h = {
            "image": _s(item.get("image")),
            "title": _s(item.get("title"))[:200],
            "text": _s(item.get("text"))[:400],
            "button_label": _s(item.get("button_label"))[:60],
            "button_url": _s(item.get("button_url"))[:300],
        }
        if h["image"] or h["title"] or h["text"]:
            out.append(h)
        if len(out) >= _MAX_HEROES:
            break
    return out


def _clean_gallery(value, cap: int) -> list[dict]:
    """FileRef-список (dict'ы с непустым url), не длиннее cap. Для галерей."""
    out = []
    for ref in value if isinstance(value, list) else []:
        if isinstance(ref, dict) and ref.get("url"):
            out.append(ref)
        if len(out) >= cap:
            break
    return out


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


def clean_usp(value) -> list[dict]:
    """A.3: пункты полосы доверия → [{icon, label}]. icon валидируется по USP_ICONS
    (неизвестный → "check"), label обязателен (иначе пропуск). Максимум _MAX_USP."""
    out = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        label = _s(item.get("label"))
        if not label:
            continue
        icon = item.get("icon")
        out.append({"icon": icon if icon in USP_ICONS else "check", "label": label})
        if len(out) >= _MAX_USP:
            break
    return out


def usp_to_text(items) -> str:
    """Сериализация usp_bar в textarea кабинета: «icon | label» по строке."""
    return "\n".join(f"{i.get('icon', 'check')} | {i.get('label', '')}" for i in items or [])


def text_to_usp(text: str) -> list[dict]:
    """Парс textarea кабинета: строка «icon | label» → {icon, label} (валидация в clean_usp)."""
    items = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        icon, _sep, label = line.partition("|")
        items.append({"icon": icon.strip(), "label": label.strip()})
    return clean_usp(items)


# Поля контент-секций (CTA/FAQ/Testimonials/Process/Team/Trust), общие для формы
# «Site» и конструктора главной (M20d). Имена полей едины во всех формах.
CONTENT_FIELDS = (
    "cta_title",
    "cta_text",
    "cta_button_label",
    "cta_button_url",
    "faq_text",
    "testimonials_text",
    "process_text",
    "team_text",
    "trust_since",
    "trust_marks",
    "usp_text",
)


def parse_content_sections(get) -> dict:
    """M20d: разобрать контент-секции из формы в фрагмент site_config.

    `get(name, default="")` — request.POST.get / data.get (один код на «Site»,
    билдер и live-preview-черновик). Возвращает {cta, faq, testimonials, process,
    team, trust} для слияния в config."""

    def g(name):
        return get(name, "") or ""

    return {
        "cta": {
            "title": g("cta_title"),
            "text": g("cta_text"),
            "button_label": g("cta_button_label"),
            "button_url": g("cta_button_url"),
        },
        "faq": text_to_pairs(g("faq_text"), "q", "a"),
        "testimonials": text_to_pairs(g("testimonials_text"), "name", "text"),
        "process": text_to_pairs(g("process_text"), "title", "text"),
        "team": [
            {"name": p["name"], "role": p["text"], "photo": ""}
            for p in text_to_pairs(g("team_text"), "name", "text")
        ],
        "trust": {
            "since": g("trust_since").strip(),
            "marks": [m.strip() for m in g("trust_marks").splitlines() if m.strip()],
        },
        "usp_bar": text_to_usp(g("usp_text")),
    }


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

    def _section(key, enabled, raw_item):
        # M20R-1: секции-сетки несут layout (пресет+override); прочие — нет.
        raw_item = raw_item if isinstance(raw_item, dict) else {}
        entry = {"key": key, "enabled": enabled}
        if key in GRID_SECTION_DEFAULTS:
            entry["layout"] = normalize_layout(raw_item.get("layout"), GRID_SECTION_DEFAULTS[key])
        # M20U-7: секции-превью несут настраиваемый лимит элементов.
        if key in GRID_SECTION_LIMITS:
            entry["limit"] = _clamp(
                raw_item.get("limit"), 1, _SECTION_LIMIT_MAX, GRID_SECTION_LIMITS[key]
            )
        # M20U-7: источник товаров секции products (избранные/новые/избр.-первыми).
        if key == "products":
            src = raw_item.get("source")
            entry["source"] = src if src in PRODUCT_SOURCES else PRODUCT_SOURCE_DEFAULT
        # M20U-7: видимость ссылки «View all» (по умолчанию показана).
        if key in SECTION_VIEWALL_KEYS:
            entry["show_all"] = bool(raw_item.get("show_all", True))
        return entry

    cblocks = 0
    for item in config.get("sections", []):
        key = item.get("key") if isinstance(item, dict) else None
        if key in _KNOWN and key not in seen:
            sections.append(_section(key, bool(item.get("enabled")), item))
            seen.add(key)
        elif key in REPEATABLE_BLOCKS and cblocks < _MAX_CBLOCKS:
            # D.2: C-блоки множественные — порядок сохраняем, по key не дедупим.
            sections.append(_clean_cblock(item))
            cblocks += 1
    for key, _label, enabled in SECTIONS:
        if key not in seen:
            sections.append(_section(key, enabled, None))

    normalized = {"sections": sections}
    for field in TEXT_FIELDS:
        value = config.get(field, "")
        normalized[field] = value.strip() if isinstance(value, str) else ""
    hero_style = config.get("hero_style")
    normalized["hero_style"] = hero_style if hero_style in HERO_STYLES else "plain"
    # Фон-фото hero (M20 demo): URL картинки-баннера; пусто → как раньше (accent/plain).
    normalized["hero_image"] = _s(config.get("hero_image"))
    # M20U-2: слайдер главных баннеров (heroes[]); пусто → одиночный hero выше (back-compat).
    normalized["heroes"] = normalize_heroes(config.get("heroes"))
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
    # S7: многоуровневое меню (top + bottom). Дерево узлов с привязкой к
    # архетипам/категориям/страницам/URL/якорям; глубина 2. Легаси без `menus`
    # → top выводим из `nav` (та же плоская шапка, без регрессии), bottom —
    # выключен (используется авто таб-бар T2b).
    normalized["menus"] = _normalize_menus(config.get("menus"), normalized["nav"])
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
    # A.3 (T-B): полоса доверия — список {icon, label}.
    normalized["usp_bar"] = clean_usp(config.get("usp_bar"))
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
    # A7: кейсы «Vorher / Nachher» — список {before, after, text}. Обе картинки
    # обязательны (иначе слайдеру нечего сравнивать); текст опционален.
    before_after = []
    for ref in config.get("before_after") if isinstance(config.get("before_after"), list) else []:
        if isinstance(ref, dict) and _s(ref.get("before")) and _s(ref.get("after")):
            before_after.append(
                {
                    "before": _s(ref.get("before")),
                    "after": _s(ref.get("after")),
                    "text": _s(ref.get("text")),
                }
            )
        if len(before_after) >= _MAX_GALLERY:
            break
    normalized["before_after"] = before_after
    # S2: пер-архетипные оверрайды тизеров секции «Наши разделы». Ключ —
    # ключ модуля (catalog/booking/…); значения переопределяют дефолт из реестра
    # (storefront_label/blurb) и прячут отдельный тизер. Картинка тизера — в S3
    # (обложка архетипа). Список активных архетипов витрина берёт из реестра;
    # здесь только оверрайды, поэтому набор ключей не валидируем по тенанту.
    archetypes = {}
    raw_arch = config.get("archetypes")
    if isinstance(raw_arch, dict):
        for key, ov in list(raw_arch.items())[:_MAX_ARCHETYPES]:
            if not isinstance(key, str) or not isinstance(ov, dict):
                continue
            archetypes[key] = {
                "label": _s(ov.get("label")),
                "blurb": _s(ov.get("blurb")),
                "hidden": bool(ov.get("hidden")),
                # S3: «обложка» раздела — интро-текст и hero-фото над лендингом.
                "intro": _s(ov.get("intro")),
                "hero_image": _s(ov.get("hero_image")),
                # S3b: галерея раздела (FileRef-список, как галерея главной).
                "gallery": _clean_gallery(ov.get("gallery"), _MAX_COVER_GALLERY),
            }
    normalized["archetypes"] = archetypes
    # T2c: быстрый заказ («+»/модалка-конфигуратор) на карточках витрины.
    # Дефолт True (поведение по умолчанию); владелец может вернуть «как раньше»
    # (карточка просто ведёт на страницу товара, без «+»).
    normalized["quick_add"] = bool(config.get("quick_add", True))
    # A9: Kfz-Werkstatt — запрашивать структурные данные авто (Kennzeichen/HSN/TSN)
    # в Anfrage + AutoRepair-разметка. Дефолт False (Handwerker/прочие — без авто-полей).
    normalized["jobs_vehicle"] = bool(config.get("jobs_vehicle", False))
    # S4: стартовая страница витрины — "home" (общая главная, дефолт) либо ключ
    # архетипа (standalone: корень `/` ведёт на его лендинг). Валидность (активен
    # ли архетип) проверяется при рендере; здесь просто строка.
    normalized["storefront_root"] = _s(config.get("storefront_root")) or "home"
    # M20U-7 (per-page): раскладка сетки страницы каталога /sortiment/. Дефолт cols3
    # воспроизводит прежнюю захардкоженную сетку (grid-cols-2 lg:grid-cols-3).
    normalized["catalog_layout"] = normalize_layout(
        config.get("catalog_layout"), {"preset": "cols3"}
    )
    # M20U-7 (per-page): раскладка сетки номеров /unterkunft/. Дефолт cols3 mobile1
    # воспроизводит прежнюю сетку (grid-cols-1 sm:2 lg:3).
    normalized["stay_index_layout"] = normalize_layout(
        config.get("stay_index_layout"), {"preset": "cols3", "mobile": 1}
    )
    # M20U-7 (per-page): раскладка индекса событий /veranstaltung/. Дефолт list =
    # прежний вертикальный список (без регрессии); cols2/3 → сетка карточек.
    normalized["events_index_layout"] = normalize_layout(
        config.get("events_index_layout"), {"preset": "list"}
    )
    # M20U-4: порядок/видимость тематических секций детальной события.
    normalized["event_detail"] = normalize_event_detail(config.get("event_detail"))
    # M20U-7 (per-page): раскладка блока «похожие товары» на детальной. Дефолт
    # cols4 воспроизводит прежнюю сетку (grid-cols-2 lg:grid-cols-4).
    normalized["detail_related_layout"] = normalize_layout(
        config.get("detail_related_layout"), {"preset": "cols4"}
    )
    # M20U-7: кастомные заголовки секций главной (только известные ключи, обрезка).
    titles = config.get("section_titles")
    clean_titles = {}
    if isinstance(titles, dict):
        for key, value in titles.items():
            if key in SECTION_TITLE_KEYS and isinstance(value, str) and _s(value):
                clean_titles[key] = _s(value)[:_SECTION_TITLE_MAX]
    normalized["section_titles"] = clean_titles
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
