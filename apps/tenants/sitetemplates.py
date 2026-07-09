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
        "recommended_for": ("bakery", "butcher", "grocery", "retail", "clothing"),
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
        "recommended_for": ("tour_operator", "other"),
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
        "description_de": "Vorstellung, Lage und Kontakt — für Pension, Ferienwohnung oder kleines Hotel.",
        "recommended_for": ("hotel",),
        "sections": ["hero", "about", "contact"],
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


def get_template(key):
    return _BY_KEY.get(key)


def templates_for(business_type):
    """Шаблоны: рекомендованные типу — первыми, затем остальные (вкл. универсальные)."""
    recommended = [t for t in TEMPLATES if business_type in t["recommended_for"]]
    rest = [t for t in TEMPLATES if business_type not in t["recommended_for"]]
    return recommended + rest


def apply_template(tenant, key) -> bool:
    """Применить шаблон к Tenant.site_config. False — неизвестный ключ."""
    template = get_template(key)
    if template is None:
        return False

    current = siteconfig.normalize(tenant.site_config)
    enabled = set(template["sections"])
    # Все известные секции явно: сначала включённые из шаблона (в его порядке),
    # затем прочие — выключенными.
    ordered = list(template["sections"])
    for sec_key, _label, _default in siteconfig.SECTIONS:
        if sec_key not in enabled:
            ordered.append(sec_key)

    config = {"sections": [{"key": k, "enabled": k in enabled} for k in ordered]}
    for field in siteconfig.TEXT_FIELDS:
        # Непустой текст владельца не трогаем; пустой — заполняем дефолтом шаблона.
        config[field] = current.get(field) or template["texts"].get(field, "")
    config["hero_style"] = template.get("hero_style", "plain")
    if isinstance(current.get("onboarding"), dict):
        config["onboarding"] = current["onboarding"]

    tenant.site_config = siteconfig.normalize(config)
    update_fields = ["site_config", "updated_at"]
    # Акцентный цвет шаблона → Tenant.primary_color (его читает витрина для hero).
    accent = template.get("accent")
    if accent:
        tenant.primary_color = accent
        update_fields.insert(1, "primary_color")
    tenant.save(update_fields=update_fields)
    return True
