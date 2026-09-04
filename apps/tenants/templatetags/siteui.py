"""Шаблонные фильтры витрины (site_config UI)."""

from django import template
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe
from django.utils.translation import get_language
from django.utils.translation import gettext as _

from apps.core import card_forms
from apps.tenants import siteconfig, video

register = template.Library()

# D.1 (анти-Битрикс Phase 2): реестр секций главной — key → партиал. Заменяет
# хардкод if/elif в storefront/home.html (single source of truth, разблокиратор
# для C-блоков и on-canvas «+»). Якоря секций (для меню типа anchor) — отдельно.
BLOCK_TEMPLATES = {
    "hero": "storefront/sections/_hero.html",
    "usp_bar": "storefront/sections/_usp_bar.html",
    "finder": "storefront/sections/_finder.html",  # FD-2: CTA «вопросы → 3 предложения»
    "stay_search": "storefront/sections/_stay_search.html",
    "stay_rooms": "storefront/sections/_stay_rooms.html",
    "services": "storefront/sections/_services.html",
    "promotions": "storefront/sections/_promotions.html",
    "categories": "storefront/sections/_categories.html",
    "products": "storefront/sections/_products.html",
    "events": "storefront/sections/_events.html",
    "tours": "storefront/sections/_tours.html",  # MT-F1: поездки на главной
    "blog": "storefront/sections/_blog.html",  # HF-1: лента новостей
    "archetypes": "storefront/sections/_archetypes.html",
    "about": "storefront/sections/_about.html",
    "process": "storefront/sections/_process.html",
    "team": "storefront/sections/_team.html",
    "cta": "storefront/sections/_cta.html",
    "testimonials": "storefront/sections/_testimonials.html",
    "trust": "storefront/sections/_trust.html",
    "reviews": "storefront/sections/_reviews.html",
    "faq": "storefront/sections/_faq.html",
    "gallery": "storefront/sections/_gallery.html",
    "before_after": "storefront/sections/_before_after.html",
    "contact": "storefront/sections/_contact.html",
    # AF-2b: базы ТОЛЬКО для ref-блоков страниц (в SECTIONS главной их нет) —
    # anfrage_ref → форма заявки (гейт jobs), message_ref → контакт-форма (inbox).
    "anfrage": "storefront/sections/_anfrage.html",
    "message": "storefront/sections/_message.html",
}
# Якорь-id обёртки секции (scroll-mt-24) — пункты меню типа «anchor» ведут на #id.
_BLOCK_ANCHOR_ID = {
    "finder": "finder",
    "stay_search": "buchen",
    "stay_rooms": "zimmer",
    "services": "leistungen",
    "about": "ueber-uns",
    "testimonials": "stimmen",
    "reviews": "bewertungen",
    "faq": "faq",
    "gallery": "galerie",
    "blog": "neuigkeiten",  # HF-1: якорь для пункта меню типа anchor
    "tours": "reisen",  # MT-F1: пункт меню «Reisen» может вести на секцию главной
    "before_after": "referenzen",
    "contact": "kontakt",
}
# Секции с обёрткой scroll-mt-24 без id (плавная прокрутка, без якоря меню).
_BLOCK_WRAP_NOID = {"archetypes"}

# D.2: C-блоки (повторяемые «кубики») — key → партиал. Данные берутся из самого
# блока (`block.data`), а не из контекста вьюхи (в отличие от фикс-секций).
CBLOCK_TEMPLATES = {
    "text": "storefront/sections/_block_text.html",
    "image": "storefront/sections/_block_image.html",
    "image_text": "storefront/sections/_block_image_text.html",
    "button": "storefront/sections/_block_button.html",
    "spacer": "storefront/sections/_block_spacer.html",
    "promo": "storefront/sections/_block_promo.html",  # UE1: LIVE-промо по promo_pk
    "stats": "storefront/sections/_block_stats.html",  # GK-4: полоса цифр
    "newsletter": "storefront/sections/_block_newsletter.html",  # GK-8: подписка (DOI)
}


@register.filter(name="stars")
def stars_filter(n):
    """GK-6: 1..5 → «★★★★☆»; мусор/вне диапазона → '' (конфиг не раздуваем —
    строка считается на рендере, golden целы)."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return ""
    return "★" * n + "☆" * (5 - n) if 1 <= n <= 5 else ""


@register.filter(name="safe_href")
def safe_href(url):
    """Разрешить только http(s)/mailto/tel/относительные ссылки; иначе '#'.

    C-блоки (напр. CTA-кнопка) хранят owner-задаваемый url; без проверки схемы
    владелец мог задать `javascript:...` → XSS на своей витрине при клике. Также
    режем protocol-relative `//host` (навигация на чужой сайт)."""
    s = (url or "").strip()
    if s.startswith("//"):
        return "#"
    low = s.lower()
    if low.startswith(("http://", "https://", "mailto:", "tel:")) or s.startswith(("/", "#")):
        return s
    return "#"


@register.simple_tag
def default_date(days=1):
    """E5b «умные дефолты»: дата = сегодня + days (ISO YYYY-MM-DD) для предзаполнения
    date-search (Anreise = завтра, Abreise = +2 ночи) — «просто нажми Suchen».
    Поиск НЕ запускается: это лишь значение инпута, посетитель меняет свободно."""
    from datetime import timedelta

    from django.utils import timezone

    return (timezone.localdate() + timedelta(days=int(days))).isoformat()


@register.simple_tag
def deal_of_day():
    """Батч A (гастро-сплит, концепт 2026-07-27): «Angebot des Tages» для плитки
    hero — первая активная акция: recurrence=daily первой (это и есть «акция
    дня»), затем ближайшая по ends_at (NULL — в конец), затем свежайшая. None —
    плитки нет (fail-safe, hero остаётся 2-плиточным)."""
    from django.db.models import Case, F, IntegerField, Value, When

    from apps.promotions.models import Promotion

    return (
        Promotion.objects.filter(status="active")
        .annotate(
            daily_first=Case(
                When(recurrence=Promotion.DAILY, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            ),
        )
        .order_by("daily_first", F("ends_at").asc(nulls_last=True), "-created_at")
        .first()
    )


@register.inclusion_tag("storefront/sections/_hero_tiles.html", takes_context=True)
def hero_tiles(context, widget):
    """Плитки-направления первого экрана из реестра `core.hero_tiles` (архетипы
    без кастомной ветки в `_hero_widget.html`). Неизвестный widget / нет
    активных модулей → пустой список → партиал ничего не рендерит."""
    from apps.core import hero_tiles as registry

    tenant = getattr(context.get("request"), "tenant", None) or context.get("tenant")
    if tenant is None:
        return {"tiles": []}
    deal = deal_of_day() if registry.needs_deal(widget) else None
    return {"tiles": registry.tiles_for(widget, tenant, deal=deal)}


@register.inclusion_tag("storefront/sections/_hero_deal_card.html", takes_context=True)
def hero_deal_card(context):
    """DL-13 C1: «стеклянная» карточка первой активной акции в Vollbild-hero.
    Гейт: модуль promotions активен И есть живая акция — иначе пусто (партиал
    самогейтится, колонка грида схлопывается)."""
    from apps.core import modules

    tenant = getattr(context.get("request"), "tenant", None) or context.get("tenant")
    if tenant is None or not modules.is_module_active(tenant, "promotions"):
        return {"deal": None}
    return {"deal": deal_of_day()}


@register.inclusion_tag("storefront/sections/_hero_bento.html", takes_context=True)
def hero_bento(context):
    """DL-13 C2: плитки Bento-hero. Бренд-плитка (заголовок/текст/CTA) — всегда;
    остальные — по данным: акция дня (модуль promotions), первая категория с
    фото (модуль catalog), часы (структурные часы заданы), Newsletter (модуль
    promotions), рейтинг (внутренний или Google). Каждая выборка fail-safe —
    первый экран не должен падать из-за одной плитки."""
    from apps.core import modules

    request = context.get("request")
    tenant = getattr(request, "tenant", None) or context.get("tenant")
    out = {
        "request": request,  # inclusion_tag рендерит СВОЙ контекст — request не наследуется
        "site": context.get("site") or {},
        "primary_item": context.get("primary_item"),
        "deal": None,
        "category": None,
        "hours": None,
        "newsletter": False,
        "rating": None,
    }
    if tenant is None:
        return out
    if modules.is_module_active(tenant, "promotions"):
        try:
            out["deal"] = deal_of_day()
        except Exception:  # pragma: no cover — плитка не роняет главную
            out["deal"] = None
        out["newsletter"] = True
    if modules.is_module_active(tenant, "catalog"):
        try:
            from apps.catalog.models import Category

            out["category"] = next(
                (
                    c
                    for c in Category.objects.filter(is_active=True, parent__isnull=True).order_by(
                        "sort_order", "slug"
                    )[:12]
                    if c.image_url
                ),
                None,
            )
        except Exception:  # pragma: no cover
            out["category"] = None
    try:
        status = tenant.open_status()  # метод, не property (в шаблоне зовётся без скобок)
        if status is not None:
            out["hours"] = {"status": status, "today": tenant.todays_hours()}
    except Exception:  # pragma: no cover
        out["hours"] = None
    try:
        from apps.core.templatetags.seo import business_rating

        out["rating"] = business_rating()
    except Exception:  # pragma: no cover
        out["rating"] = None
    out["google_rating"] = getattr(tenant, "google_rating", None)
    out["google_rating_count"] = getattr(tenant, "google_rating_count", 0)
    # Стенд DL-13.4: 6 плиток в сетке 3×2 с бренд-плиткой на 2 ряда — шестая
    # (рейтинг) уезжала одна в третий ряд. Раскладка считается по числу
    # ДАТА-плиток: рейтинг живёт в бренд-плитке подписью, 4 плитки = 2×2 рядом
    # с брендом (2 ряда), 3 → последняя на 2 колонки, ≤2 → бренд в один ряд.
    n = sum(1 for k in ("deal", "category", "hours", "newsletter") if out.get(k))
    out["brand_rows"] = 2 if n >= 3 else 1
    out["brand_cols"] = 3 if n == 0 else (2 if n == 1 else 1)
    out["last_wide"] = n == 3
    return out


@register.inclusion_tag("storefront/_funnel_steps.html")
def funnel_steps(kind, current):
    """E5 «задача-первым»: прогресс-степпер воронки (Schritt N/M) — ведём клиента
    последовательно. kind = service|stay|event|order; current = 1-based шаг.
    Вне диапазона → пусто (партиал ничего не рендерит)."""
    from apps.core import funnels

    steps = funnels.funnel_steps(kind, current)
    return {"steps": steps, "total": len(steps), "current": current}


@register.simple_tag
def live_promo(pk):
    """UE1 (D2=LIVE): активная промо по pk или None — fail-safe к мусору/уда-
    лённой/неактивной (блок тогда пуст; цена/остаток всегда актуальны из БД)."""
    if not pk:
        return None
    from django.core.exceptions import ValidationError

    from apps.promotions.models import Promotion

    try:
        return Promotion.objects.filter(pk=pk, status="active").first()
    except (ValidationError, ValueError):
        return None


@register.simple_tag(takes_context=True)
def page_blocks(context, page_key):
    """UC6-7: C-блоки страницы (хост site_config.page_blocks[page_key]) —
    рендер как на главной (ряды узких блоков + _section_block: клик→лента,
    📷, инлайн работают). При ?preview=1 — черновик сессии (live-preview)."""
    request = context.get("request")
    tenant = getattr(request, "tenant", None)
    if request is None or tenant is None:
        return ""
    raw = tenant.site_config
    try:
        if request.GET.get("preview") == "1":
            draft = request.session.get("site_preview_draft")
            if isinstance(draft, dict):
                raw = draft
    except Exception:  # noqa: BLE001 — превью не должно ронять витрину
        pass
    # Аудит переводов 2026-08-13: блоки берём из ЛОКАЛИЗОВАННОГО конфига — раньше
    # тег читал их из голого normalize, и текст C-блоков страниц («Über uns»,
    # корзина) оставался немецким на любой локали даже при готовом оверлее.
    site = siteconfig.localize(siteconfig.normalize(raw), get_language())
    blocks = [
        b for b in (site.get("page_blocks") or {}).get(page_key, []) if b.get("enabled", True)
    ]
    is_preview = bool(context.get("is_preview"))
    if not blocks and not is_preview:
        return ""
    rows = siteconfig.group_block_rows(blocks)
    ctx = {**context.flatten(), "pb_rows": rows, "pb_page_key": page_key}
    # UC2-3(b): ссылочным секциям (faq_ref/…) нужен глобальный `site` — на
    # страницах его нет в контексте (в отличие от главной); отдаём тот же
    # локализованный конфиг, НЕ переопределяя, если вьюха уже положила свой.
    ctx.setdefault("site", site)
    html = render_to_string("storefront/_page_blocks.html", ctx, request=request)
    return mark_safe(html)


@register.simple_tag(takes_context=True)
def anfrage_event_choices(context):
    """AF-1 + аудит переводов 2026-08-13: пары (value, подпись) для «Art der
    Veranstaltung».

    value ОСТАЁТСЯ немецким (базовый список): вьюха `/anfrage/` валидирует
    присланное значение по `site_config["anfrage"]["event_types"]` fail-closed и
    кладёт его в `Job.event_type` — запись бизнеса, как и снимок заказа в I18N-10,
    живёт на базовом языке. Переводится ТОЛЬКО показ (оверлей i18n, позиционно).
    """
    request = context.get("request")
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return []
    cfg = siteconfig.normalize(tenant.site_config)
    base = (cfg.get("anfrage") or {}).get("event_types") or []
    shown = (siteconfig.localize(cfg, get_language()).get("anfrage") or {}).get("event_types") or []
    out = []
    for i, value in enumerate(base):
        label = shown[i] if i < len(shown) and isinstance(shown[i], str) and shown[i] else value
        out.append((value, label))
    return out


@register.simple_tag(takes_context=True)
def finder_home(context):
    """FD-2: данные секции Finder главной — {enabled, question(первый вопрос)}.

    Секция — ОПЦИЯ: рендер только при включённом Finder (apps.core.finder.enabled);
    выключен → партиал показывает подсказку ТОЛЬКО в превью билдера."""
    request = context.get("request")
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return {"enabled": False}
    from apps.core import finder as finder_mod

    if not finder_mod.enabled(tenant):
        return {"enabled": False}
    tree = finder_mod.tree_for(tenant)
    return {"enabled": True, "question": tree[0] if tree else None}


@register.simple_tag(takes_context=True)
def render_block(context, block):
    """D.1/D.2: отрисовать секцию главной — фикс-секция (по ключу) или C-блок (dict).

    Принимает строку-ключ (фикс-секция, данные из контекста) ИЛИ dict-блок
    ({key,id,data}). C-блоки рендерятся со своими данными.
    """
    key = block if isinstance(block, str) else block.get("key")
    request = context.get("request")
    # UC2-3(b): ссылочная секция-справочник (faq_ref/team_ref/…) на странице —
    # рендер готового партиала БАЗОВОЙ секции с глобальным site.<key> (контент
    # общий; оси width/pos/visual блока применяет обёртка _section_block).
    if key in siteconfig.PAGE_REF_BLOCKS:
        base = key[: -len("_ref")]
        tpl = BLOCK_TEMPLATES.get(base)
        if not tpl:
            return ""
        html = render_to_string(
            tpl,
            {**context.flatten(), "section_row": {"key": base}},
            request=request,
        )
        return mark_safe(html)
    # D.2: C-блок — рендерим партиал с данными самого блока.
    if key in CBLOCK_TEMPLATES:
        data = block.get("data") if isinstance(block, dict) else {}
        # UC6-4: id блока — для on-canvas фото-кнопки 📷 (data-edit-pk).
        block_id = block.get("id") if isinstance(block, dict) else ""
        html = render_to_string(
            CBLOCK_TEMPLATES[key],
            {**context.flatten(), "block": data or {}, "block_id": block_id or ""},
            request=request,
        )
        return mark_safe(html)
    tpl = BLOCK_TEMPLATES.get(key)
    if not tpl:
        return ""
    # UC6-6d: строка секции — в контекст (вариант отображения section_row.style).
    html = render_to_string(
        tpl,
        {**context.flatten(), "section_row": block if isinstance(block, dict) else {}},
        request=request,
    )
    anchor = _BLOCK_ANCHOR_ID.get(key)
    if anchor:
        return mark_safe(f'<div id="{anchor}" class="scroll-mt-24">{html}</div>')
    if key in _BLOCK_WRAP_NOID:
        return mark_safe(f'<div class="scroll-mt-24">{html}</div>')
    return mark_safe(html)


@register.simple_tag(name="grid_classes")
def grid_classes(site, key):
    """M20R-1: purge-safe Tailwind-грид секции `key` из site_config.

    Использование: <div class="{% grid_classes site 'products' %}">. Раскладка —
    из layout секции (пресет+override) или её дефолта (без визуальной регрессии).
    """
    return siteconfig.grid_class_string(siteconfig.section_layout(site, key))


@register.simple_tag(name="grid_attrs")
def grid_attrs(site, key, cols="", tail="", count=0, more=False):
    """DL-11: атрибуты «полных рядов» секции `key` (рядом с grid_classes):
    <div class="{% grid_classes site 'products' %}" {% grid_attrs site 'products' %}>.
    `cols="1/2/3"` — для стилей с хардкоженной сеткой; `tail="fill"` — принудительно.
    DL-14: `count=` — число элементов (авто-колонки), `more=True` — в сетке есть
    хвостовая кнопка «Alle anzeigen» (_grid_more.html)."""
    return mark_safe(
        siteconfig.grid_attr_string(
            siteconfig.section_layout(site, key),
            cols or None,
            tail or None,
            count=int(count or 0),
            more=bool(more),
        )
    )


@register.simple_tag(name="sf_grid_attrs")
def sf_grid_attrs(layout=None, cols="", tail="", count=0, default_tail="spread", more=False):
    """DL-14: атрибуты «полных рядов» для сеток БЕЗ секции главной (листинги,
    хардкоженные сетки): раскладка страницы (dict) и/или триплет `cols`; дефолт
    хвоста — spread (листинги контент не прячут, неполный ряд распределяется)."""
    return mark_safe(
        siteconfig.grid_attr_string(
            layout if isinstance(layout, dict) else None,
            cols or None,
            tail or None,
            count=int(count or 0),
            more=bool(more),
            default_tail=default_tail,
        )
    )


@register.simple_tag(name="layout_is_default")
def layout_is_default(site, key):
    """DL-11: раскладка секции не тронута (равна дефолту секции)? Стили с жёсткой
    сеткой (categories compact) держат прежние классы, пока владелец/кит не
    настроил колонки — тогда сетка берётся из движка."""
    default = siteconfig.normalize_layout(None, siteconfig.GRID_SECTION_DEFAULTS.get(key))
    current = siteconfig.section_layout(site, key)
    return {k: v for k, v in current.items() if k != "tail"} == default


@register.simple_tag(name="section_font_vars")
def section_font_vars(font_key):
    """H1.5: CSS-переменные шрифта секции (--font-body/--font-head) — оверрайд
    глобального для текстов этой секции. Пусто/неизвестный ключ → "" (наследует
    глобальные vars из _base.html). Каскадит даже через display:contents-обёртку."""
    if not font_key or font_key not in siteconfig.FONTS:
        return ""
    body, head = siteconfig.font_stacks(font_key)
    # Стеки содержат двойные кавычки ("Segoe UI"); это inline-style HTML-атрибут
    # (style="…") → двойные кавычки закрыли бы атрибут. В CSS '…' эквивалентны "…".
    body, head = body.replace('"', "'"), head.replace('"', "'")
    return mark_safe(f"--font-body:{body};--font-head:{head};")


@register.simple_tag(name="section_title")
def section_title(site, key):
    """M20U-7: кастомный заголовок секции главной (или "" → шаблон выводит дефолт)."""
    return siteconfig.section_title(site, key)


@register.simple_tag(name="section_intro")
def section_intro(site, key):
    """H1: описание секции главной под заголовком (или "" — нечего выводить)."""
    return siteconfig.section_intro(site, key)


@register.simple_tag(name="section_show_all")
def section_show_all(site, key):
    """M20U-7: показывать ли ссылку «View all» секции (по умолчанию True)."""
    return siteconfig.section_show_all(site, key)


@register.simple_tag(name="purchase_label")
def purchase_label(module):
    """M20U-5: подпись действия покупки архетипа (Jetzt buchen / In den Warenkorb …)."""
    from apps.core import archetypes

    return archetypes.purchase_label(module)


@register.simple_tag(name="usp_icon")
def usp_icon(token):
    """A.3: emoji-символ пункта полосы доверия (usp_bar) по токену."""
    return siteconfig.usp_icon(token)


@register.filter(name="video_embed")
def video_embed(url):
    """URL видео → {"kind","src"} (см. apps.tenants.video.embed_info) или None."""
    return video.embed_info(url)


_CURRENCY_SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£", "CHF": "CHF"}


@register.filter(name="cursym")
def cursym(code):
    """Код валюты → символ («EUR» → «€»); неизвестный — как есть."""
    return _CURRENCY_SYMBOLS.get((code or "").strip().upper(), code)


#: MEN-22: посетительский переключатель вида прайс-листа — стартовое состояние
#: по стилю владельца. Пустая строка = переключателя нет (kompakt/karte/buch —
#: особые «печатные» виды, посетительская смена ломала бы их идею).
_PL_TOGGLE_INITIAL = {
    "": "plain",
    "preisliste": "plain",
    # Ревью MEN-22: preisliste_2sp здесь НЕТ — колонки-без-фото не совпадают ни с
    # одним из трёх состояний переключателя (стартовое «plain» врало, а клик по
    # активной кнопке заменял md:columns-2 владельца на узкий список без пути
    # назад). 2sp — авторский вид, как kompakt/karte/buch.
    "preisliste_foto": "foto",
    "preisliste_foto_2sp": "cols",
    "preisliste_foto_3sp": "cols",
}


# DL-19: действующая ФОРМА карточки. Своя у товара/акции побеждает дефолт сайта
# (`site_defaults.card_style` / `promo_card`); мусор в любом слое → "" (прежняя
# форма). Партиалы карточек ЗАТЕНЯЮТ этими фильтрами одноимённые контекстные
# переменные — ветвление и замки разметки остаются прежними, меняется только
# источник значения.
@register.simple_tag(takes_context=True)
def card_form(context, entity, kind=card_forms.PRODUCT):
    site_default = context.get(
        "storefront_promo_card" if kind == card_forms.PROMO else "storefront_card_style", ""
    )
    return card_forms.card_form(entity, site_default, kind)


@register.filter(name="has_more_rows")
def has_more_rows(groups):
    """MEN-24c: хотя бы одна группа прайса срезана капом строк (g["more"])."""
    try:
        return any(g.get("more") for g in groups or [])
    except (TypeError, AttributeError):
        return False


@register.filter(name="price_view_state")
def price_view_state(style, page_mode=None):
    """Стиль прайс-листа → стартовый вид переключателя ('' = без переключателя).
    MEN-24d: page_mode (pl_page каталога) глушит class-swap — там вид серверный."""
    if page_mode:
        return ""
    return _PL_TOGGLE_INITIAL.get(style or "preisliste", "")


@register.inclusion_tag("storefront/_presence_fab.html", takes_context=True)
def presence_fab(context):
    """LS-2: плавающий бейдж «Jetzt erreichbar — Video-Anruf» (wa.me, LS-1).

    Показывается только когда бизнес доступен (apps.core.presence: авто по
    часам или override) И задан Tenant.whatsapp_number — иначе пусто (фолбэк =
    чат-FAB inbox и обычные CTA брони)."""
    request = context.get("request")
    tenant = getattr(request, "tenant", None)
    wa_url = ""
    if tenant is not None:
        from apps.core import presence
        from apps.core.whatsapp import wa_link

        if presence.available_now(tenant):
            wa_url = wa_link(
                getattr(tenant, "whatsapp_number", ""),
                _("Ich bin gerade auf Ihrer Website — können Sie mir kurz per Video helfen?"),
            )
    return {"wa_url": wa_url}


@register.inclusion_tag("storefront/_booking_info.html", takes_context=True)
def booking_info(context):
    """Фидбэк 2026-07-28: инфо-блок под листингом Termine для всех booking-
    архетипов («как проходит запись» + часы/адрес/контакт).

    В embed-режиме (iframe-виджет на чужом сайте) не рендерится — там нужна
    только воронка. wa.me строим хелпером LS-1 (номер с пробелами/скобками
    фильтрами не очищался)."""
    request = context.get("request")
    tenant = getattr(request, "tenant", None)
    if tenant is None or context.get("embed"):
        return {"tenant": None}
    from apps.core import modules
    from apps.core.whatsapp import wa_link

    return {
        "tenant": tenant,
        # Ревью 2026-07-28: контекст-процессоры в инклюжн-тег не попадают —
        # гейт модуля inbox тащим сами (иначе ссылка ведёт в 404).
        "inbox_on": modules.is_module_active(tenant, "inbox"),
        "wa_url": wa_link(getattr(tenant, "whatsapp_number", "")),
        "has_contact_card": bool(
            getattr(tenant, "public_phone", "") or getattr(tenant, "whatsapp_number", "")
        ),
    }


@register.inclusion_tag("storefront/_sold_badge.html")
def sold_badge(kind, pk):
    """LS-4 v2 «Verkauft N diese Woche» — честный порог (social_proof).
    n=None (мало/нет данных/ошибка) → партиал рендерит пусто."""
    from apps.core import social_proof

    return {"n": social_proof.sold_last_week(kind, pk), "kind": kind}


@register.filter(name="lang_badge")
def lang_badge(code):
    """Ярлык локали для пилюли переключателя (фидбэк 2026-07-31: украинский — UA).

    Внутренний код при этом остаётся `uk` — см. apps/core/langs.py."""
    from apps.core.langs import badge

    return badge(code)


# ── DS-3a (Fokus): «прайс-лист» — вид вывода товаров ────────────────────────


def _price_group_rows(products):
    """Сгруппировать товары по категории (порядок sort_order, безкатегорийные в
    конце). Продукты идут в исходном порядке внутри группы."""
    groups: dict = {}
    for p in products:
        cat = getattr(p, "category", None)
        key = cat.pk if cat is not None else None
        if key not in groups:
            name = cat.get_i18n("name") if cat is not None else _("Weitere")
            sort = getattr(cat, "sort_order", 10**6) if cat is not None else 10**6
            groups[key] = {"name": name, "sort": sort, "items": []}
        groups[key]["items"].append(p)
    return sorted(groups.values(), key=lambda g: g["sort"])


@register.simple_tag
def price_list_groups(limit=40, rows=0):
    """Секция главной в стиле «preisliste»: активные товары группами по
    категориям (собственный запрос — выполняется ТОЛЬКО при выбранном стиле;
    лимит секции-превью намеренно шире карточного — прайс сканируется).

    MEN-24c: rows>0 — кап СТРОК на группу (настройка секции «Zeilen»); срез
    помечается g["more"] → под списком появляется «Mehr anzeigen». Запрос при
    капе расширяется: 40 товаров не хватает «по 3 в каждой из многих групп»."""
    from apps.catalog.models import Product

    try:
        rows = max(0, int(rows or 0))
    except (TypeError, ValueError):
        rows = 0
    if rows:
        limit = max(limit, 200)
    qs = (
        Product.objects.filter(is_active=True)
        .select_related("category")
        .order_by("category__sort_order", "-is_featured", "created_at")[:limit]
    )
    groups = _price_group_rows(qs)
    if rows:
        for g in groups:
            g["more"] = len(g["items"]) > rows
            g["items"] = g["items"][:rows]
    return groups


@register.simple_tag(takes_context=True)
def menu_labels_active(context):
    """MEN-24a-гейт: показывать ли маркировку (диеты/аллергены) в прайс-строках.

    Тег, а не site.*: на /sortiment/ `site` в контекст не кладётся (вьюха
    разворачивает cfg плоско) — site.menu_labels там молча давал бы ''.
    Гейт FOOD-типов + явное включение владельцем; fail-closed."""
    try:
        from apps.catalog.views import FOOD_BUSINESS_TYPES

        request = context.get("request")
        tenant = getattr(request, "tenant", None)
        return (
            tenant is not None
            and getattr(tenant, "business_type", "") in FOOD_BUSINESS_TYPES
            and bool((tenant.site_config or {}).get("menu_labels"))
        )
    except Exception:  # noqa: BLE001 — витрина не должна падать
        return False


@register.simple_tag
def allergen_legend(groups):
    """MEN-24a: легенда буквенных сносок по ФАКТИЧЕСКИ встреченным аллергенам
    выдачи — [(буква, метка)], порядок реестра (та же схема, что PDF GK-13)."""
    try:
        from apps.catalog.food import ALLERGENS, allergen_letters

        seen: set = set()
        for g in groups or []:
            for p in g.get("items", []):
                seen.update(getattr(p, "allergens", None) or [])
        letters = allergen_letters()
        return [(letters[code], label) for code, label in ALLERGENS if code in seen]
    except Exception:  # noqa: BLE001
        return []


@register.simple_tag
def price_groups_from(items):
    """Страница каталога в пресете «preisliste»: группировка ТЕКУЩЕЙ выдачи
    листинга (фасеты/поиск/пагинация уже применены провайдером UB)."""
    return _price_group_rows(list(items))


@register.simple_tag
def book_pages(groups, per_page=8):
    """MEN-16: страницы «меню-книги» из групп прайса.

    Страница = группа, но длинная группа режется на несколько страниц: иначе
    разворот выходит кривым (слева два блюда, справа четырнадцать). Продолжение
    несёт то же название и флаг `cont` — заголовок помечается «Fortsetzung».
    Форма элемента та же ({name, items}), поэтому цикл рендера один на все виды.
    """
    out = []
    for group in groups or []:
        items = list(group.get("items") or [])
        for start in range(0, len(items), per_page):
            out.append(
                {
                    "name": group.get("name"),
                    "items": items[start : start + per_page],
                    "cont": start > 0,
                }
            )
    return out


@register.simple_tag(takes_context=True)
def speisekarte_pdf_available(context):
    """GK-13-гейт для мест вне вьюхи каталога (секция главной): FOOD-тип и есть
    активные товары — зеркало условия storefront-speisekarte-pdf (fail-closed)."""
    try:
        from apps.catalog.models import Product
        from apps.catalog.views import FOOD_BUSINESS_TYPES

        request = context.get("request")
        tenant = getattr(request, "tenant", None)
        return (
            tenant is not None
            and getattr(tenant, "business_type", "") in FOOD_BUSINESS_TYPES
            and Product.objects.filter(is_active=True).exists()
        )
    except Exception:  # noqa: BLE001 — витринная секция не должна падать
        return False


@register.simple_tag
def categories_with_min_price(categories):
    """DS-4b/DS-5: данные плитки направления — «ab X €» (Min base_price) и число
    активных товаров категории (ОДИН запрос агрегатом на все категории)."""
    from django.db.models import Count, Min

    from apps.catalog.models import Product

    pks = [c.pk for c in categories]
    agg = {
        row[0]: (row[1], row[2])
        for row in Product.objects.filter(is_active=True, category_id__in=pks)
        .values_list("category_id")
        .annotate(m=Min("base_price"), n=Count("id"))
        .values_list("category_id", "m", "n")
    }
    return [
        {"c": c, "min_price": agg.get(c.pk, (None, 0))[0], "count": agg.get(c.pk, (None, 0))[1]}
        for c in categories
    ]


@register.filter(name="is_food_business")
def is_food_business(tenant) -> bool:
    """O-7 (стенд аутлета): гастро-язык на витрине НЕ-гастро тенанта.

    Страница наборов называлась «Kombinationen & Menüs» и звала 🍔 «Menüs»
    даже в магазине техники: «Menü» — слово общепита, у аутлета набор это
    «Set». Реестр типов один — `core.archetypes.FOOD_BUSINESS_TYPES`.
    """
    from apps.core.archetypes import FOOD_BUSINESS_TYPES

    return getattr(tenant, "business_type", "") in FOOD_BUSINESS_TYPES
