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

import re
import uuid

from django.utils.translation import gettext_lazy as _

from apps.core import detail_sections

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
REPEATABLE_BLOCKS = ("text", "image", "image_text", "button", "spacer", "promo")
_MAX_CBLOCKS = 30


def _text_style(d: dict) -> dict:
    """UC6-2: стиль текста блока — только НЕ-дефолтные валидные значения
    (дефолт = ключа нет → старые конфиги байт-в-байт, golden-замки живы).
    Цвет — ТОЛЬКО палитра темы (accent/muted), решение владельца 2026-07-06."""
    out = {}
    if d.get("align") in ("center", "right"):
        out["align"] = d["align"]
    if d.get("size") in ("sm", "lg", "xl"):
        out["size"] = d["size"]
    if d.get("color") in ("accent", "muted"):
        out["color"] = d["color"]
    return out


def _clean_cblock_data(key: str, raw) -> dict:
    """Санитизация данных C-блока по типу (строки; неизвестные ключи отброшены)."""
    d = raw if isinstance(raw, dict) else {}
    if key == "text":
        return {"title": _s(d.get("title")), "body": _s(d.get("body")), **_text_style(d)}
    # UC6-4: скругление фото блока — "" (стандарт rounded-2xl) | none | 3xl;
    # только валидные НЕ-дефолтные значения (старые конфиги байт-в-байт).
    rounded = {"rounded": d["rounded"]} if d.get("rounded") in ("none", "3xl") else {}
    if key == "image":
        return {"url": _s(d.get("url")), "caption": _s(d.get("caption")), **rounded}
    if key == "image_text":
        side = d.get("side")
        return {
            "url": _s(d.get("url")),
            "title": _s(d.get("title")),
            "body": _s(d.get("body")),
            "side": side if side in ("left", "right") else "left",
            **_text_style(d),
            **rounded,
        }
    if key == "button":
        return {"label": _s(d.get("label")), "url": _s(d.get("url"))}
    if key == "promo":
        # UE1-1 (D2=LIVE): promo_pk — строка-UUID БЕЗ запроса в БД (purge-safe;
        # существование/активность проверяет рендер _block_promo, fail-safe).
        # discount_style здесь НЕ живёт — источник един: Promotion (UE2-2).
        align = d.get("align")
        badge = d.get("badge_pos")
        return {
            "promo_pk": _s(d.get("promo_pk"))[:36],
            "align": align if align in ("left", "center", "right") else "left",
            "badge_pos": badge
            if badge in ("top-left", "top-right", "bottom-left", "bottom-right", "none")
            else "top-left",
            "show_button": bool(d.get("show_button")),
            "button_label": _s(d.get("button_label"))[:40],
            # UC6-6f: подсказка стиля скидки (каскад: акция главнее, см. PROMO_STYLE_HINTS).
            **({"style_hint": d["style_hint"]} if d.get("style_hint") in PROMO_STYLE_HINTS else {}),
        }
    return {}  # spacer — без данных


_DEVICES = ("mobile", "tablet", "desktop")


def _clean_hidden_on(raw) -> list:
    """SE-3c-mid: список устройств, на которых секция скрыта (подмножество _DEVICES)."""
    return [d for d in _DEVICES if isinstance(raw, list) and d in raw]


# UC6-3: у C-блоков шире набор ширин, чем у секций: доли контейнера
# («текст на 2/3 экрана» — запрос владельца; UC6-3b: + 1/3..1/6).
# Секции остаются на _LAYOUT_WIDTHS.
CBLOCK_WIDTHS = ("contained", "full", "w23", "w12", "w13", "w14", "w15", "w16")
# UC6-3a: узкие ширины — кандидаты на размещение В РЯД (md:flex).
NARROW_WIDTHS = ("w23", "w12", "w13", "w14", "w15", "w16")


def group_block_rows(blocks: list) -> list:
    """UC6-3a: последовательные УЗКИЕ C-блоки складываются в один ряд
    (`{"key": "_row", "row": [...]}` → home.html рендерит md:flex).
    Блок с `newline=True` принудительно начинает новый ряд; широкие блоки
    и фикс-секции ряд разрывают. Чистая функция — только для рендера."""
    out, row = [], None
    for b in blocks:
        narrow = isinstance(b, dict) and b.get("width") in NARROW_WIDTHS
        if not narrow:
            row = None
            out.append(b)
            continue
        if row is None or b.get("newline"):
            row = {"key": "_row", "row": [b]}
            out.append(row)
        else:
            row["row"].append(b)
    return out


# UC6-5: демо-данные нового C-блока — вставка сразу даёт живой пример (DE-рыба,
# владелец правит под себя); раньше пустой блок выглядел как «ничего не произошло»
# (на витрине — только placeholder в превью). spacer/promo — осознанно без демо
# (spacer без данных; promo требует реальную акцию — рендер fail-safe).
CBLOCK_DEMO_DATA = {
    "text": {
        "title": "Über uns",
        "body": (
            "Erzählen Sie hier in zwei bis drei Sätzen, was Ihr Geschäft besonders "
            "macht — Ihre Geschichte, Ihre Spezialität, Ihr Team."
        ),
    },
    "image": {
        "url": "/medien/demo.svg?kw=laden&w=1200&h=600",
        "caption": "Bildunterschrift — klicken und ersetzen",
    },
    "image_text": {
        "url": "/medien/demo.svg?kw=team&w=800&h=600",
        "title": "Frisch, regional, mit Herz",
        "body": (
            "Beschreiben Sie hier ein Angebot oder eine Besonderheit — "
            "das Foto können Sie jederzeit austauschen."
        ),
        "side": "left",
    },
    "button": {"label": "Mehr erfahren", "url": "/ueber-uns/"},
}


# UC6-6c: пресеты отображения при вставке блока («выбор шаблона с преднастрой-
# ками и демо-данными» — фидбэк владельца). Стандарт (key "") — голые демо-
# данные CBLOCK_DEMO_DATA; каждый пресет — оверрайды поверх демо: data-ключи
# и/или block-props (width/pos/newline/visual). Лейблы DE — как демо-контент.
CBLOCK_VARIANTS = {
    "text": [
        {"key": "intro", "label": "Intro zentriert", "data": {"align": "center", "size": "lg"}},
        {
            "key": "quote",
            "label": "Zitat",
            "data": {"align": "center", "size": "lg", "color": "muted"},
            "visual": {"padding": 24},
        },
        {
            "key": "banner",
            "label": "Akzent-Banner",
            "data": {"align": "center", "size": "xl", "color": "accent"},
            "visual": {"padding": 24, "radius": 16, "shadow": True},
        },
        {
            "key": "note",
            "label": "Notiz 2/3",
            "data": {"size": "sm", "color": "muted"},
            "width": "w23",
        },
        # UC6-6c2: донаполнение (курс владельца — ~10 видов на тип).
        {
            "key": "headline",
            "label": "Nur Überschrift",
            "data": {"body": "", "size": "xl", "align": "center"},
        },
        {
            "key": "card",
            "label": "Weiße Karte",
            "visual": {"background": "#ffffff", "shadow": True, "radius": 16, "padding": 24},
        },
        {
            "key": "softband",
            "label": "Band auf Vollbreite",
            "width": "full",
            "data": {"align": "center"},
            "visual": {"background": "#f9fafb", "padding": 32},
        },
        {"key": "intro_left", "label": "Intro links groß", "data": {"size": "lg"}},
        {
            "key": "quote_side",
            "label": "Zitat rechts 2/3",
            "data": {"color": "muted", "size": "lg"},
            "width": "w23",
            "pos": "right",
        },
    ],
    "image": [
        {"key": "full", "label": "Vollbreite", "width": "full", "data": {"rounded": "none"}},
        {"key": "framed", "label": "Mit Schatten", "visual": {"shadow": True, "radius": 16}},
        {"key": "square", "label": "Eckig", "data": {"rounded": "none"}},
        {"key": "half", "label": "Halbbreit links", "width": "w12", "pos": "left"},
        {"key": "half_right", "label": "Halbbreit rechts", "width": "w12", "pos": "right"},
        {"key": "third", "label": "Drittel zentriert", "width": "w13"},
        {
            "key": "polaroid",
            "label": "Polaroid",
            "visual": {"background": "#ffffff", "shadow": True, "radius": 8, "padding": 12},
        },
        {
            "key": "wide_soft",
            "label": "Weich gerundet + Schatten",
            "data": {"rounded": "3xl"},
            "visual": {"shadow": True},
        },
        {"key": "narrow", "label": "Schmal 2/3", "width": "w23"},
    ],
    "image_text": [
        {"key": "right", "label": "Foto rechts", "data": {"side": "right"}},
        {
            "key": "card",
            "label": "Karte mit Schatten",
            "visual": {"shadow": True, "radius": 16, "padding": 16},
        },
        {"key": "accent", "label": "Akzent-Titel", "data": {"color": "accent", "size": "lg"}},
        {"key": "compact", "label": "Kompakt 2/3", "width": "w23", "data": {"size": "sm"}},
        {
            "key": "band",
            "label": "Band auf Vollbreite",
            "width": "full",
            "visual": {"background": "#f9fafb", "padding": 32},
        },
        {"key": "muted", "label": "Gedämpft", "data": {"color": "muted"}},
        {
            "key": "right_card",
            "label": "Foto rechts + Karte",
            "data": {"side": "right"},
            "visual": {"shadow": True, "radius": 16, "padding": 16},
        },
        {
            "key": "compact_right",
            "label": "Kompakt 2/3, Foto rechts",
            "width": "w23",
            "data": {"side": "right", "size": "sm"},
        },
        {
            "key": "accent_card",
            "label": "Akzent-Karte",
            "data": {"color": "accent"},
            "visual": {"shadow": True, "radius": 16, "padding": 16},
        },
    ],
    "button": [
        {
            "key": "framed",
            "label": "Mit Schatten",
            "visual": {"shadow": True, "radius": 16, "padding": 16},
        },
        {"key": "right", "label": "Rechtsbündig 1/3", "width": "w13", "pos": "right"},
        {"key": "left", "label": "Linksbündig 1/3", "width": "w13", "pos": "left"},
        {
            "key": "band",
            "label": "Band mit Hintergrund",
            "width": "full",
            "visual": {"background": "#f9fafb", "padding": 24},
        },
    ],
    # UC6-6f: варианты промо-блока = стили вывода скидки (style_hint; каскад —
    # явный Promotion.discount_style главнее подсказки блока).
    "promo": [
        {"key": "percent", "label": "Prozent-Badge (−30 %)", "data": {"style_hint": "percent"}},
        {"key": "badge", "label": "Betrag-Badge (−5 €)", "data": {"style_hint": "badge"}},
        {
            "key": "strikethrough",
            "label": "Durchgestrichener Preis",
            "data": {"style_hint": "strikethrough"},
        },
        {"key": "festpreis", "label": "Nur neuer Preis", "data": {"style_hint": "festpreis"}},
        {"key": "ab", "label": "Ab-Preis", "data": {"style_hint": "ab"}},
        {"key": "countdown", "label": "Countdown-Akzent", "data": {"style_hint": "countdown"}},
        {"key": "surprise", "label": "Überraschungstüte", "data": {"style_hint": "surprise"}},
        {"key": "mystery", "label": "Mystery (Preis versteckt)", "data": {"style_hint": "mystery"}},
    ],
}


def cblock_insert_preset(btype: str, variant: str) -> dict:
    """UC6-6c: поля нового C-блока при вставке — демо-данные + оверрайды пресета.
    Неизвестный/пустой variant → стандарт (только демо). Возвращает block-item
    поля (data + width/pos/newline/visual); normalize дальше валидирует."""
    out = {"data": dict(CBLOCK_DEMO_DATA.get(btype, {}))}
    for v in CBLOCK_VARIANTS.get(btype, []):
        if v["key"] == variant:
            out["data"].update(v.get("data", {}))
            for prop in ("width", "pos", "newline", "visual"):
                if prop in v:
                    out[prop] = v[prop]
            break
    return out


def _clean_cblock(item: dict) -> dict:
    """C-блок → {key, id, enabled, data}. id сохраняется (или генерится)."""
    key = item["key"]
    bid = _s(item.get("id")) or uuid.uuid4().hex[:12]
    w = item.get("width")
    f = item.get("font")
    out = {
        "key": key,
        "id": bid,
        "enabled": bool(item.get("enabled", True)),
        "data": _clean_cblock_data(key, item.get("data")),
        "hidden_on": _clean_hidden_on(item.get("hidden_on")),  # SE-3c-mid
        "width": w if w in CBLOCK_WIDTHS else "contained",  # SE-3e + UC6-3
        "font": f if f in FONTS else "",  # H1.5
    }
    # UC6-3: положение узкого блока (w23/w12) в контейнере; дефолт (центр) —
    # без ключа, чтобы старые конфиги оставались байт-в-байт.
    if item.get("pos") in ("left", "right"):
        out["pos"] = item["pos"]
    # UC6-3a: принудительный перенос — узкий блок начинает НОВЫЙ ряд.
    if item.get("newline"):
        out["newline"] = True
    # UC6-6b: visual (тень/фон/отступ/радиус) на C-блоках — ключ добавляется
    # ТОЛЬКО при ненулевых значениях (старые конфиги байт-в-байт, golden живы).
    vis = _clean_visual(item.get("visual"))
    if vis["radius"] or vis["shadow"] or vis["background"] or vis["padding"]:
        out["visual"] = vis
    return out


# SE-4a: пользовательские блок-шаблоны (многоразовые C-блоки) — {id: {key,label,data}}
# в site_config. Владелец сохраняет блок как шаблон и вставляет его в другие места.
_MAX_BLOCK_TEMPLATES = 50

# SE-4b: шаблоны страниц — {id: {label, sections}}: именованный снимок ВСЕГО набора
# секций главной. Владелец сохраняет компоновку и применяет одним кликом.
_MAX_PAGE_TEMPLATES = 20

# SE-5b: история опубликованных версий site_config — [{ts, config}] (новейшая первая).
# Откат публикации одним кликом. Хранится в самом site_config (без миграций).
_MAX_HISTORY = 8

# SE-5b/5b-2: служебные ключи, которые НЕ попадают в снимки истории (анти-рекурсия и
# чтобы автосейв-черновик `_draft` не раздувал историю). normalize() их и так дропает.
_SNAPSHOT_EXCLUDE = ("history", "_draft", "_draft_ts")


def normalize_history(raw) -> list:
    """SE-5b: история версий — список {ts:str, config:dict}. Из каждого снимка выкинуты
    служебные ключи (`history`/`_draft*` — анти-рекурсия/раздувание). Кап `_MAX_HISTORY`."""
    out = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("config"), dict):
            continue
        snap = {k: v for k, v in item["config"].items() if k not in _SNAPSHOT_EXCLUDE}
        entry = {"ts": _s(item.get("ts")), "config": snap}
        # A3: именованные версии — необязательная подпись снимка (кламп 60).
        label = _s(item.get("label"))[:60]
        if label:
            entry["label"] = label
        out.append(entry)
        if len(out) >= _MAX_HISTORY:
            break
    return out


def push_history(prev_published, existing_history, ts: str) -> list:
    """SE-5b: добавить снимок prev_published (без служебных ключей) в начало истории.
    Пустой prev (первая публикация) → история без изменений. ts — ISO-строка (передаём
    извне, чтобы функция оставалась чистой/тестируемой)."""
    snap = {k: v for k, v in (prev_published or {}).items() if k not in _SNAPSHOT_EXCLUDE}
    if not snap:
        return normalize_history(existing_history)
    return normalize_history([{"ts": ts, "config": snap}] + list(existing_history or []))


def normalize_block_templates(raw) -> dict:
    """SE-4a: привести block_templates к {id: {key, label, data}}. key ∈
    REPEATABLE_BLOCKS, data санитизируется по типу (как C-блок). Пусто → {} (без
    регрессии для legacy-конфигов)."""
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for tid, tpl in list(raw.items())[:_MAX_BLOCK_TEMPLATES]:
        if not isinstance(tpl, dict) or tpl.get("key") not in REPEATABLE_BLOCKS:
            continue
        key = tpl["key"]
        out[_s(tid) or uuid.uuid4().hex[:12]] = {
            "key": key,
            "label": _s(tpl.get("label"))[:120],
            "data": _clean_cblock_data(key, tpl.get("data")),
        }
    return out


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

# SE-3a: микрошаблоны «Quick styles» — готовые облики секции-сетки (комбинация
# существующего layout-пресета + visual radius/shadow/padding). Применяются на
# ФРОНТЕ: кнопка распаковывает пресет в обычные инпуты секции (layout/visual) →
# live-preview → Save сохраняет распакованные значения. НЕ отдельное поле config.
# Инвариант: preset ∈ LAYOUT_PRESETS; radius 0..24, padding 0..32 (как _clean_*).
MICRO_TEMPLATES = {
    "minimal": {
        "label": _("Minimal"),
        "preset": "cols3",
        "radius": 0,
        "shadow": False,
        "padding": 0,
    },
    "soft": {
        "label": _("Soft cards"),
        "preset": "cols3",
        "radius": 16,
        "shadow": True,
        "padding": 16,
    },
    "bold": {"label": _("Bold grid"), "preset": "cols4", "radius": 8, "shadow": True, "padding": 8},
    "magazine": {
        "label": _("Magazine"),
        "preset": "list",
        "radius": 0,
        "shadow": False,
        "padding": 0,
    },
    "gallery": {
        "label": _("Gallery"),
        "preset": "gallery",
        "radius": 8,
        "shadow": False,
        "padding": 0,
    },
}


def micro_templates() -> list[dict]:
    """SE-3a: список микрошаблонов для UI (ключ + поля облика)."""
    return [{"key": k, **v} for k, v in MICRO_TEMPLATES.items()]


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
_GRID_SM = {
    1: "sm:grid-cols-1",
    2: "sm:grid-cols-2",
    3: "sm:grid-cols-3",
    4: "sm:grid-cols-4",  # SE-3c: явный пер-девайс планшет до 4 колонок
}
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
    # SE-3c: явный пер-девайс планшет (1..4). 0 = «авто» (вывод из cols/mobile, как было) —
    # back-compat: legacy без tablet → прежний планшетный шаг (_SM_FROM_COLS).
    tablet = _clamp(raw.get("tablet", eff.get("tablet", 0)), 0, 4, 0)
    gap = raw.get("gap", eff.get("gap", "md"))
    if gap not in _LAYOUT_GAPS:
        gap = "md"
    width = raw.get("width", "contained")
    if width not in _LAYOUT_WIDTHS:
        width = "contained"
    return {
        "preset": preset,
        "width": width,
        "cols": cols,
        "mobile": mobile,
        "tablet": tablet,
        "gap": gap,
    }


def grid_class_string(layout) -> str:
    """Готовая Tailwind-строка грида из layout (purge-safe, из статических таблиц)."""
    lay = normalize_layout(layout if isinstance(layout, dict) else None)
    cols, mobile, gap = lay["cols"], lay["mobile"], lay["gap"]
    # SE-3c: явный планшет (tablet>0) побеждает; иначе авто-вывод (как было).
    tablet = lay.get("tablet", 0)
    sm = tablet if tablet else max(mobile, _SM_FROM_COLS[cols])
    sm = min(max(sm, 1), 4)
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

# H1 (контент-настройка секции, Q4): опциональное описание под заголовком секции
# главной — вводный текст над гридом. Те же ключи, что у заголовка. Хранится в
# config["section_intros"][key]; пусто → на витрине не выводится (виден/правится в ?preview=1).
SECTION_INTRO_KEYS = SECTION_TITLE_KEYS
_SECTION_INTRO_MAX = 300

# M20U-7: секции с ссылкой «View all» → её можно скрыть (show_all=False).
SECTION_VIEWALL_KEYS = {"categories", "products", "events", "stay_rooms", "services"}


def section_title(config, key) -> str:
    """Кастомный заголовок секции `key` (или "" → шаблон выводит дефолт)."""
    titles = (config or {}).get("section_titles")
    if isinstance(titles, dict):
        return _s(titles.get(key))[:_SECTION_TITLE_MAX]
    return ""


def section_intro(config, key) -> str:
    """H1: описание секции `key` под заголовком (или "" — нечего выводить)."""
    intros = (config or {}).get("section_intros")
    if isinstance(intros, dict):
        return _s(intros.get(key))[:_SECTION_INTRO_MAX]
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


_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _clean_radius(value) -> int:
    """SE-3d: радиус карточки 0..24px (мусор/None → 0)."""
    try:
        return max(0, min(24, int(value))) if value is not None else 0
    except (TypeError, ValueError):
        return 0


def _clean_padding(value) -> int:
    """SE-3d: внутренний отступ карточки 0..32px (мусор/None → 0)."""
    try:
        return max(0, min(32, int(value))) if value is not None else 0
    except (TypeError, ValueError):
        return 0


def _clean_bg(value) -> str:
    """SE-3d: цвет фона карточки — валидный #rrggbb или "" (= без фона)."""
    value = value.strip() if isinstance(value, str) else ""
    return value if _HEX_COLOR_RE.match(value) else ""


def _clean_visual(raw) -> dict:
    """SE-3d: привести visual-параметры секции к канону {radius,shadow,background,padding}.
    Пустые (0/false/"") = текущий облик карточки (без регрессии для legacy)."""
    v = raw if isinstance(raw, dict) else {}
    return {
        "radius": _clean_radius(v.get("radius")),
        "shadow": bool(v.get("shadow", False)),
        "background": _clean_bg(v.get("background")),
        "padding": _clean_padding(v.get("padding")),
    }


def section_visual(config, key) -> dict:
    """SE-3d: визуальные параметры секции (radius/shadow/background/padding)."""
    for item in (config or {}).get("sections", []):
        if (
            isinstance(item, dict)
            and item.get("key") == key
            and isinstance(item.get("visual"), dict)
        ):
            return _clean_visual(item["visual"])
    return _clean_visual(None)


def normalize_site_defaults(raw) -> dict:
    """SE-2d/SE-3d: глобальные дефолты стиля карточек («весь сайт»). Применяются ко
    всем сеткам витрины, если у секции/страницы нет своего visual-override. Дефолты
    0/false/"" = текущее поведение (без регрессии для legacy-конфигов)."""
    sd = raw if isinstance(raw, dict) else {}
    return {
        "card_radius": _clean_radius(sd.get("card_radius")),
        "card_shadow": bool(sd.get("card_shadow", False)),
        "card_bg": _clean_bg(sd.get("card_bg")),
        "card_padding": _clean_padding(sd.get("card_padding")),
    }


def effective_card_visual(config, key) -> dict:
    """SE-2d/SE-3d: визуальные параметры карточек секции `key` с учётом наследования.

    Пер-секционный override (любой заданный параметр) ПОБЕЖДАЕТ глобальный дефолт;
    иначе берётся глобальный стиль карточек `site_defaults` («весь сайт»). Пустой
    site_defaults → нули/false/"" = текущее поведение."""
    config = config or {}
    sec = section_visual(config, key)
    if sec["radius"] > 0 or sec["shadow"] or sec["background"] or sec["padding"] > 0:
        return sec
    sd = normalize_site_defaults(config.get("site_defaults"))
    return {
        "radius": sd["card_radius"],
        "shadow": sd["card_shadow"],
        "background": sd["card_bg"],
        "padding": sd["card_padding"],
    }


# UA4-1 (slice B): единый нормализатор конфига секций детали. Ключи/подписи/флаги
# (orderable/hideable) — в реестре `apps.core.detail_sections` (единый источник);
# здесь только нормализация сохранённого `config['<module>_detail']`. Модуль → config-
# ключ (events→event_detail, catalog→product_detail; booking/stays добавит slice C).
_DETAIL_SECTION_CONFIG_KEY = {
    "events": "event_detail",
    "catalog": "product_detail",
    "booking": "service_detail",  # slice C
    "stays": "stay_detail",  # slice C
}


def detail_section_config_key(module: str) -> str:
    """Ключ в site_config, где лежит {order?, hidden} секций детали для module."""
    return _DETAIL_SECTION_CONFIG_KEY.get(module, f"{module}_detail")


def normalize_detail_sections(raw, module: str) -> dict:
    """Привести `config['<module>_detail']` к нормальному виду по реестру:
    orderable-модуль (event) → {order:[known], hidden:[known]}; hide-only (product) →
    {hidden:[known]}. Неизвестные ключи отбрасываются."""
    keys = detail_sections.section_keys(module)
    orderable = any(s.orderable for s in detail_sections.sections_for(module))
    d = raw if isinstance(raw, dict) else {}
    hidden = sorted({k for k in (d.get("hidden") or []) if k in keys})
    if not orderable:
        return {"hidden": hidden}
    order, seen = [], set()
    for k in d.get("order") or []:
        if k in keys and k not in seen:
            order.append(k)
            seen.add(k)
    return {"order": order, "hidden": hidden}


def detail_section_hidden(config, module: str) -> set:
    """Множество СКРЫТЫХ секций детали module (для рендера/билдера)."""
    raw = (config or {}).get(detail_section_config_key(module))
    return set(normalize_detail_sections(raw, module).get("hidden", []))


def detail_section_order(config, module: str) -> list[str]:
    """Порядок ВИДИМЫХ секций детали module: сохранённый order (известные) + недостающие
    в порядке реестра, минус hidden. Пустой/мусорный config → полный список реестра."""
    keys = detail_sections.section_keys(module)
    nd = normalize_detail_sections((config or {}).get(detail_section_config_key(module)), module)
    hidden = set(nd.get("hidden", []))
    seen = set(nd.get("order", []))
    order = nd.get("order", []) + [k for k in keys if k not in seen]
    return [k for k in order if k not in hidden]


# Обратная совместимость: прежние per-архетипные имена/сигнатуры сохранены (много
# импортов в views/шаблонах) — теперь тонкие обёртки над generic-нормализатором.
# KEYS выводятся из реестра (единый источник, порядок = порядок рендера).
EVENT_DETAIL_SECTION_KEYS = detail_sections.section_keys("events")
PRODUCT_DETAIL_SECTION_KEYS = detail_sections.section_keys("catalog")


def normalize_event_detail(raw) -> dict:
    return normalize_detail_sections(raw, "events")


def event_detail_order(config) -> list[str]:
    return detail_section_order(config, "events")


def normalize_product_detail(raw) -> dict:
    return normalize_detail_sections(raw, "catalog")


def product_detail_hidden(config) -> set:
    return detail_section_hidden(config, "catalog")


# --- UC1-1 (U-C): единый реестр секций по ТИПУ СТРАНИЦЫ ---------------------
# Одна модель (page_type, section) НАД двумя существующими реестрами: home —
# SECTIONS этого модуля (первичный источник главной), детальные — реестр
# apps.core.detail_sections (UA4-1). Потребители U-C (инспектор/draft/канва)
# читают страницы ЧЕРЕЗ этот фасад, а не через частные списки. Осознанное
# отклонение от буквы uc-плана §5: реестры остаются первичными, фасад — над
# ними (цель — единый API — та же; риск для горячего normalize()-пути ниже;
# зафиксировано в uc-plan §11). page_type `listing`/`info`/`legal` — UC1-2.
PAGE_DETAIL_MODULES = {
    "product_detail": "catalog",
    "event_detail": "events",
    "service_detail": "booking",
    "stay_detail": "stays",
}

# UC1-2: не-детальные page_type. Слоты листинга — структурные блоки каркаса
# `listing.html` (U-B); скрытие/порядок пока НЕ управляются конфигом — реестр
# даёт инспектору знание страницы, управление придёт с UC2-3/UC3-2. info/legal —
# first-class страницы текстового контента (D3; AGB — E-2/L5 через LegalDoc).
LISTING_SECTIONS = (
    ("header", _("Header & intro")),
    ("facets", _("Filters")),
    ("toolbar", _("Search & sort")),
    ("grid", _("Items grid")),
    ("pagination", _("Pagination")),
    ("empty", _("Empty state")),
    ("after", _("After-content")),
)
INFO_SECTIONS = (("about", _("About us")),)
LEGAL_SECTIONS = (
    ("impressum", "Impressum"),
    ("datenschutz", "Datenschutz"),
    ("widerruf", "Widerruf"),
    ("agb", "AGB"),  # E-2/L5: страница есть только при заданном LegalDoc-тексте
)
_STATIC_PAGE_SECTIONS = {
    "listing": LISTING_SECTIONS,
    "info": INFO_SECTIONS,
    "legal": LEGAL_SECTIONS,
}


def page_types() -> tuple[str, ...]:
    """Все page_type единого реестра: главная + детальные + листинг + инфо/право."""
    return ("home", *PAGE_DETAIL_MODULES, *_STATIC_PAGE_SECTIONS)


def page_section_keys(page_type: str) -> tuple[str, ...]:
    """Ключи секций страницы в дефолтном порядке; неизвестный page_type → ()."""
    if page_type == "home":
        return tuple(key for key, _label, _on in SECTIONS)
    if page_type in _STATIC_PAGE_SECTIONS:
        return tuple(key for key, _label in _STATIC_PAGE_SECTIONS[page_type])
    module = PAGE_DETAIL_MODULES.get(page_type)
    return detail_sections.section_keys(module) if module else ()


def page_section_labels(page_type: str) -> dict:
    """{key: lazy label} секций страницы — единый источник подписей инспектора."""
    if page_type == "home":
        return {key: label for key, label, _on in SECTIONS}
    if page_type in _STATIC_PAGE_SECTIONS:
        return dict(_STATIC_PAGE_SECTIONS[page_type])
    module = PAGE_DETAIL_MODULES.get(page_type)
    return detail_sections.section_labels(module) if module else {}


# UC1-3 (SE-9c): эмодзи-иконки секций ГЛАВНОЙ для рейла билдера (перенос из
# apps/core/views.py — реестр держит KEYS+LABELS+ICONS вместе). Дефолт — 🧩.
SECTION_ICONS = {
    "hero": "🖼",
    "usp_bar": "✨",
    "stay_search": "🔎",
    "stay_rooms": "🛏️",
    "services": "🛠️",
    "promotions": "🏷️",
    "categories": "🗂️",
    "products": "🛍️",
    "events": "📅",
    "archetypes": "🧭",
    "about": "ℹ️",
    "process": "🪜",
    "team": "👥",
    "cta": "📣",
    "testimonials": "💬",
    "trust": "🛡️",
    "reviews": "⭐",
    "faq": "❓",
    "gallery": "🏞️",
    "before_after": "🔁",
    "contact": "✉️",
}


def page_section_icons(page_type: str) -> dict:
    """{key: emoji} секций страницы; для страниц без своих иконок — {} (потребитель
    подставляет дефолт 🧩)."""
    return dict(SECTION_ICONS) if page_type == "home" else {}


def page_inspector(config, page_type: str) -> list[dict]:
    """UC1-3: строки инспектора секций ДЕТАЛЬНОЙ страницы из единого реестра —
    [{key, label, visible[, order]}]. hide-only модули — порядок реестра; orderable
    (event) — сохранённый порядок + order (1-based), как строил home_builder_view
    вручную. home — НЕ здесь (свой формат с layout/visual/…); не-детальный
    page_type → [] (fail-safe)."""
    module = PAGE_DETAIL_MODULES.get(page_type)
    if module is None:
        return []
    nd = normalize_detail_sections((config or {}).get(detail_section_config_key(module)), module)
    hidden = set(nd.get("hidden", []))
    keys = detail_sections.section_keys(module)
    labels = detail_sections.section_labels(module)
    if not any(s.orderable for s in detail_sections.sections_for(module)):
        return [{"key": k, "label": labels.get(k, k), "visible": k not in hidden} for k in keys]
    seen = set(nd.get("order", []))
    full = nd.get("order", []) + [k for k in keys if k not in seen]
    return [
        {"key": k, "label": labels.get(k, k), "order": i + 1, "visible": k not in hidden}
        for i, k in enumerate(full)
    ]


def page_sections(config, page_type: str) -> list[str]:
    """Упорядоченные ВИДИМЫЕ ключи секций страницы из конфига — ЛЮБОЙ page_type.

    home: enabled фикс-секции и включённые C-блоки в порядке конфига; детальные —
    сохранённый порядок минус скрытые (делегат `detail_section_order`); listing/
    info/legal — фиксированный порядок реестра (конфиг-управление — UC2-3/UC3-2).
    Неизвестный page_type → [] (fail-safe). `normalize_sections` определён ниже —
    поздняя привязка в runtime, порядок объявлений в модуле не важен."""
    config = config if isinstance(config, dict) else {}
    if page_type == "home":
        entries = normalize_sections(config.get("sections", []))
        return [e["key"] for e in entries if e.get("enabled")]
    if page_type in _STATIC_PAGE_SECTIONS:
        return list(page_section_keys(page_type))
    module = PAGE_DETAIL_MODULES.get(page_type)
    if module is None:
        return []
    return detail_section_order(config, module)


# Сортировка каталога: ключи валидны для keyset-пагинации (поле — реальная колонка БД,
# не JSON-имя). Маппинг ключ→(поле, descending) живёт во вьюхе product_list.
CATALOG_SORT_KEYS = ("newest", "price_asc", "price_desc")


# --- UC2-1: page-scoped draft-модуль --------------------------------------------
# Единая декларация «какие плоские конфиг-ключи принадлежат какому page_type» +
# generic-наложение per-page ключей драфта. Хранение ОСТАЁТСЯ плоским (решение
# «виртуальный фасад», docs/uc2-1-page-draft-plan-2026-07-02.md §2): «pages» —
# срез, не ключ конфига; normalize/history/storefront-ридеры не тронуты.
# «cart» есть в реестре, но не в page_types() — у корзины нет своей страницы
# редактора, её ключ правится панелью каталога.
_PAGE_DETAIL_KEYS = ("event_detail", "product_detail", "service_detail", "stay_detail")
_PAGE_LAYOUT_KEYS = (
    "catalog_layout",
    "events_index_layout",
    "stay_index_layout",
    "service_index_layout",
)
_PAGE_BOOL_KEYS = ("catalog_show_filters", "catalog_subcats_first", "cart_show_upsell")

PAGE_CONFIG_KEYS = {
    "home": (),  # sections/section_titles/… — собственный generic-путь драфта
    "product_detail": ("product_detail",),
    "event_detail": ("event_detail",),
    "service_detail": ("service_detail",),
    "stay_detail": ("stay_detail",),
    "listing": (
        "catalog_layout",
        "events_index_layout",
        "stay_index_layout",
        "service_index_layout",
        "catalog_show_filters",
        "catalog_sort",
        "catalog_subcats_first",
    ),
    "cart": ("cart_show_upsell",),
    "info": (),
    "legal": (),
}


def apply_page_payload(cfg: dict, data: dict) -> None:
    """Generic-наложение page-scoped ключей драфта на конфиг (UC2-1, слайс B).

    Семантика 1:1 с прежними per-page ветками site_preview_draft: детальные —
    dict как есть (normalize_* чистят на следующем normalize), раскладки —
    только валидный preset (⚠️ service_index_layout не материализуется
    normalize'ом — особенность сохранена: кладём только присланный валидный),
    флаги — строгий bool, сортировка — по CATALOG_SORT_KEYS. Невалидное
    молча игнорируется (драфт fail-safe, как раньше)."""
    for key in _PAGE_DETAIL_KEYS:
        if isinstance(data.get(key), dict):
            cfg[key] = data[key]
    for key in _PAGE_LAYOUT_KEYS:
        lay = data.get(key)
        if isinstance(lay, dict) and lay.get("preset") in LAYOUT_PRESETS:
            cfg[key] = {"preset": lay["preset"]}
    for key in _PAGE_BOOL_KEYS:
        if isinstance(data.get(key), bool):
            cfg[key] = data[key]
    if data.get("catalog_sort") in CATALOG_SORT_KEYS:
        cfg["catalog_sort"] = data["catalog_sort"]


def page_config(config, page_type: str) -> dict:
    """Срез нормализованного конфига для page_type — {key: value} по реестру.

    Ключи, отсутствующие в нормализованном конфиге (напр. нематериализованный
    service_index_layout), не попадают в срез. Неизвестный page_type → {}."""
    cfg = normalize(config)
    return {k: cfg[k] for k in PAGE_CONFIG_KEYS.get(page_type, ()) if k in cfg}


TEXT_FIELDS = [
    "hero_title",
    "hero_text",
    "about_title",
    "about_text",
    # H1.2: заголовок и интро страницы каталога (сущность «список»), правятся инлайн.
    "catalog_title",
    "catalog_intro",
    # Заголовок и примечание страницы корзины — правятся инлайн на канве.
    "cart_title",
    "cart_note",
    # Заголовок блока кросс-селла («Passt dazu») в корзине — правится инлайн.
    "cart_upsell_title",
    # H1.2: тэглайн подвала сайта (виден на всех страницах), правится инлайн.
    "footer_text",
]

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
    # i18n (двуязычная витрина): переводы подписи узла {"de":..,"en":..}; пусто →
    # одноязычно (label). menu._resolve выбирает по локали. Ключ добавляем только
    # при наличии переводов — легаси-меню не раздуваем.
    li18n = raw.get("label_i18n")
    if isinstance(li18n, dict):
        clean_li18n = {loc: _s(v) for loc, v in li18n.items() if loc in ("de", "en") and _s(v)}
        if clean_li18n:
            node["label_i18n"] = clean_li18n
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


# SE-3b: глобальная типографика витрины. Намеренно НЕ управляем абсолютным
# размером шрифта — витрина на Tailwind с фикс-классами text-* (em-каскад почти не
# работает, а единый размер заголовков сломал бы типошкалу). Управляем тем, что
# ложится чисто: НАЧЕРТАНИЕ заголовков (вес) и МЕЖСТРОЧНЫЙ интервал тела. Пары
# шрифтов — отдельный контрол `font` (FONTS). Пустые (0/0.0) = дефолт без регрессии.
FONT_WEIGHTS = (300, 400, 500, 600, 700, 800)


def _clean_weight(value) -> int:
    """SE-3b: начертание из набора FONT_WEIGHTS (иначе 0 = «не задано»)."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return 0
    return v if v in FONT_WEIGHTS else 0


def _clean_line_height(value) -> float:
    """SE-3b: межстрочный интервал 1.0..2.0 (иначе 0.0 = «не задан»)."""
    if value in (None, ""):
        return 0.0
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(v, 2) if 1.0 <= v <= 2.0 else 0.0


def normalize_typography(raw) -> dict:
    """SE-3b: глобальная типографика {weight_head, line_height}. Пустые = дефолт."""
    t = raw if isinstance(raw, dict) else {}
    return {
        "weight_head": _clean_weight(t.get("weight_head")),
        "line_height": _clean_line_height(t.get("line_height")),
    }


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


# --- i18n (мультиязычная витрина): платформенный механизм, переводы — у тенанта -
# Базовая локаль site_config — `LANGUAGE_CODE` (немецкий): значения-строки, как
# раньше. Переводы других локалей живут оверлеем config["i18n"][locale] =
# {<зеркало текстовых полей>} и накладываются `localize()` перед рендером. Механизм
# есть у каждого тенанта. Базовый рендер (DE) не меняется — нулевой риск регрессий.
#
# L1 (Волна L): множество оверлей-локалей — ГЕНЕРИК по реестру `settings.LANGUAGES`
# (все языки платформы, кроме базовой), а НЕ захардкоженный ("en",). Добавить язык
# в систему = добавить локаль в `settings.LANGUAGES` (+ `.po/.mo`), без правки этого
# кода. `normalize()` — tenant-free (десятки вызовов), поэтому фильтруем по реестру;
# per-tenant «какие из них показывать» решает `Tenant.active_locales` (переключатель/
# set_language). Данные оверлея переживают выключение локали у тенанта.
def overlay_locales() -> set[str]:
    """Локали-оверлеи = все языки реестра, кроме базовой (`LANGUAGE_CODE` хранится
    как базовые строки site_config, оверлеить её незачем)."""
    from django.conf import settings

    return {code for code, _label in settings.LANGUAGES} - {settings.LANGUAGE_CODE}


def _clean_i18n(raw) -> dict:
    """Оставить только оверлеи поддерживаемых (реестром) локалей (dict→dict).
    Структуру оверлея не валидируем строго — `localize` накладывает лишь совпадающие
    по форме поля (см. `_deep_overlay`)."""
    if not isinstance(raw, dict):
        return {}
    allowed = overlay_locales()
    return {loc: ov for loc, ov in raw.items() if loc in allowed and isinstance(ov, dict)}


def _deep_overlay(base: dict, ov: dict) -> None:
    """Наложить оверлей `ov` на `base` на месте: dict∘dict — рекурсивно, list∘list —
    позиционно (i-й перевод поверх i-го базового dict; лишние элементы оверлея
    игнорируем — перевод не плодит секций), иначе значение оверлея замещает."""
    for key, val in ov.items():
        cur = base.get(key)
        if isinstance(val, dict) and isinstance(cur, dict):
            _deep_overlay(cur, val)
        elif isinstance(val, list) and isinstance(cur, list):
            for i, item in enumerate(val):
                if i >= len(cur):
                    break
                if isinstance(item, dict) and isinstance(cur[i], dict):
                    _deep_overlay(cur[i], item)
                else:
                    cur[i] = item
        else:
            base[key] = val


def localize(config: dict, locale: str | None) -> dict:
    """Свернуть нормализованный site_config к строкам текущей локали.

    Накладывает оверлей `config["i18n"][locale]` поверх базовых (DE) значений и
    убирает служебный ключ `i18n` (шаблоны получают обычные строки). locale пустой
    или базовый (нет оверлея) → базовые значения. Чистая копия — вход не мутируется.
    """
    import copy

    base = copy.deepcopy(config if isinstance(config, dict) else {})
    overlay = base.pop("i18n", None) or {}
    ov = overlay.get(locale) if locale else None
    if isinstance(ov, dict):
        _deep_overlay(base, ov)
    return base


# UC6-6d: варианты отображения фикс-секций («FAQ — 5 примеров» — фидбэк
# владельца). "" (без ключа) = стандартный вид — старые конфиги байт-в-байт.
# Расширяемый реестр: новые секции со стилями добавлять сюда + ветвление в
# шаблоне секции по section_row.style.
SECTION_STYLES = {
    "faq": ("list", "twocol", "cards", "numbered"),  # "" = аккордеон (текущий)
    # UC6-6d2: «подобные FAQ» — отзывы и шаги (по 5 видов с дефолтом).
    "testimonials": ("quotes", "list", "accent", "single"),  # "" = карточки-сетка
    "process": ("timeline", "row", "minimal", "twocol"),  # "" = карточки с кружками
    # UC6-6f: остальные секции по фидбэку владельца.
    "gallery": ("strip", "large", "polaroid", "soft"),  # "" = квадратная сетка
    "team": ("circles", "list", "compact"),  # "" = карточки-сетка
    "trust": ("left", "badges", "plain"),  # "" = карточка по центру
}
# Лейблы вариантов для селекта билдера (DE — как прочий канва-контент).
SECTION_STYLE_LABELS = {
    "list": "Offene Liste",
    "twocol": "Zwei Spalten",
    "cards": "Karten",
    "numbered": "Nummeriert",
    "quotes": "Große Zitate",
    "accent": "Akzent-Rand",
    "single": "Einzeln zentriert",
    "timeline": "Zeitstrahl",
    "row": "In einer Reihe",
    "minimal": "Minimal",
    "strip": "Filmstreifen",
    "large": "Große Kacheln",
    "polaroid": "Polaroid",
    "soft": "Stark gerundet",
    "circles": "Runde Fotos",
    "compact": "Kompakt",
    "left": "Linksbündig",
    "badges": "Abzeichen",
    "plain": "Ohne Karte",
}

# UC6-6f: подсказка стиля скидки у промо-БЛОКА (фидбэк владельца «пресеты промо-
# блока из 7 стилей»). Источник стиля един — Promotion.discount_style (решение
# UE2-2); hint блока применяется ТОЛЬКО когда у акции стиль не задан ("").
# Ключи = Promotion.DISCOUNT_STYLES (дублируем константой: siteconfig не
# импортирует модели приложений).
PROMO_STYLE_HINTS = (
    "percent",
    "badge",
    "strikethrough",
    "festpreis",
    "ab",
    "countdown",
    "surprise",
    "mystery",
)


def _section_entry(key, enabled, raw_item):
    """Нормализовать одну фикс-секцию (порядок/видимость/layout/visual/hidden_on)."""
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
    # SE-3d: визуальные параметры (radius/shadow/background/padding) — для всех
    # секций кроме C-блоков. Пустые = текущий облик (без регрессии для legacy).
    entry["visual"] = _clean_visual(raw_item.get("visual"))
    # SE-3c-mid: скрыть секцию на устройствах (mobile/tablet/desktop). Пусто = везде.
    entry["hidden_on"] = _clean_hidden_on(raw_item.get("hidden_on"))
    # SE-3e: ширина контейнера секции — "contained" (в общем макс-контейнере) или
    # "full" (во всю ширину экрана, full-bleed). Действует на ЛЮБУЮ секцию (не только
    # сетки); общий размер контейнера задан в шаблоне (_base.html max-w-7xl).
    w = raw_item.get("width")
    entry["width"] = w if w in _LAYOUT_WIDTHS else "contained"
    # H1.5: пер-секционный шрифт (пара body/head из FONTS) — оверрайд глобального для
    # текстов этой секции. "" = наследовать глобальный (без регрессии).
    f = raw_item.get("font")
    entry["font"] = f if f in FONTS else ""
    # UC6-6d: вариант отображения секции (SECTION_STYLES); дефолт — БЕЗ ключа
    # (старые конфиги байт-в-байт, golden живы).
    if raw_item.get("style") in SECTION_STYLES.get(key, ()):
        entry["style"] = raw_item["style"]
    return entry


def normalize_sections(raw_sections) -> list:
    """Привести список секций к валидной схеме: фикс-секции дедупятся и дописываются
    в конец со своими дефолтами, C-блоки сохраняют порядок (кап `_MAX_CBLOCKS`).

    Вынесено в module-level (SE-4b), чтобы переиспользовать и для снимков page-шаблонов.
    """
    seen = set()
    sections = []
    cblocks = 0
    for item in raw_sections if isinstance(raw_sections, list) else []:
        key = item.get("key") if isinstance(item, dict) else None
        if key in _KNOWN and key not in seen:
            sections.append(_section_entry(key, bool(item.get("enabled")), item))
            seen.add(key)
        elif key in REPEATABLE_BLOCKS and cblocks < _MAX_CBLOCKS:
            # D.2: C-блоки множественные — порядок сохраняем, по key не дедупим.
            sections.append(_clean_cblock(item))
            cblocks += 1
    for key, _label, enabled in SECTIONS:
        if key not in seen:
            sections.append(_section_entry(key, enabled, None))
    return sections


def normalize_page_templates(raw) -> dict:
    """SE-4b: привести page_templates к {id: {label, sections}}. sections прогоняются
    через `normalize_sections` (та же санитизация, что и для главной). Пусто → {}
    (без регрессии для legacy-конфигов). Кап `_MAX_PAGE_TEMPLATES`."""
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for tid, tpl in list(raw.items())[:_MAX_PAGE_TEMPLATES]:
        if not isinstance(tpl, dict):
            continue
        out[_s(tid) or uuid.uuid4().hex[:12]] = {
            "label": _s(tpl.get("label"))[:120],
            "sections": normalize_sections(tpl.get("sections")),
        }
    return out


def normalize(config) -> dict:
    """Привести произвольный site_config к валидной схеме.

    Неизвестные секции отбрасываются, отсутствующие дописываются в конец со
    своим дефолтом — старые конфиги переживают добавление новых секций.
    """
    config = config if isinstance(config, dict) else {}

    normalized = {"sections": normalize_sections(config.get("sections", []))}
    # SE-4a: пользовательские блок-шаблоны (переживают нормализацию).
    normalized["block_templates"] = normalize_block_templates(config.get("block_templates"))
    # SE-4b: шаблоны страниц (снимки компоновки секций).
    normalized["page_templates"] = normalize_page_templates(config.get("page_templates"))
    # SE-5b: история опубликованных версий (откат публикации).
    normalized["history"] = normalize_history(config.get("history"))
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
    # SE-3b: глобальная типографика (начертание заголовков + межстрочный интервал).
    normalized["typography"] = normalize_typography(config.get("typography"))
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
    # Показывать ли фасет-фильтры (диеты) на странице каталога. Дефолт True (как было).
    normalized["catalog_show_filters"] = bool(config.get("catalog_show_filters", True))
    # Сортировка каталога по умолчанию (keyset-пагинация поддерживает поле+направление).
    _sort = config.get("catalog_sort")
    normalized["catalog_sort"] = _sort if _sort in CATALOG_SORT_KEYS else "newest"
    # Показывать ли подкатегории карточками первыми (при выбранной категории). Дефолт True.
    normalized["catalog_subcats_first"] = bool(config.get("catalog_subcats_first", True))
    # Показывать ли блок кросс-селла («Passt dazu») в корзине. Дефолт True (как было).
    normalized["cart_show_upsell"] = bool(config.get("cart_show_upsell", True))
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
    # UB1-1 (per-page): раскладка листинга услуг /termin/. В отличие от соседей ключ
    # НЕ материализуется на каждом normalize: его отсутствие = легаси-грид шаблона
    # (пиксельная неизменность ненастроенных витрин). Появляется, когда владелец
    # выбрал пресет на канве; выбор «Standard» удаляет ключ (home_builder POST).
    if isinstance(config.get("service_index_layout"), dict):
        normalized["service_index_layout"] = normalize_layout(
            config["service_index_layout"], {"preset": "cols2"}
        )
    # M20U-4: порядок/видимость тематических секций детальной события.
    normalized["event_detail"] = normalize_event_detail(config.get("event_detail"))
    # Видимость опциональных секций детальной товара (описание/инфо/отзывы/похожие).
    normalized["product_detail"] = normalize_product_detail(config.get("product_detail"))
    # UA4-1 slice C: видимость секций детальной услуги/номера (generic-нормализатор).
    normalized["service_detail"] = normalize_detail_sections(
        config.get("service_detail"), "booking"
    )
    normalized["stay_detail"] = normalize_detail_sections(config.get("stay_detail"), "stays")
    # SE-2d: глобальные дефолты стиля карточек («весь сайт»; наследуются сетками
    # без своего visual-override). Пустые 0/false → без регрессии для legacy.
    normalized["site_defaults"] = normalize_site_defaults(config.get("site_defaults"))
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
    # H1: описания секций главной (контент-настройка Q4) — те же правила, что у заголовков.
    intros = config.get("section_intros")
    clean_intros = {}
    if isinstance(intros, dict):
        for key, value in intros.items():
            if key in SECTION_INTRO_KEYS and isinstance(value, str) and _s(value):
                clean_intros[key] = _s(value)[:_SECTION_INTRO_MAX]
    normalized["section_intros"] = clean_intros
    # Состояние Onboarding-Wizard (D0c) живёт в том же JSON — сохранение
    # конструктора не должно его затирать.
    if isinstance(config.get("onboarding"), dict):
        normalized["onboarding"] = config["onboarding"]
    # Реестр id демо-контента (M20, apps.tenants.demo) — чтобы «Demo löschen»
    # удалил ровно созданное. Тоже переживает сохранение конструктора.
    if isinstance(config.get("demo"), dict):
        normalized["demo"] = config["demo"]
    # i18n-оверлеи переводов (двуязычная витрина) — переживают нормализацию;
    # `localize()` накладывает их перед рендером. Базовый рендер (DE) не трогаем.
    i18n = _clean_i18n(config.get("i18n"))
    if i18n:
        normalized["i18n"] = i18n
    return normalized


def enabled_sections(tenant) -> list[str]:
    """Упорядоченные ключи включённых секций главной для витрины."""
    return [s["key"] for s in normalize(tenant.site_config)["sections"] if s["enabled"]]
