"""ST-2 «Шаблоны всех страниц»: реестр пресетов НЕ-home страниц (уровень L2).

Обобщение паттерна AB6.10 (_ABOUT_PRESETS из setup_steps): пресет страницы =
набор C-блоков хоста `page_blocks[host]` + опц. плоские ключи существующего
normalize (напр. cart_show_upsell). Применение идемпотентно: заменяются ТОЛЬКО
блоки с префиксом id пресет-семейства хоста, блоки владельца целы. Новых
top-level ключей siteconfig НЕ вводится (golden-замки не затронуты).

Контент блоков — немецкая канва-рыба (как CBLOCK_DEMO_DATA), лейблы пресетов —
DE как прочий канва-контент; хром пикера переводится в шаблонах.
"""

# host -> {"prefix": префикс id посеянных блоков, "presets": (пресеты…)}
# Пресет: key/label/icon/blocks[(kind, data)]/flat{ключ: значение}/
# recommended_for (business_type; пусто = нейтрален, порядок не меняется).
PAGE_PRESETS = {
    # «Über uns» — переезд _ABOUT_PRESETS (AB6.10); префикс pb-about- сохранён,
    # чтобы уже посеянные мастером конфиги узнавались как «текущий пресет».
    "info": {
        "prefix": "pb-about-",
        "presets": (
            {"key": "text", "label": "Nur Text", "icon": "📝", "blocks": ()},
            {
                "key": "bild",
                "label": "Text + Bild",
                "icon": "🖼️",
                "blocks": (
                    (
                        "image",
                        {
                            "url": "/medien/demo.svg?kw=laden&w=1200&h=600",
                            "caption": "Bildunterschrift — klicken und ersetzen",
                        },
                    ),
                ),
            },
            {
                "key": "geschichte",
                "label": "Unsere Geschichte",
                "icon": "📖",
                "blocks": (
                    (
                        "image_text",
                        {
                            "url": "/medien/demo.svg?kw=laden&w=800&h=600",
                            "title": "Unsere Geschichte",
                            "body": (
                                "Wie alles begann: Erzählen Sie hier, wie Ihr Geschäft "
                                "entstanden ist und was Sie antreibt — das Foto können "
                                "Sie jederzeit austauschen."
                            ),
                            "side": "left",
                        },
                    ),
                ),
            },
            {
                "key": "team",
                "label": "Team & Werte",
                "icon": "🤝",
                "blocks": (
                    (
                        "image_text",
                        {
                            "url": "/medien/demo.svg?kw=team&w=800&h=600",
                            "title": "Unser Team",
                            "body": (
                                "Stellen Sie hier die Menschen hinter Ihrem Geschäft vor — "
                                "Namen, Rollen und was Ihre Kundschaft an ihnen schätzt."
                            ),
                            "side": "right",
                        },
                    ),
                    (
                        "text",
                        {
                            "title": "Worauf wir Wert legen",
                            "body": (
                                "Qualität, Regionalität, Handwerk: Beschreiben Sie in zwei "
                                "bis drei Sätzen, wofür Ihr Geschäft steht."
                            ),
                        },
                    ),
                ),
            },
        ),
    },
    # Корзина: раскладка страницы = блоки + тумблер кросс-селла (плоский ключ).
    "cart": {
        "prefix": "pb-cart-",
        "presets": (
            {
                "key": "schlicht",
                "label": "Schlicht",
                "icon": "🧺",
                "blocks": (),
                "flat": {"cart_show_upsell": False},
            },
            {
                "key": "empfehlung",
                "label": "Mit Empfehlungen",
                "icon": "✨",
                "blocks": (),
                "flat": {"cart_show_upsell": True},
                "recommended_for": ("online_shop", "retail", "clothing"),
            },
            {
                "key": "vertrauen",
                "label": "Vertrauen & Hinweise",
                "icon": "🤝",
                "blocks": (
                    (
                        "text",
                        {
                            "title": "Gut zu wissen",
                            "body": (
                                "Abholung und Bezahlung vor Ort möglich — Ihre Bestellung "
                                "liegt zur vereinbarten Zeit für Sie bereit."
                            ),
                        },
                    ),
                    (
                        "text",
                        {
                            "title": "Fragen zur Bestellung?",
                            "body": (
                                "Rufen Sie uns an oder schreiben Sie uns — wir helfen gern weiter."
                            ),
                        },
                    ),
                ),
                "flat": {"cart_show_upsell": True},
                "recommended_for": ("bakery", "butcher", "cafe", "grocery"),
            },
        ),
    },
}


def presets_for(host, business_type=""):
    """Пресеты хоста, рекомендованные для business_type — первыми (паттерн
    template_cards): каждому даётся флаг `recommended` для бейджа в UI."""
    reg = PAGE_PRESETS.get(host)
    if reg is None:
        return []
    cards = [
        {**p, "recommended": business_type in (p.get("recommended_for") or ())}
        for p in reg["presets"]
    ]
    return sorted(cards, key=lambda c: not c["recommended"])


def apply_page_preset(cfg, host, preset_id):
    """Применить пресет к plain-dict конфигу (до normalize). Идемпотентно:
    блоки владельца (без префикса семейства) сохраняются, свои — заменяются;
    плоские ключи пишутся поверх. Неизвестный host/preset → False, cfg цел."""
    reg = PAGE_PRESETS.get(host)
    preset = next((p for p in (reg["presets"] if reg else ()) if p["key"] == preset_id), None)
    if preset is None:
        return False
    pb = cfg.get("page_blocks") if isinstance(cfg.get("page_blocks"), dict) else {}
    pb = dict(pb)
    keep = [
        b
        for b in (pb.get(host) if isinstance(pb.get(host), list) else [])
        if not str((b or {}).get("id", "")).startswith(reg["prefix"])
    ]
    seeded = [
        {
            "key": kind,
            "id": f"{reg['prefix']}{preset['key']}-{i}",
            "enabled": True,
            "data": dict(data),
        }
        for i, (kind, data) in enumerate(preset["blocks"], start=1)
    ]
    if keep + seeded:
        pb[host] = keep + seeded
    else:
        pb.pop(host, None)
    cfg["page_blocks"] = pb
    for key, value in (preset.get("flat") or {}).items():
        cfg[key] = value
    return True


def current_preset(cfg, host):
    """Ключ активного пресета хоста по НОРМАЛИЗОВАННОМУ конфигу: сначала по
    посеянным блокам (префикс id), затем по плоским ключам (пресеты без
    блоков); ничего не подошло → первый пресет (дефолт)."""
    reg = PAGE_PRESETS.get(host)
    if reg is None:
        return ""
    ids = [str((b or {}).get("id", "")) for b in ((cfg.get("page_blocks") or {}).get(host) or [])]
    for p in reg["presets"]:
        if p["blocks"] and any(i.startswith(f"{reg['prefix']}{p['key']}-") for i in ids):
            return p["key"]
    for p in reg["presets"]:
        flat = p.get("flat") or {}
        if not p["blocks"] and flat and all(cfg.get(k) == v for k, v in flat.items()):
            return p["key"]
    return reg["presets"][0]["key"]
