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

from apps.catalog.category_styles import VALID_PAGE_STYLES as _CATEGORY_PAGE_STYLES
from apps.catalog.option_styles import VARIANT_STYLE_KEYS as _CATALOG_VARIANT_STYLE_KEYS
from apps.core import card_forms, detail_sections
from apps.core.hero_tiles import HERO_TILE_WIDGETS

# E4/2026-07-30: допустимые значения site_defaults.hero_widget — кастомные ветки
# `sections/_hero_widget.html` + архетипы из реестра плиток `core.hero_tiles`
# (иначе normalize выбросил бы ключ и первый экран потерял бы направления).
HERO_WIDGETS = (
    "stays",
    "services",
    "gastro",
    "bakery",
    "butcher",
    "mode",
) + HERO_TILE_WIDGETS

# O-2: допустимые значения дефолтного вида выбора вариантов. Берём ИЗ реестра
# каталога (option_styles тянет только gettext — моделей не грузит), чтобы
# список не разъехался с витриной и кабинетом. "" отбрасываем: это дефолт,
# в конфиге он не материализуется (golden целы).
_VARIANT_STYLE_KEYS = tuple(k for k in _CATALOG_VARIANT_STYLE_KEYS if k)

# DL-20: то же для шаблона страницы категории — источник один, реестр каталога.
_CATEGORY_PAGE_STYLE_KEYS = tuple(k for k in _CATEGORY_PAGE_STYLES if k)

# (key, подпись для кабинета, включена ли по умолчанию)
SECTIONS = [
    ("hero", _("Welcome banner"), False),
    # A.3 (T-B): тонкая «полоса доверия» под hero — иконка+подпись (Versand/Widerruf/
    # sichere Zahlung/Meisterbetrieb…). Выкл по умолчанию; показываем при наличии пунктов.
    ("usp_bar", _("Trust bar"), False),
    # FD-2: CTA-полоса Finder («вопросы → 3 предложения») — первый вопрос чипами.
    # ОПЦИЯ (решение владельца 2026-07-18): выкл по умолчанию; рендер дополнительно
    # гейтится finder.enabled (голден-регенерация 2026-07-18 — см. build-log).
    ("finder", _("Finder"), False),
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
    # MT-F1: тур-продукты (мото/квадро-туры). Главный товар тур-оператора жил
    # только на /touren/, поэтому его главная выглядела пустой. Выкл по
    # умолчанию; рендер дополнительно гейтится модулем events И наличием
    # опубликованных туров. ⚠️ Осознанная регенерация golden (новая известная
    # секция дописывается normalize'ом — прецедент FD-2/DS-3b).
    ("tours", _("Tours"), False),
    # S2: сетка тизеров активных архетипов («Наши разделы / Unsere Bereiche»).
    # По умолчанию выкл — легаси-витрины не затронуты; включают в кабинете/демо.
    # HF-1 (фидбэк владельца 2026-07-31, п. 14): лента новостей/блога на главной.
    # Выкл по умолчанию; рендер дополнительно гейтится активным модулем blog и
    # наличием опубликованных постов — пустой секции не появится.
    ("blog", _("News"), False),
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
    # DS-3b/4b (Fokus): мини-форма заявки НА ГЛАВНОЙ (поля AF-1; партиал AF-2,
    # гейт модуля jobs внутри). Выкл по умолчанию; ПОЗИЦИЯ — в конце страницы
    # (макет: доверие → форма → футер). ⚠️ Осознанная регенерация golden.
    ("anfrage", _("Anfrage"), False),
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
REPEATABLE_BLOCKS = (
    "text",
    "image",
    "image_text",
    "button",
    "spacer",
    "promo",
    "stats",
    "newsletter",
)
_MAX_CBLOCKS = 30
_MAX_STAT_ITEMS = 4  # GK-4: пар «число+подпись» в полосе цифр (больше — шум)


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
    # UC2-3(b): ссылочные секции-справочники — без собственных данных (контент
    # глобальный site.<key>; оси width/pos/visual — общие оси C-блока).
    if key in PAGE_REF_BLOCKS:
        return {}
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
    if key == "spacer":
        # ST-7a: высота отступа — только НЕ-дефолтные валидные значения
        # ("" = py-6 как раньше → ключа нет, старые конфиги байт-в-байт).
        return {"height": d["height"]} if d.get("height") in ("sm", "lg", "xl") else {}
    if key == "newsletter":
        # GK-8: блок подписки — форма рендерится ВСЕГДА (дефолтные msgid), данные
        # лишь оверрайды заголовка/текста/кнопки; всё пустое → {} (presence-minimal).
        out = {
            k: v
            for k, v in {
                "title": _s(d.get("title"))[:80],
                "body": _s(d.get("body"))[:200],
                "button_label": _s(d.get("button_label"))[:40],
            }.items()
            if v
        }
        return out
    if key == "stats":
        # GK-4: полоса цифр — rows = [{value, label}] (НЕ "items": у dict в Django-
        # шаблоне .items — метод). Принимает и текст textarea «wert | label» построчно
        # (live-draft канал шлёт сырое поле формы) — канонизируем в список.
        raw_rows = d.get("rows")
        if isinstance(raw_rows, str):
            raw_rows = [
                {"value": v.strip(), "label": lbl.strip()}
                for v, _, lbl in (line.partition("|") for line in raw_rows.splitlines())
                if v.strip()
            ]
        rows = []
        for item in raw_rows if isinstance(raw_rows, list) else []:
            if not isinstance(item, dict) or not _s(item.get("value")):
                continue
            rows.append({"value": _s(item.get("value"))[:12], "label": _s(item.get("label"))[:40]})
            if len(rows) >= _MAX_STAT_ITEMS:
                break
        return {"rows": rows} if rows else {}
    return {}


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
    # GK-8: демо-оверрайды блока подписки (round-trip замок builder).
    "newsletter": {
        "title": "Bleiben Sie auf dem Laufenden",
        "body": "Neuigkeiten und Angebote — kein Spam, jederzeit abbestellbar.",
    },
    # GK-4: демо ОБЯЗАНО быть байт-в-байт равно _clean_cblock_data("stats", demo)
    # (замок test_cblocks_builder: round-trip demo-данных).
    "stats": {
        "rows": [
            {"value": "12", "label": "Jahre Erfahrung"},
            {"value": "500+", "label": "zufriedene Kunden"},
            {"value": "4,9 ★", "label": "Bewertung"},
        ]
    },
}


# UC6-6c: пресеты отображения при вставке блока («выбор шаблона с преднастрой-
# ками и демо-данными» — фидбэк владельца). Стандарт (key "") — голые демо-
# данные CBLOCK_DEMO_DATA; каждый пресет — оверрайды поверх демо: data-ключи
# и/или block-props (width/pos/newline/visual). Лейблы DE — как демо-контент.
CBLOCK_VARIANTS = {
    "text": [
        {"key": "intro", "label": _("Intro zentriert"), "data": {"align": "center", "size": "lg"}},
        {
            "key": "quote",
            "label": _("Zitat"),
            "data": {"align": "center", "size": "lg", "color": "muted"},
            "visual": {"padding": 24},
        },
        {
            "key": "banner",
            "label": _("Akzent-Banner"),
            "data": {"align": "center", "size": "xl", "color": "accent"},
            "visual": {"padding": 24, "radius": 16, "shadow": True},
        },
        {
            "key": "note",
            "label": _("Notiz 2/3"),
            "data": {"size": "sm", "color": "muted"},
            "width": "w23",
        },
        # UC6-6c2: донаполнение (курс владельца — ~10 видов на тип).
        {
            "key": "headline",
            "label": _("Nur Überschrift"),
            "data": {"body": "", "size": "xl", "align": "center"},
        },
        {
            "key": "card",
            "label": _("Weiße Karte"),
            "visual": {"background": "#ffffff", "shadow": True, "radius": 16, "padding": 24},
        },
        {
            "key": "softband",
            "label": _("Band auf Vollbreite"),
            "width": "full",
            "data": {"align": "center"},
            "visual": {"background": "#f9fafb", "padding": 32},
        },
        {"key": "intro_left", "label": _("Intro links groß"), "data": {"size": "lg"}},
        {
            "key": "quote_side",
            "label": _("Zitat rechts 2/3"),
            "data": {"color": "muted", "size": "lg"},
            "width": "w23",
            "pos": "right",
        },
        # UC6-8: донаполнение до 10 видов на тип.
        {
            "key": "small_note_left",
            "label": _("Kleiner Hinweis links 1/3"),
            "data": {"size": "sm", "color": "muted"},
            "width": "w13",
            "pos": "left",
        },
    ],
    "image": [
        {"key": "full", "label": _("Vollbreite"), "width": "full", "data": {"rounded": "none"}},
        {"key": "framed", "label": _("Mit Schatten"), "visual": {"shadow": True, "radius": 16}},
        {"key": "square", "label": _("Eckig"), "data": {"rounded": "none"}},
        {"key": "half", "label": _("Halbbreit links"), "width": "w12", "pos": "left"},
        {"key": "half_right", "label": _("Halbbreit rechts"), "width": "w12", "pos": "right"},
        {"key": "third", "label": _("Drittel zentriert"), "width": "w13"},
        {
            "key": "polaroid",
            "label": _("Polaroid"),
            "visual": {"background": "#ffffff", "shadow": True, "radius": 8, "padding": 12},
        },
        {
            "key": "wide_soft",
            "label": _("Weich gerundet + Schatten"),
            "data": {"rounded": "3xl"},
            "visual": {"shadow": True},
        },
        {"key": "narrow", "label": _("Schmal 2/3"), "width": "w23"},
        # UC6-8: донаполнение до 10 видов.
        {"key": "quarter_right", "label": _("Viertel rechts"), "width": "w14", "pos": "right"},
    ],
    "image_text": [
        {"key": "right", "label": _("Foto rechts"), "data": {"side": "right"}},
        {
            "key": "card",
            "label": _("Karte mit Schatten"),
            "visual": {"shadow": True, "radius": 16, "padding": 16},
        },
        {"key": "accent", "label": _("Akzent-Titel"), "data": {"color": "accent", "size": "lg"}},
        {"key": "compact", "label": _("Kompakt 2/3"), "width": "w23", "data": {"size": "sm"}},
        {
            "key": "band",
            "label": _("Band auf Vollbreite"),
            "width": "full",
            "visual": {"background": "#f9fafb", "padding": 32},
        },
        {"key": "muted", "label": _("Gedämpft"), "data": {"color": "muted"}},
        {
            "key": "right_card",
            "label": _("Foto rechts + Karte"),
            "data": {"side": "right"},
            "visual": {"shadow": True, "radius": 16, "padding": 16},
        },
        {
            "key": "compact_right",
            "label": _("Kompakt 2/3, Foto rechts"),
            "width": "w23",
            "data": {"side": "right", "size": "sm"},
        },
        {
            "key": "accent_card",
            "label": _("Akzent-Karte"),
            "data": {"color": "accent"},
            "visual": {"shadow": True, "radius": 16, "padding": 16},
        },
        # UC6-8: донаполнение до 10 видов.
        {
            "key": "band_right",
            "label": _("Band Vollbreite, Foto rechts"),
            "width": "full",
            "data": {"side": "right"},
            "visual": {"background": "#f9fafb", "padding": 32},
        },
        {
            # GK-7: цитата основателя — фото сбоку, приглушённая крупная цитата;
            # только существующие data-ключи (санитайзер не расширяем).
            "key": "founder",
            "label": _("Gründer-Zitat"),
            "data": {
                "side": "right",
                "size": "lg",
                "color": "muted",
                "title": "— Anna Muster, Gründerin",
                "body": "„Wir kochen, wie wir selbst am liebsten essen: frisch, "
                "saisonal und mit Zeit für die Details.“",
                "rounded": "3xl",
            },
            "visual": {"shadow": True},
        },
    ],
    "button": [
        {
            "key": "framed",
            "label": _("Mit Schatten"),
            "visual": {"shadow": True, "radius": 16, "padding": 16},
        },
        {"key": "right", "label": _("Rechtsbündig 1/3"), "width": "w13", "pos": "right"},
        {"key": "left", "label": _("Linksbündig 1/3"), "width": "w13", "pos": "left"},
        {
            "key": "band",
            "label": _("Band mit Hintergrund"),
            "width": "full",
            "visual": {"background": "#f9fafb", "padding": 24},
        },
        # UC6-8: донаполнение до 10 видов (кнопка = label/url; варьируем ширину/
        # положение/фон-подложку — визуал применяется к обёртке .cb-box).
        {"key": "center_third", "label": _("Drittel zentriert"), "width": "w13"},
        {"key": "quarter_right", "label": _("Viertel rechts"), "width": "w14", "pos": "right"},
        {"key": "quarter_left", "label": _("Viertel links"), "width": "w14", "pos": "left"},
        {"key": "half", "label": _("Halbbreit"), "width": "w12"},
        {"key": "wide", "label": _("Vollbreite"), "width": "full"},
        {
            "key": "soft_band",
            "label": _("Weiches Band"),
            "width": "full",
            "visual": {"background": "#f3f4f6", "padding": 20, "radius": 16},
        },
    ],
    # UC6-6f: варианты промо-блока = стили вывода скидки (style_hint; каскад —
    # явный Promotion.discount_style главнее подсказки блока).
    "promo": [
        {"key": "percent", "label": _("Prozent-Badge (−30 %)"), "data": {"style_hint": "percent"}},
        {"key": "badge", "label": _("Betrag-Badge (−5 €)"), "data": {"style_hint": "badge"}},
        {
            "key": "strikethrough",
            "label": _("Durchgestrichener Preis"),
            "data": {"style_hint": "strikethrough"},
        },
        {"key": "festpreis", "label": _("Nur neuer Preis"), "data": {"style_hint": "festpreis"}},
        {"key": "ab", "label": _("Ab-Preis"), "data": {"style_hint": "ab"}},
        {"key": "countdown", "label": _("Countdown-Akzent"), "data": {"style_hint": "countdown"}},
        {"key": "surprise", "label": _("Überraschungstüte"), "data": {"style_hint": "surprise"}},
        {
            "key": "mystery",
            "label": _("Mystery (Preis versteckt)"),
            "data": {"style_hint": "mystery"},
        },
        # UC6-8: донаполнение до 10 видов (стиль скидки × раскладка).
        {
            "key": "percent_wide",
            "label": _("Prozent, Vollbreite"),
            "data": {"style_hint": "percent"},
            "width": "full",
        },
        {
            "key": "countdown_center",
            "label": _("Countdown zentriert, ohne Badge"),
            "data": {"style_hint": "countdown", "align": "center", "badge_pos": "none"},
        },
    ],
    # ST-7a: отступ — 4 высоты ("" = Standard py-6; height presence-minimal).
    "spacer": [
        {"key": "schmal", "label": _("Schmal"), "data": {"height": "sm"}},
        {"key": "standard", "label": _("Standard")},
        {"key": "gross", "label": _("Groß"), "data": {"height": "lg"}},
        {"key": "sehr_gross", "label": _("Sehr groß"), "data": {"height": "xl"}},
    ],
    # GK-4: варианты полосы цифр — только data-оси (каждый обязан пережить
    # normalize — замок variants). update() заменяет rows целиком, не доливает.
    "stats": [
        {"key": "drei", "label": _("3 Zahlen")},
        {
            "key": "vier",
            "label": _("4 Zahlen"),
            "data": {
                "rows": [
                    {"value": "12", "label": "Jahre Erfahrung"},
                    {"value": "500+", "label": "zufriedene Kunden"},
                    {"value": "10.000+", "label": "Gäste bewirtet"},
                    {"value": "4,9 ★", "label": "Bewertung"},
                ]
            },
        },
        {
            "key": "zwei",
            "label": _("2 Zahlen"),
            "data": {
                "rows": [
                    {"value": "500+", "label": "zufriedene Kunden"},
                    {"value": "4,9 ★", "label": "Bewertung"},
                ]
            },
        },
        {
            "key": "seit",
            "label": _("Seit Jahr"),
            "data": {
                "rows": [
                    {"value": "Seit 2012", "label": "für Sie da"},
                    {"value": "100 %", "label": "frisch gekocht"},
                    {"value": "4,9 ★", "label": "Bewertung"},
                ]
            },
        },
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


# UC6-7: C-блоки на ЛЮБОЙ странице — отдельный хост page_blocks
# ({page_key: [cblock,…]}); `sections` остаётся home-only (golden-паритет).
# Whitelist страниц; legal сознательно исключён (право должно быть видимым —
# DACH-риск, решение uc2-3-плана).
PAGE_BLOCK_HOSTS = (
    "catalog",
    "events",
    "stay_rooms",
    "services",
    "cart",
    "event_detail",
    "product_detail",
    "service_detail",
    "stay_detail",
    "info",
    "blog",
)

# UC2-3(b) («да» владельца 2026-07-19): ссылочные секции-справочники — типы
# блоков, разрешённые ТОЛЬКО в page_blocks (страницы), НЕ в home-sections (там
# настоящие секции; normalize_sections их отбрасывает → golden целы). Рендер —
# готовый партиал секции с ГЛОБАЛЬНЫМ справочником site.<key> (контент один на
# весь сайт, правится в конструкторе главной — честная семантика «показать
# этот блок и здесь»).
# AF-2b: + формы (anfrage_ref — заявка, гейт jobs; message_ref — контакт-форма,
# гейт inbox) — рендер общих партиалов форм, POST в штатные приёмники.
PAGE_REF_BLOCKS = (
    "faq_ref",
    "team_ref",
    "gallery_ref",
    "testimonials_ref",
    "anfrage_ref",
    "message_ref",
)


# Фидбэк 2026-08-26 («добавь на страницу кейтеринга галерею, отзывы, команду»):
# «catalog» — ОДИН хост на весь каталог, блоки появились бы и на /sortiment/, и на
# каждой странице категории. KAT-1 сделал категорию страницей, поэтому у неё может
# быть и свой набор блоков: хост «catalog:<slug>». Слаг — строгим паттерном
# (в site_config попадает только то, что похоже на слаг категории), число таких
# хостов ограничено, чтобы конфиг не рос без предела.
CATEGORY_HOST_PREFIX = "catalog:"
_MAX_CATEGORY_HOSTS = 40
# Слаг — по семантике SlugField Django (буквы/цифры/дефис/подчёркивание,
# регистр значим): у живого тенанта категория вполне может называться
# «Sommer_2026», и узкий шаблон молча выбросил бы её блоки.
_CATEGORY_HOST_RE = re.compile(r"^catalog:[-\w]{1,60}$")


def is_page_block_host(host) -> bool:
    """UC6-7 + KAT-1: допустимый хост page_blocks — фикс-страница или категория."""
    if not isinstance(host, str):
        return False
    return host in PAGE_BLOCK_HOSTS or bool(_CATEGORY_HOST_RE.match(host))


def category_host(slug) -> str:
    """Хост блоков страницы категории (пустой слаг → «», рендер тихо пропустит)."""
    slug = _s(slug)
    host = f"{CATEGORY_HOST_PREFIX}{slug}"
    return host if _CATEGORY_HOST_RE.match(host) else ""


def _page_block_hosts(raw: dict) -> list:
    """Хосты для нормализации: фикс-whitelist + категорийные из самого конфига
    (детерминированный порядок — фикс-хосты, затем категории по алфавиту)."""
    cats = sorted(k for k in raw if is_page_block_host(k) and k not in PAGE_BLOCK_HOSTS)
    return list(PAGE_BLOCK_HOSTS) + cats[:_MAX_CATEGORY_HOSTS]


def normalize_page_blocks(raw) -> dict:
    """UC6-7: привести page_blocks к {host: [cblock,…]} — whitelist хостов,
    каждый блок через _clean_cblock, кап _MAX_CBLOCKS на страницу.
    Пусто → {} (ключ в normalize добавляется presence-minimal — golden живы)."""
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for key in _page_block_hosts(raw):
        items = raw.get(key)
        if not isinstance(items, list):
            continue
        blocks = []
        for item in items:
            # UC2-3(b): на страницах, кроме обычных C-блоков, допускаются
            # ссылочные секции-справочники (PAGE_REF_BLOCKS); в home-sections
            # они по-прежнему невалидны.
            if isinstance(item, dict) and (
                item.get("key") in REPEATABLE_BLOCKS or item.get("key") in PAGE_REF_BLOCKS
            ):
                blocks.append(_clean_cblock(item))
            if len(blocks) >= _MAX_CBLOCKS:
                break
        if blocks:
            out[key] = blocks
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
    # DS-6: плитка до 6 в ряд (владелец: «плитка по 2–6 шт») — доступно всем
    # страничным пикерам раскладки.
    "cols5": {"cols": 5, "mobile": 2, "gap": "sm"},
    "cols6": {"cols": 6, "mobile": 2, "gap": "sm"},
    "gallery": {"cols": 4, "mobile": 2, "gap": "sm"},  # плотная сетка
}
LAYOUT_PRESET_KEYS = list(LAYOUT_PRESETS)
# DS-3a: НЕ-сеточные виды вывода конкретных страниц (валидны только там).
PAGE_EXTRA_PRESETS = {
    "catalog_layout": (
        "preisliste",
        "preisliste_foto",
        "preisliste_kompakt",
        "preisliste_2sp",
        # MEN-14 (запрос владельца 2026-08-13 «список с картинками в 2 и 3 колонки»):
        # те же строки с мини-фото, но сеткой — на мобильном всегда 1 колонка
        # (строка с фото и ценой в две колонки на телефоне нечитаема).
        "preisliste_foto_2sp",
        "preisliste_foto_3sp",
        "preisliste_karte",
        # MEN-16 (запрос владельца «визуализировать меню как книгу в 2 столбца
        # с листанием»): тот же прайс, но страницами-разворотами.
        "preisliste_buch",
    ),
    # MEN-18 (фидбэк 2026-08-17 «для услуг плюс список, список с картинками и
    # в 2 колонки»): прайс-виды листинга услуг /termin/. Подмножество семейства:
    # kompakt/karte/buch — гастро-виды каталога, услугам не предлагаем.
    "service_index_layout": (
        "preisliste",
        "preisliste_foto",
        "preisliste_2sp",
        "preisliste_foto_2sp",
    ),
}
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
    "tours": {"preset": "cols2", "mobile": 1},  # MT-F1: карточка поездки — крупная
    "blog": {"preset": "cols3"},  # HF-1: карточки новостей
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
# DS-5: + categories (владелец задаёт число плиток; ⚠️ материализация limit —
# осознанная golden-регенерация 2026-08-12).
# DL-13 (C4, решение владельца «лимит 9»): секция акций главной — 9 карточек
# (3 полных ряда по 3) + ссылка «Alle Aktionen» — раньше выводила ВСЕ активные
# акции (у демо 15 → главная превращалась в /aktionen/). ⚠️ материализация
# limit/show_all у promotions — осознанная golden-регенерация 2026-09-02.
GRID_SECTION_LIMITS = {
    "products": 8,
    "events": 6,
    "blog": 3,
    "categories": 30,
    "tours": 6,
    "promotions": 9,
}
# ^ дефолт categories = максимум: раньше секция выводила ВСЕ категории —
#   меньший дефолт молча отрезал бы плитки существующим сайтам (регрессия).
_SECTION_LIMIT_MAX = 30  # DS-5: было 24

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
    6: "lg:grid-cols-6",  # DS-5
}
_GRID_GAP = {"sm": "gap-3", "md": "gap-4 md:gap-6", "lg": "gap-6 md:gap-8"}
# Планшетный (sm) шаг по числу колонок десктопа — плавный спуск вниз.
_SM_FROM_COLS = {1: 1, 2: 2, 3: 2, 4: 3, 5: 3, 6: 3}  # DS-5: +6


def _clamp(value, lo, hi, default):
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def normalize_layout(raw, default=None, extra_presets=()) -> dict:
    """Привести layout секции к канону {preset, width, cols, mobile, gap}.

    Старт — пресет (из default или raw), затем ручные override. Значения клампятся;
    мусор → дефолт. Back-compat: пустой raw → раскладка из default-пресета секции.
    DS-3a: `extra_presets` — НЕ-сеточные виды конкретной страницы (напр.
    "preisliste" у каталога); grid-параметры для них берутся из "list" (шаблон
    ветвится сам), в общий реестр LAYOUT_PRESETS они не попадают — пикеры других
    страниц их не видят.
    """
    default = default or {"preset": "cols3"}
    base_preset = default.get("preset", "cols3")
    raw = raw if isinstance(raw, dict) else {}
    preset = raw.get("preset", base_preset)
    if preset not in LAYOUT_PRESETS and preset not in extra_presets:
        preset = base_preset
    eff = {
        **LAYOUT_PRESETS.get(preset, LAYOUT_PRESETS["list"]),
        **{k: v for k, v in default.items() if k != "preset"},
    }
    cols = _clamp(raw.get("cols", eff["cols"]), 1, 6, eff["cols"])  # DS-5: до 6
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
    out = {
        "preset": preset,
        "width": width,
        "cols": cols,
        "mobile": mobile,
        "tablet": tablet,
        "gap": gap,
    }
    # DS-5: симметрия неполного ряда / горизонтальный скролл — presence-minimal
    # (ключ только при True; golden целы). scroll побеждает balance в рендере.
    if raw.get("balance"):
        out["balance"] = True
    if raw.get("scroll"):
        out["scroll"] = True
    # DL-11: хвост неполного последнего ряда — "" = обрезать (дефолт, ключ НЕ
    # пишется → golden целы) | "show" = показать всё (прежнее поведение) |
    # "fill" = добить ряд плиткой-подсказкой. Рендер — CSS по data-sf-cols/
    # data-sf-tail (grid_attr_string), на каждом брейкпоинте свои колонки.
    tail = raw.get("tail")
    if tail in _LAYOUT_TAILS:
        out["tail"] = tail
    return out


# DL-14: + spread («Verteilen») — неполный последний ряд раскладывается по ширине
# (flex-wrap + space-evenly, ширина плитки как у колонки; CSS генератора).
_LAYOUT_TAILS = ("show", "fill", "spread")
_COLS_TRIPLET_RE = re.compile(r"^[1-6]/[1-6]/[1-6]$")
# DL-14 авто-колонки: элементов меньше колонок окна → колонки = число элементов,
# но не ниже пола (планшет 2, десктоп 3; телефон без изменений) — одна карточка на
# всю ширину десктопа была бы огромной. Ключа нет: применяется везде, где число
# элементов известно при рендере (count=), классы Tailwind не меняются — атрибут
# data-sf-auto + CSS переопределяют grid-template-columns.
_AUTO_COLS_FLOOR = (None, 2, 3)


def auto_cols_triplet(triplet, count) -> tuple[tuple[int, int, int], bool]:
    """(триплет после кламп-а по числу элементов, изменился ли). count ≤ 0 → 1:1."""
    if not isinstance(count, int) or count <= 0:
        return tuple(triplet), False
    out = []
    for n, floor in zip(triplet, _AUTO_COLS_FLOOR, strict=True):
        if floor is None:
            out.append(n)
        else:
            out.append(max(min(n, floor), min(n, count)))
    out = tuple(out)
    return out, out != tuple(triplet)


def grid_cols_triplet(layout) -> tuple[int, int, int]:
    """DL-11: число колонок (телефон, планшет, десктоп) из layout — ЕДИНСТВЕННЫЙ
    источник чисел для grid_class_string, атрибутов data-sf-cols и аудита демо.
    SE-3c: явный планшет (tablet>0) побеждает; иначе авто-вывод (_SM_FROM_COLS)."""
    lay = normalize_layout(layout if isinstance(layout, dict) else None)
    cols, mobile = lay["cols"], lay["mobile"]
    tablet = lay.get("tablet", 0)
    sm = tablet if tablet else max(mobile, _SM_FROM_COLS[cols])
    sm = min(max(sm, 1), 4)
    return mobile, sm, cols


def grid_class_string(layout) -> str:
    """Готовая Tailwind-строка грида из layout (purge-safe, из статических таблиц).

    DS-5: режимы scroll (горизонтальная лента со snap) и balance (flex-wrap с
    центрированием неполного ряда) подменяют grid-классы целиком — работает у
    всех секций-сеток без правок шаблонов (классы генерятся здесь центрально).
    """
    lay = normalize_layout(layout if isinstance(layout, dict) else None)
    cols, gap = lay["cols"], lay["gap"]
    if lay.get("scroll"):
        return " ".join(["sf-scroll-grid", _GRID_GAP[gap]])
    if lay.get("balance"):
        return " ".join(["sf-balance-grid", f"sf-bal-{cols}", _GRID_GAP[gap]])
    mobile, sm, cols = grid_cols_triplet(lay)
    return " ".join(["grid", _GRID_MOBILE[mobile], _GRID_SM[sm], _GRID_LG[cols], _GRID_GAP[gap]])


def grid_attr_string(layout, cols=None, tail=None, count=None, more=False, default_tail="trim"):
    """DL-11: атрибуты сетки для CSS «полных рядов»: data-sf-cols="<тел>/<планш>/<деск>"
    + data-sf-tail="trim|show|fill|spread". Классы Tailwind не трогаем (замки
    характеризации целы) — CSS в app.css (генератор scripts/gen_fill_rows_css.py)
    скрывает хвост неполного ряда (trim), растягивает плитку-подсказку .sf-filler
    (fill) или раскладывает неполный ряд по ширине (spread, DL-14) на каждом
    брейкпоинте отдельно. scroll/balance (DS-5) — своя механика → пусто.

    `cols` — переопределение триплета для хардкоженных сеток ("1/2/3"); `tail` —
    принудительный режим; `default_tail` — дефолт без ключа в раскладке (главная
    trim, листинги spread); `count` — число элементов → авто-колонки (DL-14,
    атрибут data-sf-auto); `more` — в сетке есть хвостовая кнопка .sf-more
    («Alle anzeigen» при скрытии, DL-14) — CSS считает ряды без неё."""
    lay = normalize_layout(layout if isinstance(layout, dict) else None)
    if lay.get("scroll"):
        # DL-16.1 (S1): лента получает слайдер-примитив (стрелки/точки) даром; правила
        # полных рядов к ней не применяются.
        return 'data-sf-slider="1"'
    if lay.get("balance"):
        return ""
    if isinstance(cols, str) and _COLS_TRIPLET_RE.match(cols):
        triplet = tuple(int(n) for n in cols.split("/"))
    else:
        triplet = grid_cols_triplet(lay)
    triplet, auto = auto_cols_triplet(triplet, count)
    cols = "/".join(str(n) for n in triplet)
    if tail not in _LAYOUT_TAILS and tail != "trim":
        tail = lay.get("tail") or default_tail
    attrs = f'data-sf-cols="{cols}" data-sf-tail="{tail}"'
    if auto:
        attrs += ' data-sf-auto="1"'
    if more:
        attrs += ' data-sf-more="1"'
    return attrs


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


def section_rows(config, key="products") -> int:
    """MEN-24c: кап строк на группу прайс-вида секции (0 = без капа)."""
    for item in config.get("sections", []):
        if isinstance(item, dict) and item.get("key") == key:
            return _clamp(item.get("rows"), 1, 20, 0)
    return 0


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
SECTION_TITLE_KEYS = {
    "promotions",
    "categories",
    "products",
    "events",
    "tours",
    # MT-F3: заголовок/подпись формы заявки на главной — у тур-оператора это
    # «приватный выезд», а не «смета на работы».
    "anfrage",
    "stay_rooms",
    "services",
    "blog",
}
_SECTION_TITLE_MAX = 80

# H1 (контент-настройка секции, Q4): опциональное описание под заголовком секции
# главной — вводный текст над гридом. Те же ключи, что у заголовка. Хранится в
# config["section_intros"][key]; пусто → на витрине не выводится (виден/правится в ?preview=1).
SECTION_INTRO_KEYS = SECTION_TITLE_KEYS
_SECTION_INTRO_MAX = 300

# M20U-7: секции с ссылкой «View all» → её можно скрыть (show_all=False).
SECTION_VIEWALL_KEYS = {
    "categories",
    "products",
    "promotions",  # DL-13 (C4): «Alle Aktionen» при лимите 9
    "events",
    "stay_rooms",
    "services",
    "blog",
    "tours",
}


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


def section_style(config, key) -> str:
    """Вид отображения секции `key` ("" — стандартный).

    Внутри рендера секций стиль приходит в `section_row.style`, но СТРАНИЦЫ
    (например /sortiment/) рисуются вне `render_block` — им нужен прямой ридер.
    """
    for item in (config or {}).get("sections", []):
        if isinstance(item, dict) and item.get("key") == key:
            return str(item.get("style") or "")
    return ""


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
    out = {
        "card_radius": _clean_radius(sd.get("card_radius")),
        "card_shadow": bool(sd.get("card_shadow", False)),
        "card_bg": _clean_bg(sd.get("card_bg")),
        "card_padding": _clean_padding(sd.get("card_padding")),
    }
    # ST-7c: ФОРМА карточки (архетипный вид: overlay — текст поверх фото,
    # compact — узкая строка). Ключ ТОЛЬКО при валидном не-дефолте ("" =
    # текущая форма → golden целы).
    # DL-19: допустимые значения — реестр `core.card_forms` (единственный источник;
    # раньше тот же список был захардкожен здесь, в китах и в <option> Studio).
    if sd.get("card_style") in card_forms.keys_for(card_forms.PRODUCT):
        out["card_style"] = sd["card_style"]
    # DL-16.4/DL-19: форма карточки АКЦИИ ("" | preis | regal | lookbook | deal | coupon | ring)
    if sd.get("promo_card") in card_forms.keys_for(card_forms.PROMO):
        out["promo_card"] = sd["promo_card"]
    # DL-16.4 (P2): фото на карточке товара листаются (точки/стрелки/свайп) — "on"
    if sd.get("card_slider") in ("on", True):
        out["card_slider"] = "on"
    # DL-10a (фидбэк владельца): ФОРМА кадра на карточках — "round" (круглые
    # фото) | "wide" (шире, 16:9). Пусто = зашитый в разметку вид (квадрат /
    # 3:2 / 4:3), поэтому ключ presence-minimal и golden-эталоны целы.
    if sd.get("media_shape") in ("round", "wide"):
        out["media_shape"] = sd["media_shape"]
    # O-2 (2026-08-01): дефолтный вид выбора вариантов для всего магазина; товар
    # может его переопределить. Ключ ТОЛЬКО при валидном не-пустом значении
    # ("" = выпадающий список, как раньше → golden целы).
    if sd.get("variant_style") in _VARIANT_STYLE_KEYS:
        out["variant_style"] = sd["variant_style"]
    # DL-20: ШАБЛОН СТРАНИЦЫ КАТЕГОРИИ на весь сайт; своё значение категории
    # (`Category.page_style`) его побеждает — резолвер `category_styles.page_style`.
    # Ключ ТОЛЬКО при валидном не-пустом значении ("" = Standard → golden целы).
    if sd.get("category_page_style") in _CATEGORY_PAGE_STYLE_KEYS:
        out["category_page_style"] = sd["category_page_style"]
    # E4 «задача-первым»: интерактивный hero — primary-виджет ВНУТРИ баннера
    # (первый экран = начало пути). "stays" — поиск дат; "services" — топ-услуги
    # с «Buchen». Ключ ТОЛЬКО при валидном значении ("" = обычный баннер →
    # golden целы; существующие сайты не затрагиваются).
    if sd.get("hero_widget") in HERO_WIDGETS:
        out["hero_widget"] = sd["hero_widget"]
    # DS-1: фон СТРАНИЦЫ (тёплая подложка Look-семейств: крем/песок). Ключ ТОЛЬКО
    # при валидном hex ("" = bg-gray-50 как раньше → golden целы); в тёмной теме
    # не применяется (правило в _base.html скоуплено html:not(.dark)).
    if _clean_bg(sd.get("page_bg")):
        out["page_bg"] = _clean_bg(sd.get("page_bg"))
    # DL-2: ХРОМ карточек (рамка/тень как у семейства): hard — толстая рамка +
    # жёсткая тень (проспект), hairline — волосяная линейка без тени (газета),
    # line — тонкая рамка (утилитарный/тёмный). Ключ ТОЛЬКО при валидном
    # значении ("" = прежний облик → golden целы).
    if sd.get("card_chrome") in ("hard", "hairline", "line"):
        out["card_chrome"] = sd["card_chrome"]
    return out


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
    out = normalize_detail_sections(raw, "catalog")
    # DL-16.6 (D2): раскладка секций детали товара — "" (друг под другом) | "tabs"
    # (табы на десктопе / аккордеон на мобайле); presence-minimal, golden целы.
    if isinstance(raw, dict) and raw.get("layout") == "tabs":
        out["layout"] = "tabs"
    return out


def product_detail_hidden(config) -> set:
    return detail_section_hidden(config, "catalog")


def product_detail_layout(config) -> str:
    """DL-16.6: "" | "tabs" — из нормализованного или сырого конфига."""
    pd = (config or {}).get("product_detail") if isinstance(config, dict) else None
    return "tabs" if isinstance(pd, dict) and pd.get("layout") == "tabs" else ""


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
    "anfrage": "📝",  # DS-3b: мини-форма заявки на главной
    "hero": "🖼",
    "usp_bar": "✨",
    "finder": "🧭",  # FD-2: CTA «вопросы → 3 предложения»
    "stay_search": "🔎",
    "stay_rooms": "🛏️",
    "services": "🛠️",
    "promotions": "🏷️",
    "categories": "🗂️",
    "products": "🛍️",
    "events": "📅",
    "tours": "🏍",  # MT-F1: поездки (тур-продукт)
    "blog": "📰",  # HF-1: лента новостей
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
        # DS-5c (находка адверсариального ревью): страничные extra-пресеты
        # (прайс-виды каталога) валидны и в драфте — паритет с Save-путём.
        if isinstance(lay, dict) and (
            lay.get("preset") in LAYOUT_PRESETS
            or lay.get("preset") in PAGE_EXTRA_PRESETS.get(key, ())
        ):
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
# DS-3b (Fokus): "split" — текст слева на чистом поле, фото справа (hero_image
# или первый слайд heroes; слайдер при split не крутится — ограничение v1).
# DL-13 (C1/C2): "fullscreen" — full-bleed фото ~86 vh с текстом слева снизу и
# «стеклянной» карточкой первой акции (без фото честно падает на accent);
# "bento" — мозаика плиток (акция дня · категория · часы · Newsletter · рейтинг),
# плитки без данных выпадают. Управление — селект «Banner» билдера (был чекбокс
# hero_accent: Save безусловно писал accent/plain и затирал split любой сборки).
HERO_STYLES = ("plain", "accent", "split", "fullscreen", "bento")
HERO_STYLE_LABELS = (
    ("plain", _("Banner: Standard")),
    ("accent", _("Banner: Akzentfläche")),
    ("split", _("Banner: Text + Foto")),
    ("fullscreen", _("Banner: Vollbild-Foto")),
    ("bento", _("Banner: Bento-Kacheln")),
)

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
    # HF-1 (фидбэк владельца 2026-07-31, пп. 7/9/14): акции, страница «О нас» и
    # новости были достижимы только вручную собранным меню — в дефолтной шапке их
    # не было вовсе. Теперь это обычные пункты: акции и новости гейтятся своим
    # модулем, «О нас» доступна всегда (страница витрины есть у каждого бизнеса).
    ("promotions", _("Aktionen"), "storefront-aktionen", "promotions"),
    ("blog", _("News"), "storefront-blog", "blog"),
    ("about", _("About us"), "storefront-about", None),
    # ST-8 (запрос владельца «не разделы на главной, а отдельные страницы»):
    # галерея/отзывы/команда как самостоятельные пункты. Модуля у них нет —
    # гейт по НАЛИЧИЮ контента живёт в menu._page_has_content (пустая страница
    # отдаёт 404, поэтому и пункт не должен вести в никуда).
    ("gallery", _("Galerie"), "storefront-gallery", None),
    ("team", _("Unser Team"), "storefront-team", None),
    ("reviews", _("Bewertungen"), "storefront-reviews", None),
    # 2026-08-06 (аудит демо): страницы, до которых из меню не было пути.
    # 4-й элемент — требуемый модуль: пункт гаснет, если модуль выключен.
    # НЕ добавляем сюда `account`/`wishlist`: у них уже есть иконки в шапке
    # (_header_icons.html 👤/♥) — пункт меню был бы вторым входом в то же место.
    # `combos` дополнительно гейтится наличием наборов (menu._page_has_content):
    # модуль orders включён почти у всех, а пустая страница набора — не пункт меню.
    ("loyalty", _("Treue"), "storefront-loyalty", "loyalty"),
    ("gift", _("Geschenkgutschein"), "storefront-gutschein", "gift"),
    ("combos", _("Kombi-Angebote"), "storefront-combos", "orders"),
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
#   group      → без своей ссылки, только родитель выпадающего подменю;
#   categories → MEN-15: авто-подменю категорий каталога с картинками. target
#                пуст = корневые категории, иначе slug родителя (его подкатегории).
#                Список НЕ ведётся руками: добавил категорию — она в меню.
MENU_NODE_TYPES = (
    "archetype",
    "category",
    "categories",
    "promo_group",
    "page",
    "url",
    "anchor",
    "group",
)
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
    "promotions": ("archetype", "promotions"),  # HF-1
    "blog": ("archetype", "blog"),  # HF-1
    "about": ("page", "about"),  # HF-1
    "gallery": ("page", "gallery"),  # ST-8
    "team": ("page", "team"),  # ST-8
    "reviews": ("page", "reviews"),  # ST-8
    "loyalty": ("page", "loyalty"),
    "gift": ("page", "gift"),
    "combos": ("page", "combos"),
    # `account` в NAV_ITEMS не входит (иконка 👤 в шапке), но маппинг оставляем:
    # владелец может добавить текстовый пункт вручную в конструкторе меню.
    "account": ("page", "account"),
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
    # Фидбэк 2026-08-26: узел «categories» может показывать в подменю ещё и
    # НАБОРЫ меню («меню картинками по наборам и категориям»). Ключ presence-
    # minimal: пишем только при True, иначе legacy-меню раздувалось бы флагом.
    if raw.get("with_combos"):
        node["with_combos"] = True
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
    # DS-1: self-hosted WOFF2 (static/fonts, OFL; @font-face в app.css с
    # unicode-range latin/latin-ext/cyrillic) — грузятся лениво, только когда
    # семейство реально в --font-head. Тело остаётся системным (скорость/CLS).
    "editorial": (_SANS, '"Playfair Display", Georgia, Cambria, serif'),
    "organic": (_SANS, '"Nunito", ui-rounded, system-ui, sans-serif'),
    # DL-1: display-гарнитуры «акционных» Look'ов (latin/latin-ext; кириллических
    # сабсетов у этих семейств нет — заголовки на ru/uk честно падают в фолбэк).
    "condensed": (_SANS, '"Barlow Condensed", "Arial Narrow", Arial, sans-serif'),
    "bricolage": (_SANS, '"Bricolage Grotesque", "Helvetica Neue", Arial, sans-serif'),
    "space": (_SANS, '"Space Grotesk", "Helvetica Neue", Arial, sans-serif'),
    "schibsted": (_SANS, '"Schibsted Grotesk", "Helvetica Neue", Arial, sans-serif'),
    # DL-13 (2026-09-02): шесть новых Look-семейств (self-hosted, OFL).
    "archivo": (_SANS, '"Archivo", "Helvetica Neue", Arial, sans-serif'),
    "archivo_black": (_SANS, '"Archivo Black", Impact, "Arial Black", sans-serif'),
    "quicksand": (_SANS, '"Quicksand", ui-rounded, system-ui, sans-serif'),
    "alfaslab": (_SANS, '"Alfa Slab One", "Rockwell", Georgia, serif'),
    "cormorant": (_SANS, '"Cormorant Garamond", Georgia, Cambria, serif'),
    "manrope": (_SANS, '"Manrope", "Helvetica Neue", Arial, sans-serif'),
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


def clean_testimonials(value) -> list[dict]:
    """GK-6: отзывы-витрина — {name, text} + presence-minimal `stars` (1..5) и
    `photo` (URL-строка, как team.photo). Общий _clean_pairs не расширяем — его
    делят faq/process (golden целы: без extras выход байт-в-байт прежний)."""
    out = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        name, text = _s(item.get("name")), _s(item.get("text"))
        if not name:
            continue
        entry = {"name": name, "text": text}
        try:
            stars = int(str(item.get("stars", "")).strip() or 0)
        except (TypeError, ValueError):
            stars = 0
        if 1 <= stars <= 5:
            entry["stars"] = stars
        photo = _s(item.get("photo"))[:500]
        if photo:
            entry["photo"] = photo
        out.append(entry)
        if len(out) >= _MAX_ITEMS:
            break
    return out


def testimonials_to_text(items) -> str:
    """GK-6: сериализация отзывов в textarea: «Name | Text[ | Sterne][ | Foto-URL]»
    (хвостовые части — только при заполненных; 2-частный round-trip байт-в-байт)."""
    lines = []
    for i in items or []:
        line = f"{i.get('name', '')} | {i.get('text', '')}".rstrip(" |")
        if i.get("stars") or i.get("photo"):
            line += f" | {i.get('stars') or ''}"
        if i.get("photo"):
            line += f" | {i['photo']}"
        lines.append(line)
    return "\n".join(lines)


def text_to_testimonials(text: str) -> list[dict]:
    """GK-6: парс «Name | Text | Sterne | Foto-URL» (валидация в clean_testimonials)."""
    items = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|", 3)]
        items.append(
            {
                "name": parts[0],
                "text": parts[1] if len(parts) > 1 else "",
                "stars": parts[2] if len(parts) > 2 else "",
                "photo": parts[3] if len(parts) > 3 else "",
            }
        )
    return clean_testimonials(items)


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
        entry = {"icon": icon if icon in USP_ICONS else "check", "label": label}
        # GK-5: опциональное описание столпа — presence-minimal (без text старые
        # конфиги байт-в-байт, golden целы; паттерн _text_style).
        text = _s(item.get("text"))[:200]
        if text:
            entry["text"] = text
        out.append(entry)
        if len(out) >= _MAX_USP:
            break
    return out


def stats_to_text(rows) -> str:
    """GK-4: сериализация полосы цифр в textarea редактора: «wert | label» по строке
    (обратный путь — строковая ветка rows в _clean_cblock_data)."""
    return "\n".join(f"{r.get('value', '')} | {r.get('label', '')}" for r in rows or [])


def usp_to_text(items) -> str:
    """Сериализация usp_bar в textarea кабинета: «icon | label[ | text]» по строке
    (GK-5: третья часть — только при непустом описании; 2-частный round-trip
    байт-в-байт — замок test_usp_bar)."""
    lines = []
    for i in items or []:
        line = f"{i.get('icon', 'check')} | {i.get('label', '')}"
        if i.get("text"):
            line += f" | {i['text']}"
        lines.append(line)
    return "\n".join(lines)


def text_to_usp(text: str) -> list[dict]:
    """Парс textarea кабинета: строка «icon | label» → {icon, label} (валидация в clean_usp)."""
    items = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|", 2)]  # GK-5: 3-я часть = описание
        items.append(
            {
                "icon": parts[0],
                "label": parts[1] if len(parts) > 1 else "",
                "text": parts[2] if len(parts) > 2 else "",
            }
        )
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
        "testimonials": text_to_testimonials(g("testimonials_text")),  # GK-6: 4-part
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
    # UC6-8: team/trust дотянуты до 5 видов (Standard + 4) — как faq/подобные.
    "team": ("circles", "list", "compact", "duo"),  # "" = карточки-сетка
    "trust": ("left", "badges", "plain", "cards", "compact"),  # "" = карточка по центру;
    # DS-3b compact: рейтинг + 2 цитаты + marks одной полосой (вместо 4 секций)
    # ST-2: контакт-секция — 4 вида ("" = карточка 2 колонки + карта снизу).
    "contact": ("split", "map_first", "compact"),
    # ST-7b: стили простых секций — ключи-лейблы реюзятся из реестра выше.
    "cta": ("cards", "minimal", "left"),  # "" = акцент-band по центру
    "about": ("plain", "accent", "single"),  # "" = белая карточка
    "usp_bar": ("plain", "cards", "compact", "pillars"),  # "" = карточка-полоса; GK-5
    "reviews": ("quotes", "list", "single"),  # "" = сетка карточек
    # Фидбэк 2026-08-07 («категории картинками + размер из Studio»): форма плитки
    # категории. Ширину даёт раскладка секции (колонки), высоту — этот стиль.
    # "" = 4:3, как рисовала секция главной до правки.
    "categories": ("square", "tall", "wide", "compact"),
    # DS-3a (Fokus): вид вывода товаров — «прайс-лист» (группы по категориям,
    # строка с отточием и ценой; "" = сетка карточек, как было). DS-4b: у
    # категорий compact = строка-плитка «фото 46px + имя + ab-цена + стрелка».
    # DS-5b/5c (фидбэк 2026-08-12): семейство прайс-видов — с фото 40px, компакт
    # (без описаний, плотные строки), двухколоночный (колонки md+, группы целые),
    # «классическая карта» (центр-заголовки групп, описание курсивом под блюдом —
    # как печатные меню кафе/ресторанов).
    "products": (
        "preisliste",
        "preisliste_foto",
        "preisliste_kompakt",
        "preisliste_2sp",
        "preisliste_foto_2sp",  # MEN-14: строки с фото в 2 колонки
        "preisliste_foto_3sp",  # MEN-14: то же в 3 колонки (широкий экран)
        "preisliste_karte",
        "preisliste_buch",  # MEN-16: разворот книги с перелистыванием
    ),
    # DS-4b (Fokus): форма заявки на главной — «band» (акцент-полоса со слим-
    # полями в строку, как в концепт-макете); "" = обычная карточка-форма AF-2.
    "anfrage": ("band",),
    # DL-3 (акционные сборки): spotlight — первая акция крупно + чипы «Endet
    # bald» над гридом; rows — компактные строки «процент-первым» (Marktplatz).
    # "" = прежний грид байт-в-байт.
    "promotions": ("spotlight", "rows", "banner"),  # DL-7d: + широкий баннер-дил
}
#: Класс аспекта плитки категории по стилю секции (см. _category_tile.html).
CATEGORY_TILE_ASPECTS = {
    "": "aspect-[4/3]",
    "square": "aspect-square",
    "tall": "aspect-[3/4]",
    "wide": "aspect-video",
}
# Лейблы вариантов для селекта билдера (DE — как прочий канва-контент).
SECTION_STYLE_LABELS = {
    "list": _("Offene Liste"),
    "twocol": _("Zwei Spalten"),
    "cards": _("Karten"),
    "numbered": _("Nummeriert"),
    "quotes": _("Große Zitate"),
    "accent": _("Akzent-Rand"),
    "single": _("Einzeln zentriert"),
    "timeline": _("Zeitstrahl"),
    "row": _("In einer Reihe"),
    "minimal": _("Minimal"),
    "strip": _("Filmstreifen"),
    "large": _("Große Kacheln"),
    "polaroid": _("Polaroid"),
    "soft": _("Stark gerundet"),
    "circles": _("Runde Fotos"),
    "compact": _("Kompakt"),
    "left": _("Linksbündig"),
    "badges": _("Abzeichen"),
    "plain": _("Ohne Karte"),
    "duo": _("Foto seitlich"),  # UC6-8: team — широкие карточки
    "split": _("Karte seitlich"),  # ST-2: contact
    "map_first": _("Karte zuerst"),
    # Формы плитки категории (2026-08-07).
    "pillars": _("Säulen"),  # GK-5: usp_bar — икона+заголовок+абзац
    "square": _("Quadratisch"),
    "tall": _("Hochformat"),
    "wide": _("Breitbild"),
    "preisliste": _("Preisliste"),  # DS-3a: товары строками с ценой
    "preisliste_foto": _("Preisliste mit Fotos"),  # DS-5b: + мини-фото 40px
    "preisliste_kompakt": _("Preisliste kompakt"),  # DS-5c: без описаний, плотно
    "preisliste_2sp": _("Preisliste zweispaltig"),  # DS-5c: колонки md+
    "preisliste_foto_2sp": _("Fotoliste zweispaltig"),  # MEN-14
    "preisliste_foto_3sp": _("Fotoliste dreispaltig"),  # MEN-14
    "preisliste_karte": _("Speisekarte klassisch"),  # DS-5c: печатная карта
    "preisliste_buch": _("Speisekarte zum Blättern"),  # MEN-16: книга-разворот
    "band": _("Farbband"),  # DS-4b: anfrage — слим-форма на акцент-полосе
    "spotlight": _("Deal der Woche groß"),  # DL-3: акция-фичер + Endet-bald-чипы
    "rows": _("Kompakte Zeilen"),  # DL-3: строки «процент-первым» (Marktplatz)
    "banner": _("Breites Banner"),  # DL-7d: первая акция широкой картой
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
        # MEN-24c: кап СТРОК на группу прайс-вида («Zeilen je Kategorie») —
        # presence-minimal (ключ только при заданном значении, golden целы);
        # limit не переиспользуем: он про число КАРТОЧЕК сеточной ветки.
        rows = _clamp(raw_item.get("rows"), 1, 20, 0)
        if rows:
            entry["rows"] = rows
    # M20U-7: видимость ссылки «View all» (по умолчанию показана).
    if key in SECTION_VIEWALL_KEYS:
        entry["show_all"] = bool(raw_item.get("show_all", True))
    # DS-5: плитка категорий — высота фото (px; отсутствие = аспект по стилю) и
    # состав инфо-строки (ab-цена / счётчик товаров). Presence-minimal.
    if key == "categories":
        img_h = _clamp(raw_item.get("img_h"), 80, 480, 0)
        if img_h:
            entry["img_h"] = img_h
        ti = raw_item.get("tile_info")
        if isinstance(ti, list):
            ti = [t for t in ("price", "count") if t in ti]
            if ti:
                entry["tile_info"] = ti
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


# W5: канонические стадии Kanban-доски (= apps.core.pipeline.STAGES). Дублируем
# кортеж, чтобы siteconfig не импортировал core (слой tenants → core только лениво).
_BOARD_STAGES = ("intake", "in_progress", "done", "terminal")
_BOARD_LABEL_MAX = 40


# FB-4a/FB-4b: статусы, переименовываемые владельцем (кабинет-отображение;
# FSM/письма/публичная витрина НЕ трогаются). order (FB-4a) + service/stay (FB-4b).
_STATUS_LABEL_KINDS = {
    "order": ("new", "confirmed", "ready", "picked_up", "shipped", "cancelled", "returned"),
    "booking": ("pending", "confirmed", "fulfilled", "cancelled", "no_show"),
    "stay": ("pending", "confirmed", "fulfilled", "cancelled", "no_show"),
    # SM-2 (решение владельца 2026-08-10, паритет всем шести направлениям):
    # коды 1:1 с status_registry.BUILTIN — замок в test_ablaeufe_parity.
    "job": ("new", "quoted", "accepted", "done", "invoiced", "declined", "cancelled"),
    "ticket": ("pending", "confirmed", "attended", "cancelled"),
    "reservation": ("pending", "confirmed", "fulfilled", "cancelled", "expired"),
}
_STATUS_LABEL_MAX = 40


def status_label_statuses(kind: str):
    """FB-4a/b: коды статусов kind, переименовываемых владельцем (или None). Публичный
    аксессор для core-вьюхи сохранения (слой tenants → core только лениво)."""
    return _STATUS_LABEL_KINDS.get(kind)


def normalize_status_labels(raw) -> dict:
    """FB-4a/b: {kind: {status: label}} — только известные kind/статусы, label ≤40.
    Пусто → {} (ключ в normalize не появляется — golden-паритет)."""
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for kind, statuses in _STATUS_LABEL_KINDS.items():
        node = raw.get(kind)
        if not isinstance(node, dict):
            continue
        labels = {}
        for st in statuses:
            val = _s(node.get(st))[:_STATUS_LABEL_MAX]
            if val:
                labels[st] = val
        if labels:
            out[kind] = labels
    return out


def normalize_transitions(raw) -> dict:
    """FB-3: правила переходов {kind: {src: [dst,...]}} — какие уже-легальные переходы
    показывать из src. СТРУКТУРНЫЙ whitelist (kind/src/dst — известные статусы); саму
    легальность (dst ∈ allowed_targets) обеспечивает СЛОЙ ЧТЕНИЯ (transactions
    пересекает с FSM) + apply() — тут core не импортируем (слой tenants). Пустой список
    у src ОСМЫСЛЕН (скрыть не-danger переходы) — материализуется. Пусто → {} (golden)."""
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for kind, statuses in _STATUS_LABEL_KINDS.items():
        node = raw.get(kind)
        if not isinstance(node, dict):
            continue
        sset = set(statuses)
        rules = {}
        for src, dsts in node.items():
            if src not in sset or not isinstance(dsts, (list, tuple)):
                continue
            rules[src] = [d for d in dsts if d in sset]
        if rules:
            out[kind] = rules
    return out


def normalize_status_defs(raw) -> dict:
    """FB-3 Вариант B: пользовательские определения статусов {kind: [def,...]}.

    def = {code, label, role, stage, blocks_capacity, counts_in_reports, revenue_recognized}.
    Whitelist: kind ∈ _STATUS_LABEL_KINDS (SM-2b/SM-3: все шесть направлений); code — slug
    [a-z0-9_] ≤20 (SM-3: status у всех шести моделей — varchar(20); длиннее ронял бы
    apply() DataError'ом), НЕ совпадает со встроенным статусом и не дублируется в kind;
    role ∈ ROLES; stage ∈ STAGES; флаги — bool.
    Presence-minimal → {} (golden). Реестр core импортируем лениво (слой tenants → core)."""
    raw = raw if isinstance(raw, dict) else {}
    from apps.core.status_registry import BUILTIN, ROLES, STAGES

    out = {}
    for kind in _STATUS_LABEL_KINDS:
        node = raw.get(kind)
        if not isinstance(node, list):
            continue
        builtin_codes = set(BUILTIN.get(kind, {}))
        seen, defs = set(), []
        for d in node:
            if not isinstance(d, dict):
                continue
            # SM-3: кламп 20 = max_length поля status всех шести моделей
            code = re.sub(r"[^a-z0-9_]+", "_", _s(d.get("code")).strip().lower()).strip("_")[:20]
            role, stage = _s(d.get("role")), _s(d.get("stage"))
            if not code or code in builtin_codes or code in seen:
                continue
            if role not in ROLES or stage not in STAGES:
                continue
            seen.add(code)
            defs.append(
                {
                    "code": code,
                    "label": _s(d.get("label"))[:40] or code,
                    "role": role,
                    "stage": stage,
                    "blocks_capacity": bool(d.get("blocks_capacity")),
                    "counts_in_reports": bool(d.get("counts_in_reports")),
                    "revenue_recognized": bool(d.get("revenue_recognized")),
                }
            )
        if defs:
            out[kind] = defs
    return out


def normalize_status_edges(raw) -> dict:
    """FB-3 Вариант B: кастом-переходы {kind: [{src, dst}]} (граф тенанта поверх FSM).

    Структурный whitelist: kind ∈ _STATUS_LABEL_KINDS (все шесть); src/dst — непустые слаги, src≠dst;
    дубли отброшены. Семантику (оба статуса известны + ≥1 кастом-эндпоинт, чтобы не
    добавить built-in↔built-in shortcut в обход FSM) проверяет СЛОЙ ЧТЕНИЯ
    (status_registry.custom_edges) + apply(). Presence-minimal → {} (golden)."""
    raw = raw if isinstance(raw, dict) else {}

    def _code(v):
        # SM-3: кламп согласован с normalize_status_defs (рёбра матчатся с дефами)
        return re.sub(r"[^a-z0-9_]+", "_", _s(v).strip().lower()).strip("_")[:20]

    out = {}
    for kind in _STATUS_LABEL_KINDS:
        node = raw.get(kind)
        if not isinstance(node, list):
            continue
        seen, edges = set(), []
        for e in node:
            if not isinstance(e, dict):
                continue
            src, dst = _code(e.get("src")), _code(e.get("dst"))
            if not src or not dst or src == dst or (src, dst) in seen:
                continue
            seen.add((src, dst))
            edges.append({"src": src, "dst": dst})
        if edges:
            out[kind] = edges
    return out


def normalize_board(raw) -> dict:
    """W5: настройки доски (labels/order/hidden) — только известные стадии.

    labels: {stage: строка ≤40}; order: перестановка стадий (дубли/чужое отброшены);
    hidden: скрытые стадии (в порядке STAGES). Каждый под-ключ материализуется только
    при непустом → пустой board → {} (ключ `board` в normalize не появляется, golden-
    паритет). Правила переходов (V4) тут НЕ трогаем."""
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    labels_in = raw.get("labels")
    if isinstance(labels_in, dict):
        labels = {}
        for stage in _BOARD_STAGES:
            val = _s(labels_in.get(stage))[:_BOARD_LABEL_MAX]
            if val:
                labels[stage] = val
        if labels:
            out["labels"] = labels
    order_in = raw.get("order")
    if isinstance(order_in, list):
        seen, order = set(), []
        for stage in order_in:
            if stage in _BOARD_STAGES and stage not in seen:
                order.append(stage)
                seen.add(stage)
        if order:
            out["order"] = order
    hidden_in = raw.get("hidden")
    if isinstance(hidden_in, list):
        hidden = [stage for stage in _BOARD_STAGES if stage in set(hidden_in)]
        if hidden:
            out["hidden"] = hidden
    return out


def normalize_sales_views(raw) -> dict:
    """Единая страница Verkäufe (2026-08-03): выбранный вид на kind.

    {kind: view} только по известным парам из реестра `sales_page.KIND_VIEWS`;
    ключ материализуется ТОЛЬКО при непустом (golden-паритет). НЕ путать с
    удалённым легаси `orders_view` — тот дропается normalize'ом и остаётся
    дропаемым (иная семантика: одна страница на весь хаб)."""
    from apps.core.sales_page import KIND_VIEWS

    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for kind, views in KIND_VIEWS.items():
        if raw.get(kind) in views:
            out[kind] = raw[kind]
    return out


# FD-1: Finder «вопросы → 3 предложения» (план fd1-finder-plan-2026-07-18).
_MAX_FINDER_QUESTIONS = 6
_MAX_FINDER_CHIPS = 8
_FINDER_MATCH_SLUGS = ("collection", "category")


def _clean_finder_match(raw) -> dict:
    """match-спека чипа: только известные ключи с валидными значениями.
    words — скоринг по имени/описанию; collection/category — slug (+баллы);
    price_min/max — жёсткий фильтр в EUR (> 0)."""
    d = raw if isinstance(raw, dict) else {}
    out = {}
    words_in = d.get("words") if isinstance(d.get("words"), list) else []
    words = [_s(w)[:40] for w in words_in if isinstance(w, str) and w.strip()]
    if words:
        out["words"] = words[:10]
    for key in _FINDER_MATCH_SLUGS:
        if _s(d.get(key)):
            out[key] = _s(d.get(key))[:80]
    for key in ("price_min", "price_max"):
        try:
            val = float(d.get(key))
        except (TypeError, ValueError):
            continue
        if val > 0:
            out[key] = round(val, 2)
    return out


# DL-13 (C3): режим страницы /aktionen/ — "" (по группам владельца, как было)
# или "time" (Prospekt по времени: Endet heute · Endet diese Woche · Länger
# gültig · Dauerhaft). Presence-minimal: ключ пишется ТОЛЬКО при "time".
PROMO_GROUPINGS = ("time",)


def normalize_promo_grouping(raw) -> str:
    return raw if raw in PROMO_GROUPINGS else ""


# DL-16.2 (A3): раскладка секций-групп на /aktionen/ — "" сетка (как было) или
# "slider": каждая группа — горизонтальная лента со стрелками (S1) + «Alle anzeigen».
PROMO_LAYOUTS = ("slider",)


def normalize_promo_layout(raw) -> str:
    return raw if raw in PROMO_LAYOUTS else ""


def normalize_presence(raw) -> dict:
    """LS-2 «Jetzt erreichbar»: {"mode": "on"|"off"}; auto — ДЕФОЛТ и в конфиг
    не пишется (presence-minimal, golden-паритет). Мусор → auto (пусто)."""
    raw = raw if isinstance(raw, dict) else {}
    mode = raw.get("mode")
    return {"mode": mode} if mode in ("on", "off") else {}


_ANFRAGE_FIELDS = ("date", "guests", "event_type")  # канонический порядок
_MAX_EVENT_TYPES = 12


def normalize_anfrage(raw) -> dict:
    """AF-1: событийные поля формы заявки /anfrage/ (Catering/Partyservice).

    {"fields": ["date","guests","event_type"], "event_types": ["Hochzeit", …]}.
    Ключ `anfrage` материализуется ТОЛЬКО при непустом fields (presence-minimal,
    golden-паритет; отсутствие = форма прежняя). fields — подмножество
    _ANFRAGE_FIELDS в каноническом порядке; event_types — строки владельца
    (кап 12 × 60), сохраняются и без поля event_type (черновик наполнения)."""
    raw = raw if isinstance(raw, dict) else {}
    chosen = raw.get("fields")
    chosen = {f for f in (chosen if isinstance(chosen, list) else []) if isinstance(f, str)}
    fields = [f for f in _ANFRAGE_FIELDS if f in chosen]
    if not fields:
        return {}
    out = {"fields": fields}
    types = []
    for item in raw.get("event_types") if isinstance(raw.get("event_types"), list) else []:
        if isinstance(item, str) and item.strip():
            types.append(item.strip()[:60])
        if len(types) >= _MAX_EVENT_TYPES:
            break
    if types:
        out["event_types"] = types
    return out


CARD_AMENITIES_MAX = 6  # больше пиктограмм на карточке — уже шум, не информация


def normalize_card_amenities(raw) -> list:
    """HF-2: ключи удобств, показываемых пиктограммами на карточке номера.

    Пустой список = дефолт (первые несколько удобств самого номера), поэтому в
    конфиг ключ не пишется. Валидация по реестру `stays.AMENITIES` — мусор и
    несуществующие ключи отбрасываются, порядок реестра, дубли схлопываются."""
    from apps.stays.models import AMENITIES

    known = [key for key, _label, _icon in AMENITIES]
    chosen = {k for k in (raw if isinstance(raw, list) else []) if isinstance(k, str)}
    return [k for k in known if k in chosen][:CARD_AMENITIES_MAX]


def normalize_finder(raw) -> dict:
    """FD-1: конфиг Finder — {"enabled": bool, "questions": [{key,label,chips}]}.

    Ключ `finder` в normalize материализуется ТОЛЬКО при непустом (golden-паритет,
    паттерн board/seo). enabled — только при True. Пустые questions → страница
    берёт пресет архетипа (apps.core.finder); кастом-дерево пишет кабинет (FD-3)."""
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    if raw.get("enabled"):
        out["enabled"] = True
    questions_in = raw.get("questions") if isinstance(raw.get("questions"), list) else []
    questions = []
    for q in questions_in:
        if not isinstance(q, dict):
            continue
        key, label = _s(q.get("key"))[:40], _s(q.get("label"))[:120]
        chips_in = q.get("chips") if isinstance(q.get("chips"), list) else []
        chips = []
        for c in chips_in:
            if not isinstance(c, dict):
                continue
            ckey, clabel = _s(c.get("key"))[:40], _s(c.get("label"))[:80]
            if ckey and clabel:
                chips.append(
                    {"key": ckey, "label": clabel, "match": _clean_finder_match(c.get("match"))}
                )
            if len(chips) >= _MAX_FINDER_CHIPS:
                break
        if key and label and chips:
            questions.append({"key": key, "label": label, "chips": chips})
        if len(questions) >= _MAX_FINDER_QUESTIONS:
            break
    if questions:
        out["questions"] = questions
    return out


def normalize_seo(raw) -> dict:
    """SEO-2: per-тип шаблоны мета (title/description) для движка seo_meta.

    Только известные page_types (home/listing/detail/category); строки чистятся и
    обрезаются (шаблон, не рендер — рендер клампит resolve). Пустой тип/поле —
    пропуск. SEO-3b: `allow_ai` материализуется ТОЛЬКО когда явно False (дефолт
    True = разрешено; golden-паритет). Пусто целиком → {} (ключ `seo` НЕ
    материализуется). Так настройки переживают normalize (иначе любое сохранение
    билдера их бы стёрло — неизвестные секции отбрасываются)."""
    from apps.core import seo_meta

    if not isinstance(raw, dict):
        return {}
    raw_t = raw.get("templates") if isinstance(raw.get("templates"), dict) else {}
    templates = {}
    for pt in seo_meta.PAGE_TYPES:
        entry_in = raw_t.get(pt) if isinstance(raw_t.get(pt), dict) else {}
        entry = {}
        title = _s(entry_in.get("title"))[:200]
        desc = _s(entry_in.get("description"))[:300]
        if title:
            entry["title"] = title
        if desc:
            entry["description"] = desc
        if entry:
            templates[pt] = entry
    result = {}
    if templates:
        result["templates"] = templates
    if raw.get("allow_ai") is False:  # дефолт True → ключ не материализуем
        result["allow_ai"] = False
    return result


def normalize(config) -> dict:
    """Привести произвольный site_config к валидной схеме.

    Неизвестные секции отбрасываются, отсутствующие дописываются в конец со
    своим дефолтом — старые конфиги переживают добавление новых секций.

    T-1: нормализация ЛОКАЛЕ-СТАБИЛЬНА — lazy-подписи (метки меню и т.п.)
    материализуются в ХРАНИМЫЙ конфиг всегда как msgid (перевод выключен на
    время прогона), иначе содержимое site_config зависело бы от языка
    запроса, а golden-эталоны — от активного каталога переводов.
    """
    from django.utils import translation

    with translation.override(None):
        return _normalize_impl(config)


def _normalize_impl(config) -> dict:
    config = config if isinstance(config, dict) else {}

    normalized = {"sections": normalize_sections(config.get("sections", []))}
    # SEO-2: per-тип мета-шаблоны (переживают нормализацию; ключ только при непустом).
    seo = normalize_seo(config.get("seo"))
    if seo:
        normalized["seo"] = seo
    # SM-1 (2026-08-10): ключ ui_mode (режим Простой/Эксперт) снесён вместе с
    # механизмом — normalize его ДРОПАЕТ, как classic_ui (W-CL).
    # W-CL (2026-08-05, решение владельца Р-1): режим «Klassische Ansicht» снесён —
    # ключ classic_ui дропается нормализацией (паттерн retired-ключа orders_view ниже).
    # ST-1: тёмный Look витрины — ключ ТОЛЬКО при "dark" (presence-minimal,
    # golden-паритет; светлая = отсутствие ключа). Посетительский тумблер
    # sf-theme (localStorage) остаётся сильнее — это лишь ДЕФОЛТ сайта.
    if config.get("theme") == "dark":
        normalized["theme"] = "dark"
    # W5: настройки Kanban-доски (переименование/порядок/скрытие колонок); ключ
    # ТОЛЬКО при непустом (golden-паритет старых конфигов).
    board = normalize_board(config.get("board"))
    if board:
        normalized["board"] = board
    # ST-5b: ключ orders_view УДАЛЁН (фидбэк 2026-07-28 — маппинг фиксированный,
    # архетип-дефолт; нормализация дропает легаси-значения самоочисткой).
    # Verkäufe-страница (2026-08-03): выбранный вид на kind; ключ ТОЛЬКО при
    # непустом (golden-паритет).
    sv = normalize_sales_views(config.get("sales_views"))
    if sv:
        normalized["sales_views"] = sv
    # SR-1: вид обзора Sortiment; единственное недефолтное значение — "liste"
    # (kacheln = дефолт → ключ не материализуется, golden-паритет).
    if config.get("sortiment_view") == "liste":
        normalized["sortiment_view"] = "liste"
    # DL-8a: выбранный дизайн ({look, bundle}) — пишут apply_look/apply_bundle;
    # питает бейдж «Aktiv» страницы Design и data-sf-look витрины. Валидация
    # по реестрам — ленивый импорт (siteconfig не импортирует sitetemplates
    # на уровне модуля: тот сам импортирует siteconfig). Presence-minimal.
    dsg = config.get("design")
    if isinstance(dsg, dict) and (dsg.get("look") or dsg.get("bundle")):
        from apps.tenants import sitetemplates as _st

        clean = {}
        if _st.get_look_family(str(dsg.get("look") or "")) is not None:
            clean["look"] = str(dsg["look"])
        if _st.get_bundle(str(dsg.get("bundle") or "")) is not None:
            clean["bundle"] = str(dsg["bundle"])
        if clean:
            normalized["design"] = clean
    # FD-1: Finder («вопросы → 3 предложения»); ключ ТОЛЬКО при непустом.
    fnd = normalize_finder(config.get("finder"))
    if fnd:
        normalized["finder"] = fnd
    # LS-2: присутствие «Jetzt erreichbar»; ключ ТОЛЬКО при override (auto = нет ключа).
    presence = normalize_presence(config.get("presence"))
    if presence:
        normalized["presence"] = presence
    # DL-13 (C3): страница акций «по времени»; ключ ТОЛЬКО при "time" (golden целы).
    promo_grouping = normalize_promo_grouping(config.get("promo_grouping"))
    if promo_grouping:
        normalized["promo_grouping"] = promo_grouping
    promo_layout = normalize_promo_layout(config.get("promo_layout"))
    if promo_layout:
        normalized["promo_layout"] = promo_layout
    # AF-1: событийные поля формы /anfrage/; ключ ТОЛЬКО при непустом (golden-паритет).
    anfrage = normalize_anfrage(config.get("anfrage"))
    if anfrage:
        normalized["anfrage"] = anfrage
    # HF-2: какие удобства показывать на карточке номера; ключ ТОЛЬКО при выборе
    # владельца (пусто = дефолт «первые несколько удобств номера») — golden-паритет.
    ca = normalize_card_amenities(config.get("stay_card_amenities"))
    if ca:
        normalized["stay_card_amenities"] = ca
    # FB-4a: свои имена статусов заказа; ключ ТОЛЬКО при непустом (golden-паритет).
    sl = normalize_status_labels(config.get("status_labels"))
    if sl:
        normalized["status_labels"] = sl
    # FB-3: правила переходов статусов; ключ ТОЛЬКО при непустом (golden-паритет).
    tr = normalize_transitions(config.get("transitions"))
    if tr:
        normalized["transitions"] = tr
    # FB-3 Вариант B: пользовательские определения статусов; ключ ТОЛЬКО при непустом.
    sd = normalize_status_defs(config.get("status_defs"))
    if sd:
        normalized["status_defs"] = sd
    # FB-3 Вариант B: кастом-переходы; ключ ТОЛЬКО при непустом (golden-паритет).
    se = normalize_status_edges(config.get("status_edges"))
    if se:
        normalized["status_edges"] = se
    # UC6-7: C-блоки не-home страниц; ключ ТОЛЬКО при непустом (golden-паритет).
    pb = normalize_page_blocks(config.get("page_blocks"))
    if pb:
        normalized["page_blocks"] = pb
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
    # DS-3b (Fokus): CTA primary-действия в шапке (+акцент пункта таб-бара).
    # Presence-minimal: ключ только при включении — golden целы.
    if nav_in.get("cta"):
        normalized["nav"]["cta"] = True
    # KAT-1: тумблер category_landings УМЕР (прецедент classic_ui) — категория
    # теперь ВСЕГДА страница /sortiment/<slug>/, а шапку решает Category.page_style;
    # normalize ключ ДРОПАЕТ (не переносим в normalized).
    # DS-7b: цены в меню (прайс-виды/плитки). Дефолт ПОКАЗЫВАТЬ; ключ
    # материализуется только при False. PAngV-гейт применяет вьюха/форма
    # (скрытие только для browse-only меню) — normalize хранит намерение.
    if config.get("menu_show_prices") is False:
        normalized["menu_show_prices"] = False
    # MEN-24a: маркировка (диеты/аллергены) в витринном прайс-листе —
    # presence-minimal, дефолт ВЫКЛ (иконки не «зарастают» без спроса).
    if config.get("menu_labels"):
        normalized["menu_labels"] = True
    # S7: многоуровневое меню (top + bottom). Дерево узлов с привязкой к
    # архетипам/категориям/страницам/URL/якорям; глубина 2. Легаси без `menus`
    # → top выводим из `nav` (та же плоская шапка, без регрессии), bottom —
    # выключен (используется авто таб-бар T2b).
    normalized["menus"] = _normalize_menus(config.get("menus"), normalized["nav"])
    # Контент-секции (M20 ⑤a): FAQ, отзывы, CTA. Все опциональны; пустое — пропуск.
    normalized["faq"] = _clean_pairs(config.get("faq"), "q", "a")
    # GK-6: свой клинер (stars/photo presence-minimal; пары — байт-в-байт прежние).
    normalized["testimonials"] = clean_testimonials(config.get("testimonials"))
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
                # Фидбэк 2026-07-28: кнопка на слайдере обложки (пусто = дефолтный
                # якорь «Discover» вниз к содержимому).
                "button_label": _s(ov.get("button_label")),
                "button_url": _s(ov.get("button_url")),
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
    # 2026-07-30: явный «главный товар» (hero-CTA/buybar) НЕЗАВИСИМО от корня витрины.
    # С активным jobs эвристика _PRIORITY делала primary=jobs (Bäckerei/Metzgerei c
    # Partyservice: hero-CTA «Angebot anfragen» вместо Sortiment). Presence-minimal:
    # пусто/не-архетип → ключа нет (легаси-резолюция по приоритету, golden целы).
    _pm = _s(config.get("primary_module"))
    if _pm in {"events", "stays", "booking", "jobs", "catalog", "promotions"}:
        normalized["primary_module"] = _pm
    # M3 Boutique: Click&Reserve «In der Anprobe» — presence-minimal (ключ только
    # при True; выключено = ключа нет, golden целы).
    if config.get("anprobe"):
        normalized["anprobe"] = True
    # MEN-9 (кейтеринг, решение владельца «продавать сразу не нужно, но через
    # корзину прогонять как заказ на просчёт»): корзина и чекаут работают, но
    # заказ — НЕОБЯЗЫВАЮЩИЙ запрос: без оплаты, без §312j-кнопки, письма
    # говорят «Anfrage». Presence-minimal (ключ только при True — golden целы).
    if config.get("quote_cart"):
        normalized["quote_cart"] = True
    # M20U-7 (per-page): раскладка сетки страницы каталога /sortiment/. Дефолт cols3
    # воспроизводит прежнюю захардкоженную сетку (grid-cols-2 lg:grid-cols-3).
    normalized["catalog_layout"] = normalize_layout(
        config.get("catalog_layout"),
        {"preset": "cols3"},
        extra_presets=PAGE_EXTRA_PRESETS["catalog_layout"],
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
            config["service_index_layout"],
            {"preset": "cols2"},
            # MEN-18: прайс-виды услуг (список/с фото/2 колонки) — как у каталога.
            extra_presets=PAGE_EXTRA_PRESETS["service_index_layout"],
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
    # W7a (аудит 2026-08-05): операционные узлы, которые пишут ДРУГИЕ экраны
    # кабинета мимо конструктора — уведомления/Telegram владельца
    # (apps.notifications.prefs, apps.telegram.notify), настройки склада
    # (apps.inventory) и presence-minimal read-hook'и витрины. Без passthrough
    # сохранение любого normalize-экрана (билдер/SEO/Finder/мастер) молча
    # стирало их (класс W0/W6). Ключи presence-minimal: отсутствуют — не
    # материализуем (golden целы).
    if isinstance(config.get("notify"), dict):
        normalized["notify"] = config["notify"]
    if isinstance(config.get("low_stock_threshold"), int) and not isinstance(
        config.get("low_stock_threshold"), bool
    ):
        normalized["low_stock_threshold"] = config["low_stock_threshold"]
    if isinstance(config.get("lots_enabled"), bool):
        normalized["lots_enabled"] = config["lots_enabled"]
    if isinstance(config.get("wishlist"), bool):
        normalized["wishlist"] = config["wishlist"]
    if config.get("primary_service_cta") in ("booking", "request"):
        normalized["primary_service_cta"] = config["primary_service_cta"]
    # i18n-оверлеи переводов (двуязычная витрина) — переживают нормализацию;
    # `localize()` накладывает их перед рендером. Базовый рендер (DE) не трогаем.
    i18n = _clean_i18n(config.get("i18n"))
    if i18n:
        normalized["i18n"] = i18n
    return normalized


def enabled_sections(tenant) -> list[str]:
    """Упорядоченные ключи включённых секций главной для витрины."""
    return [s["key"] for s in normalize(tenant.site_config)["sections"] if s["enabled"]]
