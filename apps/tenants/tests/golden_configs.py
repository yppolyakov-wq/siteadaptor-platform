"""UC1-1 (шаг 0): репрезентативные входы для golden-замков `siteconfig.normalize`.

Эталоны в `golden/normalize_<name>.json` сгенерированы на коде ДО введения
`PAGE_SECTION_REGISTRY` — рефактор реестров обязан давать БАЙТ-В-БАЙТ тот же
normalize-выход (жёсткий гейт U-C, риск №5 uc-плана). Регенерация эталонов —
ТОЛЬКО осознанным решением при изменении схемы (см. test_normalize_golden).
"""

# Пустой/легаси конфиг — normalize дописывает все дефолты.
EMPTY = {}

# Старый конфиг: подмножество секций (до добавления новых) + тексты.
LEGACY_SUBSET = {
    "sections": [
        {"key": "hero", "enabled": True},
        {"key": "products", "enabled": True},
        {"key": "about", "enabled": False},
        {"key": "unknown_key_dropped", "enabled": True},
    ],
    "hero_title": "  Bäckerei Sonne  ",
    "about_text": "Seit 1950.",
    "font": "serif",
    "hero_style": "image",
}

# Богатый home: C-блоки, layout/limit/source/visual/hidden_on/width/font на секциях,
# heroes-слайдер, nav/menus, контент-пары, trust/team, шаблоны, история.
RICH_HOME = {
    "sections": [
        {
            "key": "products",
            "enabled": True,
            "layout": {"cols": 3, "gap": "lg", "width": "full"},
            "limit": 9,
            "source": "featured_first",
            "show_all": False,
            "visual": {"radius": 12, "shadow": "md", "background": "#ffeecc", "padding": 24},
            "hidden_on": ["mobile"],
            "width": "full",
            "font": "serif",
        },
        {"key": "text", "id": "cb1", "enabled": True, "data": {"html": "<p>Hallo</p>"}},
        {
            "key": "image_text",
            "id": "cb2",
            "enabled": True,
            "data": {"url": "/x.jpg", "html": "<p>Bild</p>", "side": "right"},
        },
        {"key": "button", "id": "cb3", "enabled": False, "data": {"label": "Mehr", "url": "/a/"}},
        {"key": "hero", "enabled": True},
        {"key": "faq", "enabled": True},
    ],
    "heroes": [
        {"title": "Eins", "text": "T1", "image": "/h1.jpg", "cta_label": "Los", "cta_url": "/p/"},
        {"title": "Zwei", "text": "T2", "image": "/h2.jpg"},
    ],
    "nav": {
        "style": "centered",
        "sticky": False,
        "items": [{"key": "products", "enabled": False}, {"key": "nope", "enabled": True}],
    },
    "menus": {
        "top": {
            "style": "classic",
            "sticky": True,
            "items": [
                {"label": "Shop", "type": "archetype", "target": "catalog"},
                {"label": "FAQ", "type": "anchor", "target": "/#faq"},
            ],
        },
        "bottom": {
            "enabled": True,
            "items": [{"label": "Start", "type": "page", "target": "home"}],
        },
    },
    "faq": [["Frage?", "Antwort."], {"q": "Q2", "a": "A2"}],
    "testimonials": [{"name": "Anna", "text": "Toll!"}],
    "process": [{"title": "Schritt 1", "text": "Anruf"}],
    "team": [{"name": "Lea", "role": "Chefin", "photo": "/lea.jpg"}, {"bad": True}],
    "trust": {"since": "1950", "marks": ["Bio", "Meisterbetrieb", 7]},
    "typography": {"heading_weight": "bold", "leading": "relaxed"},
    "site_defaults": {"radius": 8, "shadow": "sm"},
    "block_templates": {"t1": {"key": "text", "label": "Мой блок", "data": {"html": "<p>x</p>"}}},
    "page_templates": {"p1": {"label": "Лендинг", "sections": [{"key": "hero", "enabled": True}]}},
    "history": [{"ts": "2026-01-01T00:00:00", "config": {"sections": []}}],
    "cart_title": "Warenkorb",
    "cart_show_upsell": False,
}

# Детальные страницы: order+hidden события (orderable), скрытия product/booking/stays,
# per-page раскладки и реестр архетипов.
DETAIL_PAGES = {
    "sections": [{"key": "hero", "enabled": True}],
    "event_detail": {
        "order": ["program", "for_whom", "faq", "nope"],
        "hidden": ["testimonials", "bogus"],
    },
    "product_detail": {"hidden": ["related"]},
    "booking_detail": {"hidden": ["team"]},
    "stays_detail": {"hidden": ["similar"]},
    "catalog_layout": {"cols": 4, "gap": "sm"},
    "event_index_layout": {"cols": 2},
    "stay_index_layout": {"cols": 3},
    "detail_related_layout": {"cols": 2},
    "service_index_layout": {"cols": 2},
    "archetypes": {"booking": {"title": "Termine", "teaser": "Jetzt buchen"}},
    "primary_archetype": "booking",
    "jobs_vehicle": True,
}

GOLDEN_INPUTS = {
    "empty": EMPTY,
    "legacy_subset": LEGACY_SUBSET,
    "rich_home": RICH_HOME,
    "detail_pages": DETAIL_PAGES,
}
