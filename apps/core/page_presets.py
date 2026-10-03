"""ST-2 «Шаблоны всех страниц»: реестр пресетов НЕ-home страниц (уровень L2).

Обобщение паттерна AB6.10 (_ABOUT_PRESETS из setup_steps): пресет страницы =
набор C-блоков хоста `page_blocks[host]` + опц. плоские ключи существующего
normalize (напр. cart_show_upsell). Применение идемпотентно: заменяются ТОЛЬКО
блоки с префиксом id пресет-семейства хоста, блоки владельца целы. Новых
top-level ключей siteconfig НЕ вводится (golden-замки не затронуты).

Контент блоков — немецкая канва-рыба (как CBLOCK_DEMO_DATA), лейблы пресетов —
DE как прочий канва-контент; хром пикера переводится в шаблонах.
"""

from django.utils.translation import gettext_lazy as _

# host -> {"prefix": префикс id посеянных блоков, "presets": (пресеты…)}
# Пресет: key/label/icon/blocks[(kind, data)]/flat{ключ: значение}/
# recommended_for (business_type; пусто = нейтрален, порядок не меняется).
# LB-3b: above=True — блоки встают НАД основным списком страницы (маркер LB-2);
# per_type=True — плюс по блоку «Liste» на каждую живую рубрику акций.
PAGE_PRESETS = {
    # «Über uns» — переезд _ABOUT_PRESETS (AB6.10); префикс pb-about- сохранён,
    # чтобы уже посеянные мастером конфиги узнавались как «текущий пресет».
    "info": {
        "prefix": "pb-about-",
        "presets": (
            {"key": "text", "label": _("Nur Text"), "icon": "📝", "blocks": ()},
            {
                "key": "bild",
                "label": _("Text + Bild"),
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
                "label": _("Unsere Geschichte"),
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
                "label": _("Team & Werte"),
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
                "label": _("Schlicht"),
                "icon": "🧺",
                "blocks": (),
                "flat": {"cart_show_upsell": False},
            },
            {
                "key": "empfehlung",
                "label": _("Mit Empfehlungen"),
                "icon": "✨",
                "blocks": (),
                "flat": {"cart_show_upsell": True},
                "recommended_for": ("online_shop", "retail", "clothing"),
            },
            {
                "key": "vertrauen",
                "label": _("Vertrauen & Hinweise"),
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


# LB-3b (план docs/lb-list-blocks-plan-2026-10-02.md §12.6, решение Р-5 (а)):
# страница акций — обзор блоками. «Prospekt» один раз раскладывает встроенный обзор в
# блоки, которые владелец дальше настраивает по одному: «Endet heute» лентой,
# «Demnächst», по блоку на каждую живую рубрику — всё над основным списком; в нём
# остаётся «всё, что выше не показано» (N-3). Заголовков у блоков нет намеренно:
# подпись берётся по выборке и переводится (рубрика — своим переводом владельца).
# «Standard» забирает назад только блоки пресета.
PAGE_PRESETS["promos"] = {
    "prefix": "pb-promos-",
    "presets": (
        {"key": "standard", "label": _("Standard-Übersicht"), "icon": "🗂️", "blocks": ()},
        {
            "key": "prospekt",
            "label": _("Prospekt (Blöcke)"),
            "icon": "📰",
            "above": True,
            "per_type": True,
            "blocks": (
                ("list", {"source": "promotions", "endet": "heute", "out": "slider"}),
                ("list", {"source": "promotions", "phase": "upcoming"}),
            ),
        },
    ),
}


def _live_rubrics() -> list[str]:
    """Свои рубрики действующих акций — в порядке обзора (свежая первой)."""
    from apps.promotions.models import Promotion

    seen: list[str] = []
    rows = (
        Promotion.objects.filter(status="active")
        .exclude(group="")
        .order_by("-created_at")
        .values_list("group", flat=True)
    )
    for group in rows:
        if group not in seen:
            seen.append(group)
    return seen


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
    specs = list(preset["blocks"])
    if preset.get("per_type"):
        specs += [("list", {"source": "promotions", "type": key}) for key in _live_rubrics()]
    seeded = [
        {
            "key": kind,
            "id": f"{reg['prefix']}{preset['key']}-{i}",
            "enabled": True,
            "data": dict(data),
        }
        for i, (kind, data) in enumerate(specs, start=1)
    ]
    if preset.get("above"):
        from apps.tenants import siteconfig

        # LB-3b: над основным списком — блоки владельца, стоявшие над ним, остаются
        # первыми; его блоки под списком — под ним (маркер LB-2 между частями).
        above, below = siteconfig.split_at_main(keep)
        head = above + seeded
        rows = head + ([{"key": siteconfig.MAIN_LIST_KEY}] if head else []) + below
    else:
        rows = keep + seeded
    if rows:
        pb[host] = rows
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
