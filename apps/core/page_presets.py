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


# LB-4d-2 (план docs/lb4-home-lists-archetypes-plan-2026-10-04.md §12.2): листинги —
# «Standard» и блочный пресет под архетип. `blocks` встают над основным списком
# (`above`), `below` — под ним. Блок источника выключенного модуля пресет не кладёт,
# пресет без единого доступного блока не предлагается (`presets_for(tenant=…)`).
# Заголовков нет намеренно (как у «Prospekt»): подпись по выборке и переводится.
def _listing(prefix, preset):
    return {
        "prefix": prefix,
        "presets": (
            {"key": "standard", "label": _("Standard"), "icon": "🗂️", "blocks": ()},
            {**preset, "above": True},
        ),
    }


PAGE_PRESETS["catalog"] = _listing(
    "pb-catalog-",
    {
        "key": "neu_sale",
        "label": _("Neuheiten + Sale"),
        "icon": "✨",
        "blocks": (
            ("list", {"source": "products", "sort": "newest", "out": "slider"}),
            ("list", {"source": "products", "only": "sale", "out": "slider"}),
        ),
        "recommended_for": ("retail", "clothing", "online_shop", "grocery"),
    },
)
PAGE_PRESETS["services"] = _listing(
    "pb-services-",
    {
        "key": "beratung",
        "label": _("Beratung & Angebote"),
        "icon": "🎥",
        "blocks": (
            ("list", {"source": "services", "only": "video", "out": "slider"}),
            ("list", {"source": "promotions", "ziel": "service"}),
        ),
        "recommended_for": ("friseur", "werkstatt"),
    },
)
PAGE_PRESETS["stay_rooms"] = _listing(
    "pb-stays-",
    {
        "key": "angebote",
        "label": _("Angebote & Stimmen"),
        "icon": "🛎️",
        "blocks": (("list", {"source": "promotions", "ziel": "stay"}),),
        "below": (("list", {"source": "reviews", "entity": "stay", "stars": 4}),),
        "recommended_for": ("hotel",),
    },
)
PAGE_PRESETS["events"] = _listing(
    "pb-events-",
    {
        "key": "bald",
        "label": _("Bald & Highlights"),
        "icon": "⏳",
        "blocks": (("list", {"source": "events", "only": "soon", "out": "slider"}),),
        "below": (("list", {"source": "reviews", "entity": "event", "stars": 4}),),
        "recommended_for": ("events",),
    },
)
# /touren/ уже разбит по странам (MT-D2) — блок на страну над списком был бы дублем;
# пресет показывает ближайшие заезды над списком и отзывы путешественников под ним.
PAGE_PRESETS["tours"] = _listing(
    "pb-tours-",
    {
        "key": "termine",
        "label": _("Termine & Stimmen"),
        "icon": "🧭",
        # без окна «14 дней»: заезды тура планируют за месяцы (LB-4d-3, демо moto)
        "blocks": (("list", {"source": "events", "out": "slider"}),),
        "below": (("list", {"source": "reviews", "entity": "event", "stars": 4}),),
        "recommended_for": ("tour_operator",),
    },
)


def _specs(preset) -> list:
    """Все блоки пресета (над и под основным списком)."""
    return list(preset.get("blocks", ())) + list(preset.get("below", ()))


def _available(tenant, kind, data) -> bool:
    """LB-4d-2: модуль источника блока «Liste» (и цели «Gilt für») включён."""
    if tenant is None or kind != "list":
        return True
    from apps.core import list_blocks

    source = data.get("source") or "promotions"
    modules = [list_blocks.SOURCE_MODULES.get(source, "")]
    if data.get("ziel") in list_blocks.TARGET_SOURCES:
        modules.append(list_blocks.SOURCE_MODULES[list_blocks.TARGET_SOURCES[data["ziel"]]])
    # отзывы о событиях без модуля событий — пустая выборка (вид сущности выключен)
    entity_source = list_blocks._REVIEW_KIND_SOURCES.get(data.get("entity") or "")
    if source == "reviews" and entity_source:
        modules.append(list_blocks.SOURCE_MODULES[entity_source])
    return all(list_blocks._module_on(tenant, m) for m in modules if m)


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


def _list_signature(data) -> tuple:
    """Выборка блока «Liste» (источник и фильтры, без вида и подписи) — для сравнения."""
    from apps.tenants import siteconfig

    clean = siteconfig._clean_list_block(data if isinstance(data, dict) else {})
    # LB-3d: все поля фильтра всех источников — из реестра, чтобы новый фильтр не
    # выпал из сравнения (иначе два разных блока считались бы одной выборкой).
    fields = ["source"]
    for spec in siteconfig.LIST_SOURCES.values():
        fields += [f for f in spec["filters"] if f not in fields]
    return tuple(clean.get(key) for key in fields)


def presets_for(host, business_type="", tenant=None):
    """Пресеты хоста, рекомендованные для business_type — первыми (паттерн
    template_cards): каждому даётся флаг `recommended` для бейджа в UI.

    LB-4d-2: с `tenant` — без пресетов, у которых не осталось ни одного блока
    включённого модуля (пустой пресет обещал бы страницу, которой не будет)."""
    reg = PAGE_PRESETS.get(host)
    if reg is None:
        return []
    cards = [
        {**p, "recommended": business_type in (p.get("recommended_for") or ())}
        for p in reg["presets"]
        if not _specs(p) or p.get("per_type") or any(_available(tenant, k, d) for k, d in _specs(p))
    ]
    return sorted(cards, key=lambda c: not c["recommended"])


def apply_page_preset(cfg, host, preset_id, tenant=None):
    """Применить пресет к plain-dict конфигу (до normalize). Идемпотентно:
    блоки владельца (без префикса семейства) сохраняются, свои — заменяются;
    плоские ключи пишутся поверх. Неизвестный host/preset → False, cfg цел.

    LB-4d-2: `below` — блоки под основным списком; с `tenant` блок источника
    выключенного модуля не кладётся."""
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
    specs = [(k, d) for k, d in preset["blocks"] if _available(tenant, k, d)]
    if preset.get("per_type"):
        specs += [("list", {"source": "promotions", "type": key}) for key in _live_rubrics()]
    below = [(k, d) for k, d in preset.get("below", ()) if _available(tenant, k, d)]
    n_above = len(specs)
    specs += below
    if specs:
        from apps.tenants import siteconfig

        # Ревью LB-3: блок с той же выборкой у владельца уже есть (например, добавлен
        # подсказкой «＋ тип») — пресет его не дублирует: иначе рубрика вышла бы дважды,
        # а в полосе прыжков — два одинаковых чипа.
        owned = {
            _list_signature(b.get("data"))
            for b in keep
            if siteconfig.cblock_type((b or {}).get("key")) == "list"
        }
        tagged = [(i < n_above, k, d) for i, (k, d) in enumerate(specs)]
        tagged = [
            (up, k, d) for up, k, d in tagged if k != "list" or _list_signature(d) not in owned
        ]
        # …и не вытесняет блоки владельца за кап страницы (normalize оставляет первые
        # _MAX_CBLOCKS): лишним рубрикам место в основном списке — их секции в остатке.
        room = siteconfig._MAX_CBLOCKS - sum(1 for b in keep if not siteconfig.is_main_marker(b))
        tagged = tagged[: max(0, room)]
    else:
        tagged = []

    def _seed(items, start):
        return [
            {
                "key": kind,
                "id": f"{reg['prefix']}{preset['key']}-{i}",
                "enabled": True,
                "data": dict(data),
            }
            for i, (kind, data) in enumerate(items, start=start)
        ]

    seeded_up = _seed([(k, d) for up, k, d in tagged if up], 1)
    seeded_down = _seed([(k, d) for up, k, d in tagged if not up], len(seeded_up) + 1)
    if preset.get("above"):
        from apps.tenants import siteconfig

        # LB-3b: над основным списком — блоки владельца, стоявшие над ним, остаются
        # первыми; его блоки под списком — под ним (маркер LB-2 между частями).
        # LB-4d-2: блоки пресета «под списком» встают сразу под маркером, перед
        # блоками владельца — у страницы и так есть место для своих снизу.
        above, below = siteconfig.split_at_main(keep)
        head = above + seeded_up
        tail = seeded_down + below
        rows = head + ([{"key": siteconfig.MAIN_LIST_KEY}] if head or tail else []) + tail
    else:
        rows = keep + seeded_up + seeded_down
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
        if _specs(p) and any(i.startswith(f"{reg['prefix']}{p['key']}-") for i in ids):
            return p["key"]
    for p in reg["presets"]:
        flat = p.get("flat") or {}
        if not _specs(p) and flat and all(cfg.get(k) == v for k, v in flat.items()):
            return p["key"]
    return reg["presets"][0]["key"]
