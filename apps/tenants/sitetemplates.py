"""Шаблоны витрины — ранний срез M20 (решение владельца 2026-06-15).

Шаблон = курируемый пресет `site_config` под тип бизнеса/архетип поверх
секционного движка Track C2 (`apps.tenants.siteconfig`): какие секции главной
включены и в каком порядке + готовые тексты hero/about. Это НЕ drag-drop
конструктор (тот — Stage 3): владелец выбирает готовую раскладку в один клик,
дальше тонко правит на той же странице «Site».

Применение (`apply_template`):
- переписывает раскладку секций (все известные секции выставляются явно —
  включённые из шаблона, прочие выключены; иначе `siteconfig.normalize` дописал
  бы недостающие со своим дефолтом и «вернул» бы их);
- тексты: НЕ затираем непустые значения владельца, пустые — заполняем дефолтом
  шаблона;
- состояние Onboarding-Wizard (тот же JSON) сохраняем.
"""

from . import siteconfig

# key · label · описание (DE) · recommended_for (типы бизнеса — рекомендация и
# сортировка; пусто = универсальный) · sections (включённые, в порядке показа) ·
# texts (дефолтные hero/about, подставляются только в пустые поля) · accent (hex
# → Tenant.primary_color) · hero_style (plain/accent — фон баннера).
TEMPLATES = [
    {
        "key": "laden",
        "label": "Klassischer Laden",
        "description_de": "Startbanner, aktuelle Angebote, Produkte, Über uns, Kontakt — der Allrounder für den Einzelhandel.",
        "recommended_for": ("bakery", "butcher", "grocery", "retail", "clothing", "online_shop"),
        "sections": ["hero", "promotions", "products", "about", "contact"],
        "texts": {
            "hero_title": "Willkommen",
            "hero_text": "Schön, dass Sie da sind. Entdecken Sie unsere aktuellen Angebote.",
            "about_title": "Über uns",
            "about_text": "",
        },
        "accent": "#4f46e5",  # indigo
        "hero_style": "accent",
    },
    {
        "key": "gastro",
        "label": "Café & Restaurant",
        "description_de": "Speisen und Angebote im Fokus, Öffnungszeiten prominent — für die Gastronomie.",
        "recommended_for": ("cafe", "restaurant"),
        "sections": ["hero", "products", "promotions", "contact"],
        "texts": {
            "hero_title": "Herzlich willkommen",
            "hero_text": "Unsere Karte und aktuelle Angebote — frisch für Sie.",
            "about_title": "",
            "about_text": "",
        },
        "accent": "#b45309",  # amber/warm
        "hero_style": "accent",
    },
    {
        "key": "dienstleister",
        "label": "Dienstleister & Termine",
        "description_de": "Vorstellung und Kontakt im Vordergrund — für Termin-Geschäfte (Friseur, Studio, Beratung).",
        # E2 «задача-первым»: tour_operator убран — его primary-задача (туры/
        # события с датами) обслуживает шаблон `veranstaltung` (events-first), а
        # не «about»-first dienstleister. Остаётся generic-фолбэком для «other».
        "recommended_for": ("other",),
        "sections": ["hero", "about", "promotions", "contact"],
        "texts": {
            "hero_title": "Ihr Termin bei uns",
            "hero_text": "Lernen Sie uns kennen und buchen Sie online Ihren Termin.",
            "about_title": "Über uns",
            "about_text": "",
        },
        "accent": "#0f766e",  # teal
        "hero_style": "accent",
    },
    {
        "key": "gastgeber",
        "label": "Übernachtung & Gastgeber",
        "description_de": "Verfügbarkeit, Zimmer, Lage und Kontakt — für Pension, Ferienwohnung oder kleines Hotel.",
        "recommended_for": ("hotel",),
        # «Задача-первым» (E1): date-search + карточки номеров сразу под hero —
        # главная задача гостя (свободно ли на мои даты) на первом экране. Секции
        # гейтятся модулем stays (неактивен → не рендерятся). Совпадает с демо-китом.
        "sections": ["hero", "stay_search", "stay_rooms", "about", "contact"],
        "texts": {
            "hero_title": "Willkommen bei uns",
            "hero_text": "Ihre Unterkunft für eine schöne Zeit — jetzt Verfügbarkeit prüfen.",
            "about_title": "Ihr Aufenthalt",
            "about_text": "",
        },
        "accent": "#0e7490",  # cyan/sea
        "hero_style": "accent",
    },
    {
        # S6: Friseur/Werkstatt — Termin + «Leistungen & Preise» (services) на главной.
        "key": "termine",
        "label": "Termine & Leistungen",
        "description_de": "Leistungen mit Preisen und Online-Termin im Fokus — für Friseur, Werkstatt und Studios.",
        "recommended_for": ("friseur", "werkstatt"),
        "sections": ["hero", "services", "about", "promotions", "contact"],
        "texts": {
            "hero_title": "Ihr Termin bei uns",
            "hero_text": "Sehen Sie unsere Leistungen und buchen Sie online Ihren Wunschtermin.",
            "about_title": "Über uns",
            "about_text": "",
        },
        "accent": "#0f766e",  # teal
        "hero_style": "accent",
    },
    {
        # S6: Handwerker — Anfrage/Angebot; Referenzen (before_after) + Ablauf (process).
        "key": "handwerk",
        "label": "Handwerk & Angebote",
        "description_de": "Referenzen, Ablauf und unverbindliches Angebot — für Meisterbetrieb, Sanierung und Montage.",
        "recommended_for": ("handwerker",),
        "sections": ["hero", "before_after", "process", "promotions", "contact"],
        "texts": {
            "hero_title": "Ihr Meisterbetrieb",
            "hero_text": "Schildern Sie Ihr Vorhaben — Sie erhalten ein unverbindliches Angebot.",
            "about_title": "Über den Betrieb",
            "about_text": "",
        },
        "accent": "#ea580c",  # Handwerk-Orange
        "hero_style": "accent",
    },
    {
        # S6: Veranstalter/Events — Tickets/Termine (events) im Fokus.
        "key": "veranstaltung",
        "label": "Veranstaltungen & Tickets",
        "description_de": "Kommende Termine und Tickets im Fokus — für Veranstalter, Guides und Studios.",
        "recommended_for": ("events", "tour_operator"),
        "sections": ["hero", "events", "about", "contact"],
        "texts": {
            "hero_title": "Unsere Veranstaltungen",
            "hero_text": "Sichern Sie sich jetzt Ihre Tickets für die nächsten Termine.",
            "about_title": "Über uns",
            "about_text": "",
        },
        "accent": "#7c3aed",  # violet
        "hero_style": "accent",
    },
    {
        "key": "minimal",
        "label": "Minimal / Visitenkarte",
        "description_de": "Schlichte Eine-Seite-Visitenkarte: Banner und Kontakt. Für alle, die es einfach mögen.",
        "recommended_for": (),  # универсальный
        "sections": ["hero", "contact"],
        "texts": {"hero_title": "", "hero_text": "", "about_title": "", "about_text": ""},
        "accent": "#111827",  # нейтральный графит
        "hero_style": "plain",  # минимал — белый баннер
    },
]

_BY_KEY = {t["key"]: t for t in TEMPLATES}

# ST-1 «Каталог Look'ов» (план st1-looks-plan-2026-07-19): Look = целостный
# визуальный образ = СЕМЕЙСТВО (шрифт/типографика/карточки/шапка/hero/тема) ×
# архетипный акцент (ARCHETYPE_LOOK_ACCENTS) × набор секций рекомендованного
# шаблона архетипа. 3 семейства × 14 архетипов = 42 Look'а из чистых данных.
LOOK_FAMILIES = [
    {
        "key": "klar",
        "label": "Klar",
        "description_de": "Hell und aufgeräumt — klare Flächen, ruhige Typografie.",
        "font": "system",
        "typography": {"weight_head": 0, "line_height": 0.0},  # дефолты витрины
        "site_defaults": {"card_radius": 0, "card_shadow": False, "card_bg": "", "card_padding": 0},
        "nav_style": "classic",
        "hero_style": "plain",
        "theme": "",
    },
    {
        "key": "warm",
        "label": "Warm",
        "description_de": "Serif-Überschriften, weiche Karten — einladend und persönlich.",
        "font": "serif",
        "typography": {"weight_head": 600, "line_height": 1.6},
        "site_defaults": {
            "card_radius": 16,
            "card_shadow": True,
            "card_bg": "",
            "card_padding": 0,
        },
        "nav_style": "centered",
        "hero_style": "accent",
        "theme": "",
    },
    {
        "key": "nacht",
        "label": "Nacht",
        "description_de": "Dunkler Auftritt mit kräftigen Überschriften — modern und markant.",
        "font": "system",
        "typography": {"weight_head": 800, "line_height": 0.0},
        "site_defaults": {
            "card_radius": 16,
            "card_shadow": True,
            "card_bg": "",
            "card_padding": 0,
        },
        "nav_style": "minimal",
        "hero_style": "accent",
        "theme": "dark",  # ST-1: site_config["theme"]="dark" (посетитель может переключить)
    },
]

_FAMILY_BY_KEY = {f["key"]: f for f in LOOK_FAMILIES}

# Акценты per-архетип: {business_type: (klar, warm, nacht)}. Nacht-тона светлее
# (контраст на тёмном фоне). Неизвестный тип → retail-палитра.
ARCHETYPE_LOOK_ACCENTS = {
    "bakery": ("#b45309", "#9a3412", "#f59e0b"),
    "butcher": ("#b91c1c", "#7f1d1d", "#f87171"),
    "grocery": ("#15803d", "#166534", "#4ade80"),
    "clothing": ("#111827", "#9d174d", "#e879f9"),
    "restaurant": ("#b45309", "#7c2d12", "#fbbf24"),
    "cafe": ("#92400e", "#78350f", "#fbbf24"),
    "retail": ("#4f46e5", "#1e40af", "#818cf8"),
    "online_shop": ("#4f46e5", "#0f766e", "#a78bfa"),
    "tour_operator": ("#0e7490", "#155e75", "#22d3ee"),
    "hotel": ("#0e7490", "#1e3a8a", "#38bdf8"),
    "friseur": ("#0f766e", "#9d174d", "#f472b6"),
    "handwerker": ("#ea580c", "#9a3412", "#fb923c"),
    "werkstatt": ("#1e40af", "#374151", "#60a5fa"),
    "events": ("#7c3aed", "#6d28d9", "#c084fc"),
}
_DEFAULT_ACCENTS = ARCHETYPE_LOOK_ACCENTS["retail"]


def get_template(key):
    return _BY_KEY.get(key)


def get_look_family(key):
    return _FAMILY_BY_KEY.get(key)


def look_accent(business_type, family_key) -> str:
    """Акцент Look'а для архетипа (неизвестный тип → retail-палитра)."""
    accents = ARCHETYPE_LOOK_ACCENTS.get(business_type, _DEFAULT_ACCENTS)
    idx = next((i for i, f in enumerate(LOOK_FAMILIES) if f["key"] == family_key), 0)
    return accents[idx]


def looks_for(business_type) -> list[dict]:
    """ST-1: 3 Look-карточки архетипа для галереи (мастер/билдер).

    Приёмка ТЗ «пекарь видит 3 пекарских Look'а первыми» выполняется по
    построению: каждый Look уже собран ПОД архетип (акцент+секции его шаблона).
    """
    return [
        {
            "key": f["key"],
            "label": f["label"],
            "description": f["description_de"],
            "accent": look_accent(business_type, f["key"]),
            "font": f["font"],
            "nav_style": f["nav_style"],
            "hero_style": f["hero_style"],
            "theme": f["theme"],
            "site_defaults": dict(f["site_defaults"]),
            "typography": dict(f["typography"]),
        }
        for f in LOOK_FAMILIES
    ]


def templates_for(business_type):
    """Шаблоны: рекомендованные типу — первыми, затем остальные (вкл. универсальные)."""
    recommended = [t for t in TEMPLATES if business_type in t["recommended_for"]]
    rest = [t for t in TEMPLATES if business_type not in t["recommended_for"]]
    return recommended + rest


def template_cards(business_type):
    """M20/AB6.2b: шаблоны сайта как карточки с мини-превью раскладки — акцент +
    стек секций (для рисованного мокапа) + бейдж «рекомендовано». Единый источник
    для конструктора «Site» и слайда «Stil» мастера (рекомендованные — первыми)."""
    from . import siteconfig

    labels = {key: label for key, label, _default in siteconfig.SECTIONS}
    return [
        {
            "key": t["key"],
            "label": t["label"],
            "description": t["description_de"],
            "recommended": business_type in t["recommended_for"],
            "sections": [{"key": s, "label": labels.get(s, s)} for s in t["sections"]],
            "accent": t.get("accent", ""),
            "hero_style": t.get("hero_style", "plain"),
        }
        for t in templates_for(business_type)
    ]


def _apply(tenant, template, *, family=None, accent=None) -> None:
    """Общее применение шаблона/Look'а к Tenant.site_config.

    ST-1 (исправлен латентный баг класса W6): база = ПОЛНАЯ копия текущего
    конфига — применение шаблона больше не стирает чужие ключи (ui_mode/board/
    seo/presence/page_blocks/menus/…). Переписываются только раскладка секций,
    пустые тексты, hero_style и — при family — пачка ключей Look'а.
    """
    current = siteconfig.normalize(tenant.site_config)
    config = dict(current)
    enabled = set(template["sections"])
    # Все известные секции явно: сначала включённые из шаблона (в его порядке),
    # затем прочие — выключенными.
    ordered = list(template["sections"])
    for sec_key, _label, _default in siteconfig.SECTIONS:
        if sec_key not in enabled:
            ordered.append(sec_key)
    config["sections"] = [{"key": k, "enabled": k in enabled} for k in ordered]
    for field in siteconfig.TEXT_FIELDS:
        # Непустой текст владельца не трогаем; пустой — заполняем дефолтом шаблона.
        config[field] = current.get(field) or template["texts"].get(field, "")
    config["hero_style"] = (family or template).get("hero_style", "plain")

    if family is not None:
        # ST-1: пачка ключей Look'а (все ключи уже существуют в normalize-схеме).
        config["font"] = family["font"]
        config["typography"] = dict(family["typography"])
        config["site_defaults"] = dict(family["site_defaults"])
        nav = dict(config.get("nav") or {})
        nav["style"] = family["nav_style"]
        config["nav"] = nav
        if family.get("theme") == "dark":
            config["theme"] = "dark"
        else:
            config.pop("theme", None)  # светлый Look снимает тёмный дефолт

    tenant.site_config = siteconfig.normalize(config)
    update_fields = ["site_config", "updated_at"]
    # Акцентный цвет → Tenant.primary_color (его читает витрина для hero).
    if accent:
        tenant.primary_color = accent
        update_fields.insert(1, "primary_color")
    tenant.save(update_fields=update_fields)


def apply_template(tenant, key) -> bool:
    """Применить шаблон к Tenant.site_config. False — неизвестный ключ."""
    template = get_template(key)
    if template is None:
        return False
    _apply(tenant, template, accent=template.get("accent"))
    return True


def apply_look(tenant, family_key) -> bool:
    """ST-1: применить Look (семейство × архетипный акцент × секции шаблона
    архетипа). False — неизвестное семейство. Идемпотентно (двойной normalize);
    чужие ключи конфига целы (_apply — полная копия)."""
    family = get_look_family(family_key)
    if family is None:
        return False
    business_type = getattr(tenant, "business_type", "") or "retail"
    template = templates_for(business_type)[0]  # рекомендованный архетипу первым
    _apply(tenant, template, family=family, accent=look_accent(business_type, family_key))
    return True
