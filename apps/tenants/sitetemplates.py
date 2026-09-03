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

from django.utils.translation import gettext_lazy as _

from apps.core import page_presets

from . import siteconfig

# key · label · описание (DE) · recommended_for (типы бизнеса — рекомендация и
# сортировка; пусто = универсальный) · sections (включённые, в порядке показа) ·
# texts (дефолтные hero/about, подставляются только в пустые поля) · accent (hex
# → Tenant.primary_color) · hero_style (plain/accent — фон баннера).
TEMPLATES = [
    {
        "key": "laden",
        "label": _("Klassischer Laden"),
        "description_de": _(
            "Startbanner, aktuelle Angebote, Produkte, Über uns, Kontakt — der Allrounder für den Einzelhandel."
        ),
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
        "label": _("Café & Restaurant"),
        "description_de": _(
            "Speisen und Angebote im Fokus, Öffnungszeiten prominent — für die Gastronomie."
        ),
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
        # Батч A «гастро-сплит» (концепт 2026-07-27): 2-3 плитки-входа В баннере
        # (Reservieren / Speisekarte / Angebot des Tages) — первый экран сразу
        # ведёт гостя к его задаче (как date-search у отеля, услуги у friseur).
        "site_defaults": {"hero_widget": "gastro"},
    },
    {
        "key": "dienstleister",
        "label": _("Dienstleister & Termine"),
        "description_de": _(
            "Vorstellung und Kontakt im Vordergrund — für Termin-Geschäfte (Friseur, Studio, Beratung)."
        ),
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
        "label": _("Übernachtung & Gastgeber"),
        "description_de": _(
            "Verfügbarkeit, Zimmer, Lage und Kontakt — für Pension, Ferienwohnung oder kleines Hotel."
        ),
        "recommended_for": ("hotel",),
        # «Задача-первым» (E4): поиск дат ВНУТРИ hero (site_defaults.hero_widget=
        # "stays") — первый экран сразу ведёт гостя к его задаче «свободно ли на
        # мои даты». Секция stay_search убрана (жила бы дублем к hero-виджету);
        # карточки номеров идут сразу под баннером. Гейт — модуль stays.
        "sections": ["hero", "stay_rooms", "about", "contact"],
        "site_defaults": {"hero_widget": "stays"},
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
        "label": _("Termine & Leistungen"),
        "description_de": _(
            "Leistungen mit Preisen und Online-Termin im Fokus — für Friseur, Werkstatt und Studios."
        ),
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
        # R2 «первый экран»: топ-услуги + «Termin buchen» ВНУТРИ баннера (услуги-
        # primary; services-секция и services_preview есть). Как hero_widget=stays
        # у отеля. Существующие сайты не трогаем (применяется дефолт-шаблоном).
        "site_defaults": {"hero_widget": "services"},
    },
    {
        # S6: Handwerker — Anfrage/Angebot; Referenzen (before_after) + Ablauf (process).
        "key": "handwerk",
        "label": _("Handwerk & Angebote"),
        "description_de": _(
            "Referenzen, Ablauf und unverbindliches Angebot — für Meisterbetrieb, Sanierung und Montage."
        ),
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
        # GK-1: Catering/Partyservice — jobs-primary (Anfrage → Angebot); Speisekarte
        # browse-only (catalog core, orders выключен пресетом), доверие/процесс/FAQ.
        "key": "catering",
        "label": _("Catering & Partyservice"),
        "description_de": _(
            "Anfrage, Angebot und Event-Planung — für Catering, Partyservice und Foodtrucks."
        ),
        "recommended_for": ("catering",),
        "sections": ["hero", "usp_bar", "products", "process", "testimonials", "faq", "contact"],
        "texts": {
            "hero_title": "Catering für Ihr Event",
            "hero_text": "Sagen Sie uns Datum und Gästezahl — Sie erhalten ein unverbindliches Angebot.",
            "about_title": "Über uns",
            "about_text": "",
        },
        "accent": "#15803d",  # frisch/bio-грин
        "hero_style": "accent",
        "site_defaults": {"hero_widget": "catering"},
    },
    {
        # S6: Veranstalter/Events — Tickets/Termine (events) im Fokus.
        "key": "veranstaltung",
        "label": _("Veranstaltungen & Tickets"),
        "description_de": _(
            "Kommende Termine und Tickets im Fokus — für Veranstalter, Guides und Studios."
        ),
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
        "label": _("Minimal / Visitenkarte"),
        "description_de": _(
            "Schlichte Eine-Seite-Visitenkarte: Banner und Kontakt. Für alle, die es einfach mögen."
        ),
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
# шаблона архетипа. 10 семейств × 15 архетипов = 150 Look'ов из чистых данных
# (ST-1: klar/warm/nacht · DS-1: fein/natur · DL-2: prospekt/frisch/neon/
# blatt/smart — deal-looks-wave-plan-2026-09-01).
LOOK_FAMILIES = [
    {
        "key": "klar",
        "label": _("Klar"),
        "description_de": _("Hell und aufgeräumt — klare Flächen, ruhige Typografie."),
        "font": "system",
        "typography": {"weight_head": 0, "line_height": 0.0},  # дефолты витрины
        "site_defaults": {"card_radius": 0, "card_shadow": False, "card_bg": "", "card_padding": 0},
        "nav_style": "classic",
        "hero_style": "plain",
        "theme": "",
    },
    {
        "key": "warm",
        "label": _("Warm"),
        "description_de": _("Serif-Überschriften, weiche Karten — einladend und persönlich."),
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
        "label": _("Nacht"),
        "description_de": _("Dunkler Auftritt mit kräftigen Überschriften — modern und markant."),
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
    # DS-1 (2026-08-12): семейства с ХАРАКТЕРОМ — self-hosted шрифт заголовков
    # (FONTS editorial/organic) + тёплая подложка страницы (site_defaults.page_bg).
    {
        "key": "fein",
        "label": _("Fein"),
        "description_de": _("Elegante Serif-Überschriften auf Creme — edel und ruhig."),
        "font": "editorial",  # Playfair Display 600 (latin/latin-ext/cyrillic)
        "typography": {"weight_head": 600, "line_height": 1.65},
        "site_defaults": {
            "card_radius": 20,
            "card_shadow": True,
            "card_bg": "#ffffff",
            "card_padding": 0,
            "page_bg": "#faf7f2",  # крем
        },
        "nav_style": "centered",
        "hero_style": "plain",
        "theme": "",
    },
    {
        "key": "natur",
        "label": _("Natur"),
        "description_de": _("Runde Formen und warme Erdtöne — freundlich und bodenständig."),
        "font": "organic",  # Nunito 800 (latin/latin-ext/cyrillic)
        "typography": {"weight_head": 800, "line_height": 1.6},
        "site_defaults": {
            "card_radius": 24,
            "card_shadow": True,
            "card_bg": "#ffffff",
            "card_padding": 0,
            "page_bg": "#f6f2e7",  # тёплый песок
        },
        "nav_style": "classic",
        "hero_style": "accent",
        "theme": "",
    },
    # DL-2 (2026-09-01): пять «акционных» семейств по утверждённому канвасу
    # «Sparfuchs Aktionsmarkt Redesign». Новая ось site_defaults.card_chrome
    # (hard/hairline/line) — рамка/тень карточек, presence-minimal.
    {
        "key": "prospekt",
        "label": _("Prospekt"),
        "description_de": _(
            "Discounter-Energie: Preis-Sticker, kräftige Rahmen, plakative Schrift."
        ),
        "font": "condensed",  # Barlow Condensed 700 (latin/latin-ext)
        "typography": {"weight_head": 700, "line_height": 1.45},
        "site_defaults": {
            "card_radius": 0,
            "card_shadow": False,
            "card_bg": "#ffffff",
            "card_padding": 0,
            "card_chrome": "hard",
        },
        "nav_style": "classic",
        "hero_style": "split",
        "theme": "",
    },
    {
        "key": "frisch",
        "label": _("Frischmarkt"),
        "description_de": _("Warmer Markt von nebenan: Creme, weiche Karten, viel Luft."),
        "font": "bricolage",  # Bricolage Grotesque 700
        "typography": {"weight_head": 700, "line_height": 1.6},
        "site_defaults": {
            "card_radius": 20,
            "card_shadow": True,
            "card_bg": "#ffffff",
            "card_padding": 0,
            "page_bg": "#faf6ef",  # крем-подложка канваса V2
        },
        "nav_style": "classic",
        "hero_style": "split",
        "theme": "",
    },
    {
        "key": "neon",
        "label": _("Nachtmarkt"),
        "description_de": _("Dunkler Deal-Jäger: Neon-Preise, große Timer, maximaler Kontrast."),
        "font": "space",  # Space Grotesk 700
        "typography": {"weight_head": 700, "line_height": 1.5},
        "site_defaults": {
            "card_radius": 14,
            "card_shadow": False,
            "card_bg": "",
            "card_padding": 0,
            "card_chrome": "line",
        },
        "nav_style": "classic",
        "hero_style": "split",
        "theme": "dark",
    },
    {
        "key": "blatt",
        "label": _("Markthalle"),
        "description_de": _("Wochenzeitung der guten Preise: Serifen, Papier, feine Linien."),
        "font": "editorial",  # Playfair Display 600 (реюз DS-1)
        "typography": {"weight_head": 600, "line_height": 1.65},
        "site_defaults": {
            "card_radius": 0,
            "card_shadow": False,
            "card_bg": "#ffffff",
            "card_padding": 0,
            "page_bg": "#f7f5f0",  # бумага канваса V4
            "card_chrome": "hairline",
        },
        "nav_style": "centered",
        "hero_style": "split",
        "theme": "",
    },
    {
        "key": "smart",
        "label": _("Marktplatz"),
        "description_de": _("Nüchtern und dicht: Prozent zuerst, klare Listen, volle Übersicht."),
        "font": "schibsted",  # Schibsted Grotesk 700
        "typography": {"weight_head": 700, "line_height": 1.5},
        "site_defaults": {
            "card_radius": 12,
            "card_shadow": False,
            "card_bg": "#ffffff",
            "card_padding": 0,
            "page_bg": "#f4f6f9",  # холодный светлый фон канваса V5
            "card_chrome": "line",
        },
        "nav_style": "classic",
        "hero_style": "plain",
        "theme": "",
    },
    # DL-13 (2026-09-02): шесть направлений канваса «Neue Design-Richtungen»
    # (решение владельца) — кожа; композиции несут сборки deal_* (H3/H6/H2/H4/H5).
    {
        "key": "monochrom",
        "label": _("Monochrom"),
        "description_de": _("Schwarz-Weiß-Typografie, Farbe nur beim Preis: ehrlich und ruhig."),
        "font": "archivo",  # Archivo 700
        "typography": {"weight_head": 700, "line_height": 1.4},
        "site_defaults": {
            "card_radius": 0,
            "card_shadow": False,
            "card_bg": "#ffffff",
            "card_padding": 0,
            "page_bg": "#ffffff",
            "card_chrome": "line",
        },
        "nav_style": "minimal",
        "hero_style": "plain",
        "theme": "",
    },
    {
        "key": "pastell",
        "label": _("Pastell"),
        "description_de": _("Weiche Kacheln und runde Ecken — freundlich, für Familien und Bio."),
        "font": "quicksand",  # Quicksand 700
        "typography": {"weight_head": 700, "line_height": 1.6},
        "site_defaults": {
            "card_radius": 22,
            "card_shadow": True,
            "card_bg": "#ffffff",
            "card_padding": 0,
            "page_bg": "#fbf6f8",
        },
        "nav_style": "classic",
        "hero_style": "split",
        "theme": "",
    },
    {
        "key": "retro",
        "label": _("Retro"),
        "description_de": _("Plakat der 70er: Ocker, Stempel-Badges, kräftige Slab-Schrift."),
        "font": "alfaslab",  # Alfa Slab One 400
        "typography": {"weight_head": 400, "line_height": 1.5},
        "site_defaults": {
            "card_radius": 6,
            "card_shadow": True,
            "card_bg": "#fffdf7",
            "card_padding": 0,
            "page_bg": "#f6efe1",
            "card_chrome": "hard",
        },
        "nav_style": "classic",
        "hero_style": "accent",
        "theme": "",
    },
    {
        "key": "nobel",
        "label": _("Nobel"),
        "description_de": _("Dunkel, Gold-Haarlinie, Antiqua — Feinkost, Wein, Delikatessen."),
        "font": "cormorant",  # Cormorant Garamond 600
        "typography": {"weight_head": 600, "line_height": 1.7},
        "site_defaults": {
            "card_radius": 0,
            "card_shadow": False,
            "card_bg": "",
            "card_padding": 0,
            "card_chrome": "hairline",
        },
        "nav_style": "centered",
        "hero_style": "split",
        "theme": "dark",
    },
    {
        "key": "foto",
        "label": _("Foto"),
        "description_de": _("Bilder im Vollformat, Glas-Karten darüber — für starke eigene Fotos."),
        "font": "manrope",  # Manrope 800
        "typography": {"weight_head": 800, "line_height": 1.5},
        "site_defaults": {
            "card_radius": 22,
            "card_shadow": False,
            "card_bg": "#ffffff",
            "card_padding": 0,
            "page_bg": "#ffffff",
        },
        "nav_style": "classic",
        "hero_style": "fullscreen",
        "theme": "",
    },
    {
        "key": "bauhaus",
        "label": _("Bauhaus"),
        "description_de": _("Schwarzes Raster, drei reine Farben, Geometrie — Concept-Store."),
        "font": "archivo_black",  # Archivo Black 400
        "typography": {"weight_head": 400, "line_height": 1.4},
        "site_defaults": {
            "card_radius": 0,
            "card_shadow": False,
            "card_bg": "#ffffff",
            "card_padding": 0,
            "page_bg": "#f4f1ea",
            "card_chrome": "hard",
        },
        "nav_style": "classic",
        "hero_style": "bento",
        "theme": "",
    },
]

_FAMILY_BY_KEY = {f["key"]: f for f in LOOK_FAMILIES}

# Акценты per-архетип: {business_type: (klar, warm, nacht, fein, natur,
# prospekt, frisch, neon, blatt, smart, monochrom, pastell, retro, nobel, foto,
# bauhaus)} — ПОЗИЦИОННО, порядок = LOOK_FAMILIES.
# Nacht/neon-тона светлее (контраст на тёмном); fein/blatt — глубокие
# благородные; natur/frisch — травяные/земляные; prospekt — «продажный»
# красно-оранжевый жанра проспекта; smart — функциональный синий (DL-2).
ARCHETYPE_LOOK_ACCENTS = {
    # fmt: off
    "bakery": (
        "#b45309",
        "#9a3412",
        "#f59e0b",
        "#7c2d12",
        "#a16207",
        "#dc2626",
        "#a16207",
        "#f59e0b",
        "#7c2d12",
        "#1d4ed8",
        # DL-13: monochrom · pastell · retro · nobel · foto · bauhaus
        "#b45309",
        "#c08457",
        "#b45309",
        "#b8860b",
        "#3f2a14",
        "#d62828",
    ),
    "butcher": (
        "#b91c1c",
        "#7f1d1d",
        "#f87171",
        "#7f1d1d",
        "#92400e",
        "#dc2626",
        "#92400e",
        "#f87171",
        "#7f1d1d",
        "#1d4ed8",
        # DL-13: monochrom · pastell · retro · nobel · foto · bauhaus
        "#b91c1c",
        "#b5567a",
        "#9a3412",
        "#b08d57",
        "#3b0a0a",
        "#d62828",
    ),
    "grocery": (
        "#15803d",
        "#166534",
        "#4ade80",
        "#14532d",
        "#4d7c0f",
        "#dc2626",
        "#2e6b3c",
        "#c8f542",
        "#b3202c",
        "#1d4ed8",
        # DL-13: monochrom · pastell · retro · nobel · foto · bauhaus
        "#dc2626",
        "#b5567a",
        "#c2410c",
        "#c6a15b",
        "#17181c",
        "#d62828",
    ),
    "clothing": (
        "#111827",
        "#9d174d",
        "#e879f9",
        "#1c1917",
        "#78716c",
        "#b91c1c",
        "#78716c",
        "#e879f9",
        "#1c1917",
        "#1d4ed8",
        # DL-13: monochrom · pastell · retro · nobel · foto · bauhaus
        "#be123c",
        "#7c6fb0",
        "#7c2d12",
        "#c9a96e",
        "#17181c",
        "#1d3f9e",
    ),
    "restaurant": (
        "#b45309",
        "#7c2d12",
        "#fbbf24",
        "#7c2d12",
        "#4d7c0f",
        "#dc2626",
        "#4d7c0f",
        "#fbbf24",
        "#7c2d12",
        "#1d4ed8",
        # DL-13: monochrom · pastell · retro · nobel · foto · bauhaus
        "#b91c1c",
        "#b5567a",
        "#9a3412",
        "#c6a15b",
        "#2a1a12",
        "#d62828",
    ),
    "cafe": (
        "#92400e",
        "#78350f",
        "#fbbf24",
        "#713f12",
        "#a16207",
        "#dc2626",
        "#a16207",
        "#fbbf24",
        "#713f12",
        "#1d4ed8",
        # DL-13: monochrom · pastell · retro · nobel · foto · bauhaus
        "#92400e",
        "#a0715e",
        "#92400e",
        "#b8860b",
        "#2b1d16",
        "#1d3f9e",
    ),
    "retail": (
        "#4f46e5",
        "#1e40af",
        "#818cf8",
        "#312e81",
        "#0f766e",
        "#dc2626",
        "#0f766e",
        "#a3e635",
        "#312e81",
        "#1d4ed8",
        # DL-13: monochrom · pastell · retro · nobel · foto · bauhaus
        "#1d4ed8",
        "#6f8fb5",
        "#a16207",
        "#c0a062",
        "#17181c",
        "#1d3f9e",
    ),
    "online_shop": (
        "#4f46e5",
        "#0f766e",
        "#a78bfa",
        "#312e81",
        "#0f766e",
        "#dc2626",
        "#0f766e",
        "#a78bfa",
        "#312e81",
        "#1d4ed8",
        # DL-13: monochrom · pastell · retro · nobel · foto · bauhaus
        "#1d4ed8",
        "#6f8fb5",
        "#a16207",
        "#c0a062",
        "#17181c",
        "#1d3f9e",
    ),
    "tour_operator": (
        "#0e7490",
        "#155e75",
        "#22d3ee",
        "#164e63",
        "#15803d",
        "#c2410c",
        "#15803d",
        "#22d3ee",
        "#164e63",
        "#1d4ed8",
        # DL-13: monochrom · pastell · retro · nobel · foto · bauhaus
        "#0e7490",
        "#5b9aa0",
        "#7c5e10",
        "#b39a5c",
        "#0f2f3a",
        "#1d3f9e",
    ),
    "hotel": (
        "#0e7490",
        "#1e3a8a",
        "#38bdf8",
        "#1e3a8a",
        "#166534",
        "#c2410c",
        "#166534",
        "#38bdf8",
        "#1e3a8a",
        "#1d4ed8",
        # DL-13: monochrom · pastell · retro · nobel · foto · bauhaus
        "#1e40af",
        "#7a8fb5",
        "#854d0e",
        "#c6a15b",
        "#12233a",
        "#1d3f9e",
    ),
    "friseur": (
        "#0f766e",
        "#9d174d",
        "#f472b6",
        "#831843",
        "#0f766e",
        "#db2777",
        "#0f766e",
        "#f472b6",
        "#831843",
        "#1d4ed8",
        # DL-13: monochrom · pastell · retro · nobel · foto · bauhaus
        "#9d174d",
        "#b57a9a",
        "#9f1239",
        "#cdb07a",
        "#2a1229",
        "#d62828",
    ),
    "handwerker": (
        "#ea580c",
        "#9a3412",
        "#fb923c",
        "#7c2d12",
        "#92400e",
        "#ea580c",
        "#92400e",
        "#fb923c",
        "#7c2d12",
        "#1d4ed8",
        # DL-13: monochrom · pastell · retro · nobel · foto · bauhaus
        "#c2410c",
        "#8a9a6f",
        "#78350f",
        "#b39a5c",
        "#1f2937",
        "#f2c230",
    ),
    "werkstatt": (
        "#1e40af",
        "#374151",
        "#60a5fa",
        "#1e3a8a",
        "#374151",
        "#ea580c",
        "#374151",
        "#60a5fa",
        "#1e3a8a",
        "#1d4ed8",
        # DL-13: monochrom · pastell · retro · nobel · foto · bauhaus
        "#1d4ed8",
        "#6f8fb5",
        "#7c2d12",
        "#a89060",
        "#17181c",
        "#1d3f9e",
    ),
    "events": (
        "#7c3aed",
        "#6d28d9",
        "#c084fc",
        "#581c87",
        "#6d28d9",
        "#db2777",
        "#6d28d9",
        "#c084fc",
        "#581c87",
        "#1d4ed8",
        # DL-13: monochrom · pastell · retro · nobel · foto · bauhaus
        "#6d28d9",
        "#9a7ab5",
        "#b45309",
        "#c6a15b",
        "#1e1b4b",
        "#d62828",
    ),
    # GK-1: frisch/bio-грин + тёплый warm
    "catering": (
        "#15803d",
        "#b45309",
        "#4ade80",
        "#166534",
        "#4d7c0f",
        "#dc2626",
        "#2e6b3c",
        "#c8f542",
        "#166534",
        "#1d4ed8",
        # DL-13: monochrom · pastell · retro · nobel · foto · bauhaus
        "#15803d",
        "#6fa08a",
        "#6b7a1e",
        "#b8a06a",
        "#14301f",
        "#1d3f9e",
    ),
    # fmt: on
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
    """Шаблоны: рекомендованные типу + универсальные (пустой recommended_for).

    DL-7a (фидбэк владельца): чужие отраслевые пресеты («посторонние шаблоны»
    в Studio и мастере) больше не показываются — их Apply менял раскладку
    секций под чужой архетип и выглядел как «тема не применилась»."""
    recommended = [t for t in TEMPLATES if business_type in t["recommended_for"]]
    universal = [t for t in TEMPLATES if not t["recommended_for"]]
    return recommended + universal


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
    конфига — применение шаблона больше не стирает чужие ключи (board/
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
        # Look = ВИЗУАЛЬНАЯ тема (card-стиль семейства). hero_widget — не визуал,
        # а выбор раскладки первого экрана (E4): сохраняем существующий выбор
        # тенанта, чтобы смена Look'а не сбрасывала date-search-в-hero.
        fam_sd = dict(family["site_defaults"])
        prev_hw = (current.get("site_defaults") or {}).get("hero_widget")
        if prev_hw in ("stays", "services", "gastro"):
            fam_sd["hero_widget"] = prev_hw
        config["site_defaults"] = fam_sd
        nav = dict(config.get("nav") or {})
        nav["style"] = family["nav_style"]
        config["nav"] = nav
        if family.get("theme") == "dark":
            config["theme"] = "dark"
        else:
            config.pop("theme", None)  # светлый Look снимает тёмный дефолт

    # E4 «задача-первым»: ПРИ ВЫБОРЕ ШАБЛОНА (не Look'а) переносим его витринные
    # дефолты (напр. интерактивный hero отеля hero_widget="stays"). В пути Look'а
    # НЕ трогаем (там site_defaults = card-стиль семейства + сохранённый hero_widget
    # выше) — иначе смена Look ломала бы контракт «site_defaults == семейство».
    tpl_sd = template.get("site_defaults")
    if family is None and tpl_sd:
        config["site_defaults"] = {**(config.get("site_defaults") or {}), **tpl_sd}

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


# DS-3c (Fokus): СБОРКИ (Startpakete) — «Look + виды вывода одним кликом».
# Сборка = данные поверх осей: кожа (look) + композиция (hero_style/nav.cta) +
# виды вывода (стили секций, страничные пресеты) + включение секций. Владелец
# дальше меняет любую ось по отдельности — сборка лишь стартовая комбинация.
# Общая ДНК всех сборок «Fokus» (DS-3c → DS-8): одно главное действие на экран —
# сплит-баннер, CTA-кнопка в шапке, компакт-полоса доверия, чистая главная.
_FOKUS_BASE = {
    "hero_style": "split",
    "nav_cta": True,
    # DS-9: плитки задач в баннере снимаются ("none" = явное снятие; отель и
    # сервисные архетипы переопределяют своим ФУНКЦИОНАЛЬНЫМ виджетом —
    # поиск дат / топ-услуги с кнопкой записи).
    "hero_widget": "none",
    # DS-9: шапка Fokus — одной строкой «лого | меню | CTA».
    "nav_style": "classic",
    "section_styles": {"trust": "compact"},
    "sections_on": ("trust",),
    # Отключаем «шумные» секции — у Fokus главная ведёт к ОДНОМУ действию;
    # контент остаётся на своих страницах (галерея/команда/отзывы — ST-8).
    "sections_off": ("archetypes", "usp_bar", "team", "gallery", "reviews", "testimonials"),
}


def _fokus(extra: dict) -> dict:
    """Сборка Fokus: общая ДНК + архетипные отличия (виды вывода/виджет hero)."""
    cfg = {
        **_FOKUS_BASE,
        **{
            k: v
            for k, v in extra.items()
            if k not in ("section_styles", "sections_on", "sections_off")
        },
    }
    cfg["section_styles"] = {**_FOKUS_BASE["section_styles"], **extra.get("section_styles", {})}
    cfg["sections_on"] = tuple(_FOKUS_BASE["sections_on"]) + tuple(extra.get("sections_on", ()))
    cfg["sections_off"] = tuple(
        k for k in _FOKUS_BASE["sections_off"] if k not in cfg["sections_on"]
    ) + tuple(extra.get("sections_off", ()))
    return cfg


# DL-9b: ДНК ДИЛ-шаблонов (волна DL) — отдельная от Fokus: у акционного сайта
# главный контент не «одно действие», а сами акции, поэтому trust не форсится,
# а состав и ПОРЯДОК блоков каждая сборка задаёт сама (ось sections_order).
# Общий знаменатель: CTA в шапке, плитки задач сняты, «шумные» разделы (команда/
# галерея/портфолио/лендинги других модулей) выключены — их место занимает
# композиция конкретного шаблона.
_DEAL_BASE = {
    "nav_cta": True,
    "hero_widget": "none",
    # DL-16.4 (решение владельца): карточка акции «Preis zuerst» — дефолт всех дил-сборок.
    "promo_card": "preis",
    # DL-13 C3: режим страницы акций — часть композиции; сброс, если сборка
    # не задаёт «по времени» явно (иначе Retro «протёк» бы в следующую сборку).
    "promo_grouping": "",
    "sections_off": (
        "archetypes",
        "team",
        "gallery",
        "reviews",
        "before_after",
        "blog",
        "services",
        "events",
        "tours",
        "stay_search",
        "stay_rooms",
        "finder",
        "anfrage",
        "cta",
    ),
}


def _deal(extra: dict) -> dict:
    """Дил-сборка: общая ДНК + СВОЯ композиция (набор/порядок/виды блоков).

    Всё, что сборка не включила явно, гасится: иначе пять шаблонов снова
    сползлись бы в одну страницу с разными цветами (фидбэк 2026-09-01)."""
    cfg = {
        **_DEAL_BASE,
        **{
            k: v
            for k, v in extra.items()
            if k not in ("section_styles", "sections_on", "sections_off")
        },
    }
    cfg["section_styles"] = dict(extra.get("section_styles", {}))
    cfg["sections_on"] = tuple(extra.get("sections_on", ()))
    # Гасим всё остальное известное — кроме включённого этой сборкой и hero
    # (его судьбу сборка решает явно через sections_on/sections_off).
    known = {key for key, _label, _default in siteconfig.SECTIONS}
    always_keep = {"contact"}  # контакты/часы — на всех дил-шаблонах
    off = (
        set(_DEAL_BASE["sections_off"])
        | (known - set(cfg["sections_on"]) - always_keep)
        | set(extra.get("sections_off", ()))
    ) - set(cfg["sections_on"])
    cfg["sections_off"] = tuple(sorted(off))
    return cfg


# DL-13 (анализ DL-12 §4.1): семейства КОМПОЗИЦИЙ главной — подпись на карточке
# сборки в Design/мастере, чтобы шаблоны различались для владельца «по смыслу»,
# а не только по цвету. Ключ → человеческая метка; сборка несёт "composition".
COMPOSITIONS = {
    "fokus": _("Fokus: Kategorien → Sortiment → Vertrauen"),
    "prospekt": _("Prospekt: Aktionen zuerst"),
    "sortiment": _("Sortiment zuerst, ohne Banner"),
    "magazin": _("Magazin: Geschichte & Bilder"),
    "vollbild": _("Vollbild-Foto mit Angebot des Tages"),
    "bento": _("Bento: Kacheln-Mosaik als erster Bildschirm"),
}


def composition_label(bundle: dict) -> str:
    """Подпись композиции сборки ("" — у сборки нет ключа/неизвестный)."""
    return str(COMPOSITIONS.get(bundle.get("composition", ""), ""))


BUNDLES = [
    {
        # Сервисный «цена + заявка» — прайс и форма прямо на главной (catering).
        "key": "fokus",
        "label": _("Fokus"),
        "description_de": _(
            "Ein Hauptziel pro Bildschirm: Split-Banner, Preisliste, "
            "Anfrage direkt auf der Startseite."
        ),
        "recommended_for": ("catering",),
        "look": "klar",
        "config": _fokus(
            {
                "catalog_layout": {"preset": "preisliste"},
                "section_styles": {"products": "preisliste"},
                "sections_on": ("products", "anfrage"),
            }
        ),
    },
    {
        # DS-8: отель — «свободно ли на мои даты»: поиск ВНУТРИ баннера.
        "key": "fokus_hotel",
        "label": _("Fokus"),
        "description_de": _(
            "Ein Hauptziel pro Bildschirm: Split-Banner mit Datumssuche, "
            "Zimmer direkt darunter, kompaktes Vertrauensband."
        ),
        "recommended_for": ("hotel",),
        "look": "klar",
        "config": _fokus(
            {
                "hero_widget": "stays",
                "sections_on": ("stay_rooms",),
                "sections_off": ("stay_search",),
            }
        ),
    },
    {
        # DS-8: ресторан — печатная карта + бронь стола.
        "key": "fokus_gastro",
        "label": _("Fokus"),
        "description_de": _(
            "Ein Hauptziel pro Bildschirm: Split-Banner, klassische Speisekarte, "
            "Tisch-Reservierung immer sichtbar."
        ),
        "recommended_for": ("restaurant",),
        "look": "klar",
        "config": _fokus(
            {
                "catalog_layout": {"preset": "preisliste_karte"},
                "section_styles": {"products": "preisliste_karte"},
                "sections_on": ("products",),
            }
        ),
    },
    {
        # DS-8: кафе — много позиций: компакт на главной, фото-прайс на странице.
        "key": "fokus_cafe",
        "label": _("Fokus"),
        "description_de": _(
            "Ein Hauptziel pro Bildschirm: Split-Banner, kompakte Karte auf der "
            "Startseite, Speisekarte mit Fotos."
        ),
        "recommended_for": ("cafe",),
        "look": "klar",
        "config": _fokus(
            {
                "catalog_layout": {"preset": "preisliste_foto"},
                "section_styles": {"products": "preisliste_kompakt"},
                "sections_on": ("products",),
            }
        ),
    },
    {
        # DS-8: пекарня — направления плитками + прайс с фото («глазами выбирают»).
        "key": "fokus_bakery",
        "label": _("Fokus"),
        "description_de": _(
            "Ein Hauptziel pro Bildschirm: Split-Banner, Sortiment-Kacheln und "
            "Preisliste mit Fotos."
        ),
        "recommended_for": ("bakery",),
        "look": "klar",
        "config": _fokus(
            {
                "catalog_layout": {"preset": "preisliste_foto"},
                "section_styles": {"products": "preisliste_foto", "categories": "compact"},
                "sections_on": ("categories", "products"),
            }
        ),
    },
    {
        # DS-9: мясная лавка — витрина «прилавок»: направления + прайс с фото +
        # Partyservice-заявка (jobs у Metzgerei активен) прямо на главной.
        "key": "fokus_theke",
        "label": _("Fokus"),
        "description_de": _(
            "Ein Hauptziel pro Bildschirm: Theken-Sortiment mit Fotos und "
            "Partyservice-Anfrage direkt auf der Startseite."
        ),
        "recommended_for": ("butcher",),
        "look": "klar",
        "config": _fokus(
            {
                "catalog_layout": {"preset": "preisliste_foto"},
                "section_styles": {"products": "preisliste_foto", "categories": "compact"},
                "sections_on": ("categories", "products", "anfrage"),
            }
        ),
    },
    {
        # DS-9: Friseur — «Termin-Fokus»: топ-услуги В баннере, прайс услуг,
        # МАСТЕРА остаются (у салона доверие — это люди), затем доверие.
        "key": "fokus_termin",
        "label": _("Fokus"),
        "description_de": _(
            "Ein Hauptziel pro Bildschirm: Leistungen mit Preisen im Banner, "
            "Team und Termin-Buchung immer sichtbar."
        ),
        "recommended_for": ("friseur",),
        "look": "klar",
        "config": _fokus(
            {
                "hero_widget": "services",
                "sections_on": ("services", "team"),
            }
        ),
    },
    {
        # DS-9: Werkstatt — «Ablauf-Fokus»: услуги с фикс-ценой + понятный
        # процесс (Termin → Diagnose → Abholung) + заявка на смету.
        "key": "fokus_werkstatt",
        "label": _("Fokus"),
        "description_de": _(
            "Ein Hauptziel pro Bildschirm: Festpreis-Leistungen, klarer Ablauf "
            "und Kostenvoranschlag-Anfrage."
        ),
        "recommended_for": ("werkstatt",),
        "look": "klar",
        "config": _fokus(
            {
                "hero_widget": "services",
                "section_styles": {"process": "row"},
                "sections_on": ("services", "process", "anfrage"),
            }
        ),
    },
    {
        # DS-9: Handwerker — «Referenz-Fokus»: доверие через РАБОТЫ (до/после),
        # затем ход работы и заявка. Прайса нет — цена всегда индивидуальна.
        "key": "fokus_referenz",
        "label": _("Fokus"),
        "description_de": _(
            "Ein Hauptziel pro Bildschirm: Referenzen vorher/nachher, klarer "
            "Ablauf und Angebots-Anfrage."
        ),
        "recommended_for": ("handwerker",),
        "look": "klar",
        "config": _fokus(
            {
                "section_styles": {"process": "timeline"},
                "sections_on": ("before_after", "process", "anfrage"),
            }
        ),
    },
    {
        # DS-9: продуктовый/акционный магазин — «Angebots-Fokus»: скидки ПЕРВЫМИ
        # (магазин у дома живёт предложениями), затем направления.
        "key": "fokus_angebote",
        "label": _("Fokus"),
        "description_de": _(
            "Ein Hauptziel pro Bildschirm: aktuelle Angebote ganz oben, Sortiment-Kacheln darunter."
        ),
        "recommended_for": ("grocery",),
        "look": "klar",
        "config": _fokus(
            {
                "section_styles": {"categories": "compact"},
                "sections_on": ("promotions", "categories"),
            }
        ),
    },
    {
        # DS-9: розница/онлайн-магазин — «Sortiment-Fokus»: направления крупными
        # плитками + товары КАРТОЧКАМИ (фото+цена+кнопка) + полоса преимуществ
        # (доставка/оплата/возврат — конверсия онлайн-покупки).
        "key": "fokus_sortiment",
        "label": _("Fokus"),
        "description_de": _(
            "Ein Hauptziel pro Bildschirm: Sortiment-Kacheln, Produkte als Karten "
            "und Versand-Vorteile auf einen Blick."
        ),
        "recommended_for": ("retail", "online_shop", "other"),
        "look": "klar",
        "config": _fokus(
            {
                "section_styles": {"categories": "square", "usp_bar": "compact"},
                "sections_on": ("categories", "products", "usp_bar"),
            }
        ),
    },
    {
        # DS-9: мода — «Lookbook-Fokus»: картинка правит. Вертикальные плитки
        # направлений, карточки-оверлеи, галерея образов остаётся.
        "key": "fokus_lookbook",
        "label": _("Fokus"),
        "description_de": _(
            "Ein Hauptziel pro Bildschirm: große Bilder, Kollektionen als Kacheln "
            "und Lookbook-Galerie."
        ),
        "recommended_for": ("clothing",),
        "look": "klar",
        "config": _fokus(
            {
                "card_style": "lookbook",  # DL-19: у сборки «Lookbook» — своя форма карточки
                "section_styles": {"categories": "tall", "gallery": "large"},
                "sections_on": ("categories", "products", "gallery"),
            }
        ),
    },
    {
        # DS-9: события/ретриты — «Programm-Fokus»: ближайшие даты афишей,
        # затем «как проходит» и доверие.
        "key": "fokus_programm",
        "label": _("Fokus"),
        "description_de": _(
            "Ein Hauptziel pro Bildschirm: kommende Termine als Programm, "
            "Ablauf und Stimmen der Gäste."
        ),
        "recommended_for": ("events",),
        "look": "klar",
        "config": _fokus(
            {
                "section_styles": {"process": "timeline"},
                "sections_on": ("events", "process"),
            }
        ),
    },
    {
        # DS-9: туры — «Touren-Fokus»: даты + ФОТО маршрутов (галерея продаёт
        # тур сильнее текста). MT-F2: главный товар тур-оператора — ПОЕЗДКА
        # (`tours`): даты видны прямо в её карточке («2 Termine · ab 1490 €»),
        # поэтому отдельную секцию заездов сборка НЕ включает — это был бы тот
        # же список дат второй раз, но без маршрута и фото. Заявка на приватный
        # выезд — сразу на главной (гейт модуля jobs внутри партиала).
        "key": "fokus_touren",
        "label": _("Fokus"),
        "description_de": _(
            "Ein Hauptziel pro Bildschirm: Reisen mit Bildern, Termine und "
            "Anfrage für die eigene Gruppe."
        ),
        "recommended_for": ("tour_operator",),
        "look": "klar",
        "config": _fokus(
            {
                "section_styles": {"gallery": "strip"},
                "sections_on": ("tours", "gallery", "anfrage"),
            }
        ),
    },
    # DL-3 (волна DL): пять «дил-шаблонов» по утверждённому канвасу «Sparfuchs
    # Aktionsmarkt Redesign» — в отличие от архетипных «Fokus» это УНИВЕРСАЛЬНЫЕ
    # полноценные шаблоны (пустой recommended_for → видны всем типам): кожу даёт
    # Look-семейство DL-2 (label/description реюзятся оттуда же — msgid одни),
    # композицию — оси Fokus-ДНК + акции первыми (spotlight/rows) + направления
    # компактно + страничные пресеты ST-2 («О нас»/корзина).
    {
        "key": "deal_prospekt",
        "composition": "prospekt",  # DL-13: семейство композиции (COMPOSITIONS)
        "label": _("Prospekt"),
        "description_de": _(
            "Discounter-Energie: Preis-Sticker, kräftige Rahmen, plakative Schrift."
        ),
        "recommended_for": (),
        "look": "prospekt",
        # V1: плакат-листовка — красная плита, ленты категорий, крупный дил,
        # «как это работает» строкой и полоса преимуществ. Без рассказов о себе.
        "config": _deal(
            {
                "section_layouts": {"categories": {"preset": "cols3"}},  # DL-11: 6 = 2×3
                "hero_style": "accent",
                "nav_style": "classic",
                "sections_on": ("hero", "categories", "promotions", "process", "usp_bar"),
                "sections_order": (
                    "hero",
                    "categories",
                    "promotions",
                    "process",
                    "usp_bar",
                    "contact",
                ),
                "section_styles": {
                    "categories": "compact",
                    "promotions": "spotlight",
                    "process": "row",
                    "usp_bar": "compact",
                    "contact": "compact",
                },
                "page_presets": {"info": "bild", "cart": "vertrauen"},
            }
        ),
    },
    {
        "key": "deal_frisch",
        "composition": "magazin",  # DL-13: семейство композиции (COMPOSITIONS)
        "label": _("Frischmarkt"),
        "description_de": _("Warmer Markt von nebenan: Creme, weiche Karten, viel Luft."),
        "recommended_for": (),
        "look": "frisch",
        # V2: рынок по соседству — фото-баннер, крупные плитки категорий, акции,
        # затем ИСТОРИЯ (панель «о нас») и голоса гостей. Тёплый и неспешный.
        "config": _deal(
            {
                "section_layouts": {"categories": {"preset": "cols3"}},  # DL-11: 6 = 2×3
                "hero_style": "split",
                "nav_style": "classic",
                "media_shape": "round",
                "sections_on": (
                    "hero",
                    "categories",
                    "promotions",
                    "about",
                    "testimonials",
                    "usp_bar",
                ),
                "sections_order": (
                    "hero",
                    "categories",
                    "promotions",
                    "about",
                    "testimonials",
                    "usp_bar",
                    "contact",
                ),
                "section_styles": {
                    "categories": "square",
                    "promotions": "spotlight",
                    "about": "accent",
                    "testimonials": "quotes",
                    "usp_bar": "plain",
                    "contact": "split",
                },
                "page_presets": {"info": "geschichte", "cart": "vertrauen"},
            }
        ),
    },
    {
        "key": "deal_neon",
        "composition": "prospekt",  # DL-13: семейство композиции (COMPOSITIONS)
        "label": _("Nachtmarkt"),
        "description_de": _("Dunkler Deal-Jäger: Neon-Preise, große Timer, maximaler Kontrast."),
        "recommended_for": (),
        "look": "neon",
        # V3: охотник за скидками — АКЦИИ СРАЗУ под баннером, фото во всю плитку,
        # затем короткие ответы и знаки доверия. Никаких рассказов и преимуществ.
        "config": _deal(
            {
                "section_layouts": {"categories": {"preset": "cols3"}},  # DL-11: 6 = 2×3
                "hero_style": "split",
                "nav_style": "classic",
                "card_style": "overlay",
                "sections_on": ("hero", "promotions", "categories", "faq", "trust"),
                "sections_order": (
                    "hero",
                    "promotions",
                    "categories",
                    "faq",
                    "trust",
                    "contact",
                ),
                "section_styles": {
                    "promotions": "spotlight",
                    "categories": "compact",
                    "faq": "list",
                    "trust": "compact",
                    "contact": "compact",
                },
                "page_presets": {"cart": "schlicht"},
            }
        ),
    },
    {
        "key": "deal_blatt",
        "composition": "magazin",  # DL-13: семейство композиции (COMPOSITIONS)
        "label": _("Markthalle"),
        "description_de": _("Wochenzeitung der guten Preise: Serifen, Papier, feine Linien."),
        "recommended_for": (),
        "look": "blatt",
        # V4: газета недели — шапка по центру, полоса-оглавление, акции, затем
        # ПРАЙС-ЛИСТ товаров, передовица «о нас» и пронумерованные вопросы.
        "config": _deal(
            {
                "section_layouts": {"categories": {"preset": "cols3"}},  # DL-11: 6 = 2×3
                "hero_style": "split",
                "nav_style": "centered",
                "media_shape": "wide",
                "catalog_layout": {"preset": "preisliste"},
                "sections_on": ("hero", "usp_bar", "promotions", "products", "about", "faq"),
                "sections_order": (
                    "hero",
                    "usp_bar",
                    "promotions",
                    "products",
                    "about",
                    "faq",
                    "contact",
                ),
                "section_styles": {
                    "usp_bar": "pillars",
                    "promotions": "spotlight",
                    "products": "preisliste",
                    "about": "plain",
                    "faq": "numbered",
                    "contact": "map_first",
                },
                "page_presets": {"info": "text", "cart": "schlicht"},
            }
        ),
    },
    {
        "key": "deal_smart",
        "composition": "sortiment",  # DL-13: семейство композиции (COMPOSITIONS)
        "label": _("Marktplatz"),
        "description_de": _("Nüchtern und dicht: Prozent zuerst, klare Listen, volle Übersicht."),
        "recommended_for": (),
        "look": "smart",
        # V5: утилитарный маркетплейс — БЕЗ баннера: сразу список акций
        # «процент-первым», плотные карточки, три шага и знаки доверия строкой.
        "config": _deal(
            {
                "section_layouts": {"categories": {"preset": "cols3"}},  # DL-11: 6 = 2×3
                "hero_style": "plain",
                "nav_style": "minimal",
                "card_style": "compact",
                "catalog_layout": {"preset": "preisliste_foto"},
                "sections_on": ("promotions", "categories", "process", "trust"),
                "sections_off": ("hero",),
                "sections_order": ("promotions", "categories", "process", "trust", "contact"),
                "section_styles": {
                    "promotions": "rows",
                    "categories": "compact",
                    "process": "minimal",
                    "trust": "plain",
                    "contact": "compact",
                },
                "page_presets": {"cart": "empfehlung"},
            }
        ),
    },
    # ── DL-13: шесть дизайнов канваса «Neue Design-Richtungen» — КАЖДЫЙ в
    # своей композиции (анализ DL-12 §4.1, утверждено владельцем 2026-09-02).
    {
        "key": "deal_monochrom",
        "label": _("Monochrom"),
        "composition": "sortiment",
        "description_de": _("Schwarz-Weiß-Typografie, Farbe nur beim Preis: ehrlich und ruhig."),
        "recommended_for": (),
        "look": "monochrom",
        # V6 / H3 Sortiment-first: без баннера — плитки категорий первым экраном,
        # акции строками, преимущества и доверие компактно.
        "config": _deal(
            {
                "section_layouts": {"categories": {"preset": "cols3"}},
                "hero_style": "plain",
                "nav_style": "minimal",
                "catalog_layout": {"preset": "cols4"},
                "sections_on": ("categories", "promotions", "usp_bar", "trust"),
                "sections_off": ("hero",),
                "sections_order": ("categories", "promotions", "usp_bar", "trust", "contact"),
                "section_styles": {
                    "categories": "square",
                    "promotions": "rows",
                    "usp_bar": "compact",
                    "trust": "compact",
                    "contact": "compact",
                },
                "page_presets": {"cart": "empfehlung"},
            }
        ),
    },
    {
        "key": "deal_pastell",
        "label": _("Pastell"),
        "composition": "bento",
        "description_de": _("Weiche Kacheln und runde Ecken — freundlich, für Familien und Bio."),
        "recommended_for": (),
        "look": "pastell",
        # V7 / H6 Bento: мозаика первым экраном (бренд · акция дня · категория ·
        # часы · Newsletter · рейтинг), затем категории, spotlight-акции, голоса.
        "config": _deal(
            {
                "section_layouts": {"categories": {"preset": "cols3"}},
                "hero_style": "bento",
                "nav_style": "classic",
                "media_shape": "round",
                "sections_on": ("hero", "categories", "promotions", "testimonials"),
                "sections_order": ("hero", "categories", "promotions", "testimonials", "contact"),
                "section_styles": {
                    "categories": "wide",
                    "promotions": "spotlight",
                    "testimonials": "quotes",
                },
                "page_presets": {"info": "geschichte"},
            }
        ),
    },
    {
        "key": "deal_retro",
        "label": _("Retro"),
        "composition": "prospekt",
        "description_de": _("Plakat der 70er: Ocker, Stempel-Badges, kräftige Slab-Schrift."),
        "recommended_for": (),
        "look": "retro",
        # V8 / H2 Prospekt по времени: акцент-плита, spotlight-акции сразу, страница
        # акций «Endet heute / diese Woche / …» (promo_grouping), категории компактно,
        # «как это работает» строкой, преимущества.
        "config": _deal(
            {
                "section_layouts": {"categories": {"preset": "cols3"}},
                "hero_style": "accent",
                "nav_style": "classic",
                "promo_grouping": "time",
                "media_shape": "wide",
                "catalog_layout": {"preset": "preisliste_foto"},
                "sections_on": ("hero", "promotions", "categories", "process", "usp_bar"),
                "sections_order": (
                    "hero",
                    "promotions",
                    "categories",
                    "process",
                    "usp_bar",
                    "contact",
                ),
                "section_styles": {
                    "promotions": "spotlight",
                    "categories": "compact",
                    "process": "row",
                    "usp_bar": "compact",
                    "contact": "compact",
                },
                "page_presets": {"info": "bild"},
            }
        ),
    },
    {
        "key": "deal_nobel",
        "label": _("Nobel"),
        "composition": "magazin",
        "description_de": _("Dunkel, Gold-Haarlinie, Antiqua — Feinkost, Wein, Delikatessen."),
        "recommended_for": (),
        "look": "nobel",
        # V9 / H4 Magazin: split-hero с фото, «о нас» акцентом, акции широкой
        # картой (banner), галерея, отзывы цитатами, контакт сплитом.
        "config": _deal(
            {
                "section_layouts": {"categories": {"preset": "cols3"}},
                "hero_style": "split",
                "nav_style": "centered",
                "sections_on": ("hero", "about", "promotions", "gallery", "testimonials"),
                "sections_order": (
                    "hero",
                    "about",
                    "promotions",
                    "gallery",
                    "testimonials",
                    "contact",
                ),
                "section_styles": {
                    "about": "accent",
                    "promotions": "banner",
                    "gallery": "large",
                    "testimonials": "quotes",
                    "contact": "split",
                },
                "page_presets": {"info": "geschichte"},
            }
        ),
    },
    {
        "key": "deal_foto",
        "label": _("Foto"),
        "composition": "vollbild",
        "description_de": _("Bilder im Vollformat, Glas-Karten darüber — für starke eigene Fotos."),
        "recommended_for": (),
        "look": "foto",
        # V10 / H5 Vollbild: фото во весь экран + стеклянная карточка акции дня,
        # полоса преимуществ, акции overlay-карточками, CTA-баннер.
        "config": _deal(
            {
                "section_layouts": {"categories": {"preset": "cols3"}},
                "hero_style": "fullscreen",
                "nav_style": "classic",
                "card_style": "overlay",
                "sections_on": ("hero", "usp_bar", "promotions", "cta"),
                "sections_order": ("hero", "usp_bar", "promotions", "cta", "contact"),
                # promotions "" = СБРОС на стандартную сетку (у демо-кита сохранён
                # spotlight — без явного "" стиль кита протекал в превью Vollbild).
                "section_styles": {"usp_bar": "plain", "promotions": ""},
                "page_presets": {"info": "bild"},
            }
        ),
    },
    {
        "key": "deal_bauhaus",
        "label": _("Bauhaus"),
        "composition": "bento",
        "description_de": _("Schwarzes Raster, drei reine Farben, Geometrie — Concept-Store."),
        "recommended_for": (),
        "look": "bauhaus",
        # V11 / H6 Bento-geo: геометрическая мозаика, категории квадратами,
        # акции строками, «как это работает» строкой; каталог плотнее (4).
        "config": _deal(
            {
                "section_layouts": {"categories": {"preset": "cols3"}},
                "hero_style": "bento",
                "nav_style": "classic",
                "catalog_layout": {"preset": "cols4"},
                "sections_on": ("hero", "categories", "promotions", "process"),
                "sections_order": ("hero", "categories", "promotions", "process", "contact"),
                "section_styles": {
                    "categories": "square",
                    "promotions": "rows",
                    "process": "row",
                },
                "page_presets": {"cart": "empfehlung"},
            }
        ),
    },
]

_BUNDLE_BY_KEY = {b["key"]: b for b in BUNDLES}


def get_bundle(key):
    """DL-3: сборка по ключу (None — неизвестный) — для stateless-превью."""
    return _BUNDLE_BY_KEY.get(key)


def apply_preview_bundle(cfg, key):
    """DL-3: оси сборки НА КОПИИ конфига (stateless-превью ?preview=1&bundle=).

    Ряды секций делят ссылки с нормализованным конфигом — копируем ДО мутации
    (_apply_bundle_axes правит row'ы на месте). Неизвестный ключ → cfg как есть."""
    bundle = _BUNDLE_BY_KEY.get(key)
    if bundle is None:
        return cfg
    cfg = dict(cfg)
    cfg["sections"] = [dict(r) for r in cfg["sections"]]
    _apply_bundle_axes(cfg, bundle["config"])
    return cfg


def bundles_for(business_type) -> list[dict]:
    """Сборки для архетипа: рекомендованные + универсальные (пустой
    recommended_for = всем). DS-8: у каждого архетипа своя вариация «Fokus» —
    показывать ЧУЖИЕ было бы шумом (пять одинаковых карточек «Fokus»)."""
    rec = [b for b in BUNDLES if business_type in b["recommended_for"]]
    universal = [b for b in BUNDLES if not b["recommended_for"]]
    return rec + [b for b in universal if b not in rec]


def apply_bundle_config(config: dict, key: str) -> bool:
    """DS-9: применить ОСИ сборки к готовому конфигу (без Look и без записи в БД).

    Выделено из `apply_bundle`, чтобы демо-киты собирали ту же композицию, что
    получает владелец кнопкой «Startpaket» — один источник правды вместо
    девяти копий полей в китах. Мутирует `config` на месте."""
    bundle = _BUNDLE_BY_KEY.get(key)
    if bundle is None:
        return False
    _apply_bundle_axes(config, bundle["config"])
    return True


def apply_bundle(tenant, key) -> bool:
    """DS-3c: применить сборку — apply_look (полная копия конфига, W6-инвариант)
    + таргетные оси поверх. Идемпотентно (двойной normalize); False — неизвестный
    ключ. Секция anfrage включается, но её рендер остаётся за гейтом модуля jobs
    (fail-closed в партиале) — сборка безопасна любому архетипу."""
    bundle = _BUNDLE_BY_KEY.get(key)
    if bundle is None:
        return False
    apply_look(tenant, bundle["look"])
    config = siteconfig.normalize(tenant.site_config)
    _apply_bundle_axes(config, bundle["config"])
    # DL-8a: запомнить выбранную сборку (бейдж «Aktiv» страницы Design).
    config["design"] = {"look": bundle["look"], "bundle": key}
    tenant.site_config = siteconfig.normalize(config)
    tenant.save(update_fields=["site_config", "updated_at"])
    return True


def _apply_bundle_axes(config: dict, over: dict) -> None:
    """Оси сборки поверх конфига (общее тело apply_bundle/apply_bundle_config)."""
    if over.get("hero_style"):
        config["hero_style"] = over["hero_style"]
    # DL-13 C3: страница /aktionen/ «по времени» (Retro = Prospekt по сроку);
    # "" снимает ключ (presence-minimal). Ось только когда сборка её знает.
    if "promo_grouping" in over:
        if over["promo_grouping"]:
            config["promo_grouping"] = over["promo_grouping"]
        else:
            config.pop("promo_grouping", None)
    if over.get("nav_cta"):
        nav = dict(config.get("nav") or {})
        nav["cta"] = True
        config["nav"] = nav
    if over.get("catalog_layout"):
        config["catalog_layout"] = dict(over["catalog_layout"])
    # DL-10b: форма кадра (круглые/широкие фото) — часть композиции шаблона.
    if over.get("media_shape"):
        sd = dict(config.get("site_defaults") or {})
        sd["media_shape"] = over["media_shape"]
        config["site_defaults"] = sd
    # DS-9: форма карточек (мода — фото во всю плитку).
    if over.get("card_style"):
        sd = dict(config.get("site_defaults") or {})
        sd["card_style"] = over["card_style"]
        config["site_defaults"] = sd
    # DL-16.4: форма карточки акции ("preis" у дил-сборок; "" = снять).
    if "promo_card" in over:
        sd = dict(config.get("site_defaults") or {})
        sd["promo_card"] = over["promo_card"]
        config["site_defaults"] = sd
    # DS-8/9: виджет первого экрана — часть композиции ("none" = снять плитки).
    if over.get("hero_widget"):
        sd = dict(config.get("site_defaults") or {})
        sd["hero_widget"] = "" if over["hero_widget"] == "none" else over["hero_widget"]
        config["site_defaults"] = sd
    # DS-9: шапка одной строкой — и легаси-ключ nav, и дерево меню S7 (шапку
    # рисует menus.top.style; без него Fokus оставался бы двухэтажным).
    if over.get("nav_style"):
        nav = dict(config.get("nav") or {})
        nav["style"] = over["nav_style"]
        config["nav"] = nav
        menus = config.get("menus")
        if isinstance(menus, dict) and isinstance(menus.get("top"), dict):
            top = dict(menus["top"])
            top["style"] = over["nav_style"]
            config["menus"] = {**menus, "top": top}
    styles = over.get("section_styles", {})
    # DL-11: раскладка секции (колонки) — часть композиции: ряды плиток у сборки
    # полные по построению (6 категорий × 3 колонки), не только по CSS-обрезке.
    layouts = over.get("section_layouts", {})
    on = set(over.get("sections_on", ()))
    off = set(over.get("sections_off", ())) - on
    for row in config["sections"]:
        if row["key"] in styles:
            row["style"] = styles[row["key"]]
        if row["key"] in layouts:
            # Нормализованный ряд несёт материализованные cols/mobile/tablet — при
            # смене пресета они перебили бы его (стенд: превью frisch осталось 4-кол.).
            keep = {
                k: v
                for k, v in (row.get("layout") or {}).items()
                if k not in ("preset", "cols", "mobile", "tablet")
            }
            row["layout"] = {**keep, **layouts[row["key"]]}
        if row["key"] in on:
            row["enabled"] = True
        elif row["key"] in off:
            row["enabled"] = False
    # DL-9a: ПОРЯДОК блоков главной — часть шаблона (до этой оси порядок задавал
    # только шаблон архетипа, и сборки отличались лишь «кожей»). Сортировка
    # стабильная: ключи вне списка сохраняют относительный порядок и уходят в
    # конец, поэтому чужие секции конфига не теряются и не перемешиваются.
    order = over.get("sections_order")
    if order:
        rank = {key: i for i, key in enumerate(order)}
        config["sections"].sort(key=lambda row: rank.get(row["key"], len(rank)))
    # DL-3: страничные пресеты ST-2 — сборка красит и «О нас»/корзину, не только
    # главную. apply_page_preset идемпотентен и хранит блоки владельца.
    for host, preset_id in (over.get("page_presets") or {}).items():
        page_presets.apply_page_preset(config, host, preset_id)


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
    # DL-8a: запомнить выбранную кожу (бейдж «Aktiv» страницы Design +
    # data-sf-look витрины). Прежний bundle-ключ сохраняется: Look меняет
    # только оптику, композиция сборки остаётся.
    config = siteconfig.normalize(tenant.site_config)
    design = dict(config.get("design") or {})
    design["look"] = family_key
    config["design"] = design
    tenant.site_config = siteconfig.normalize(config)
    tenant.save(update_fields=["site_config", "updated_at"])
    return True
