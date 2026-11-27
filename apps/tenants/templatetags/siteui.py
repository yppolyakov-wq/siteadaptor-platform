"""Шаблонные фильтры витрины (site_config UI)."""

import logging

from django import template
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe
from django.utils.translation import get_language
from django.utils.translation import gettext as _

from apps.core import block_catalog, card_forms
from apps.tenants import siteconfig, video

logger = logging.getLogger(__name__)
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
    # LB-1: блок «Liste» — акции или товары с фильтром и своим видом (легаси PT-6
    # «акции одного типа» читается как он: siteconfig.LEGACY_CBLOCK_ALIASES).
    "list": "storefront/sections/_block_list.html",
    "stats": "storefront/sections/_block_stats.html",
    "banner": "storefront/sections/_block_banner.html",  # FB-22b  # GK-4: полоса цифр
    "newsletter": "storefront/sections/_block_newsletter.html",  # GK-8: подписка (DOI)
    "textpage": "storefront/sections/_block_textpage.html",  # FB-27 R6
    "contact_card": "storefront/sections/_block_contact.html",  # FB-27 R6
    "quick_links": "storefront/sections/_block_quick_links.html",  # FB-33 M2c
    "site_search": "storefront/sections/_block_site_search.html",  # FB-33 M5a
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
        Promotion.objects.filter(Promotion.on_sale_q())
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
    if widget == registry.MENU_SET:
        # FB-33 M5a: плитки — верхний уровень меню витрины из контекста (второго разбора нет)
        return {"tiles": registry.menu_tiles(context.get("storefront_menu"))}
    deal = deal_of_day() if registry.needs_deal(widget) else None
    # FB-33 M3-5b: скрытые плашки и свои подписи блока «Schnellzugriff» (`quick_links_html`)
    hidden, labels = context.get("ql_hidden") or (), context.get("ql_labels") or {}
    return {"tiles": registry.tiles_for(widget, tenant, deal=deal, hidden=hidden, labels=labels)}


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
        "lead": context.get("lead") or {},
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
def list_block(context, block):
    """LB-1: данные блока «Liste» — выборка источника + действующий вид.

    Конфиг берётся из контекста (`site`): на главной и в тегах блоков страниц он уже
    нормализован и учитывает черновик Студии (?preview=1), поэтому вид, унаследованный
    от типа или страницы, в превью совпадает с тем, что редактирует владелец. Без
    `site` (сторонний шаблон) — сохранённый конфиг тенанта.
    """
    from apps.core import list_blocks

    request = context.get("request")
    tenant = getattr(request, "tenant", None)
    data = block if isinstance(block, dict) else {}
    if not list_blocks.source_active(tenant, data):
        return {"items": []}
    site = context.get("site")
    cfg = site if isinstance(site, dict) and "sections" in site else None
    if cfg is None:
        cfg = siteconfig.normalize(tenant.site_config)
    # FB-29 R7: блок в узкой ширине (⅔, ½, ⅓) — столько колонок, сколько помещается
    row = context.get("b")
    width = row.get("width") if isinstance(row, dict) else ""
    if width in siteconfig._NARROW_COLS:
        layout = list_blocks.effective_view(cfg, data)["layout"]
        if not layout.get("scroll"):
            data = _narrow_list_data(data, width, int(layout.get("cols") or 0))
    # LB-3: та же выборка, что уже посчитала вьюха страницы акций (чипы Sprungleiste),
    # — из кэша запроса, а не вторым набором запросов.
    return list_blocks.resolve_for(request, cfg, data)


def _narrow_list_data(data: dict, width: str, cols: int) -> dict:
    """Данные блока «Liste» с числом колонок, которое помещается в его ширину."""
    cap = siteconfig._NARROW_COLS.get(width)
    if not cap or cols <= cap:
        return data
    return {**data, "cols": cap}


def _is_promo_list(block) -> bool:
    if siteconfig.cblock_type(block.get("key")) != "list":
        return False
    data = block.get("data") if isinstance(block.get("data"), dict) else {}
    return (data.get("source") or siteconfig.LIST_SOURCE_DEFAULT) == "promotions"


@register.simple_tag(takes_context=True)
def page_flow(context, host):
    """FB-32 S6c: поток строк страницы с постоянными разделами ({"page_flow", "tail_part"}) —
    тегом, а не во вьюхе: страницу «Kontakt» рендерят два пути (форма с ошибкой и GET).
    Пусто — прежняя разметка."""
    from apps.core import detail_parts, page_settings

    empty = {"page_flow": [], "tail_part": "after"}
    request = context.get("request")
    if getattr(request, "tenant", None) is None:
        return empty
    try:
        return detail_parts.flow_ctx(page_settings.raw_config(request), host)
    except Exception:  # noqa: BLE001 — сбой превью не роняет страницу формы (как page_blocks)
        logger.warning("page_flow failed for %s", host, exc_info=True)
        return empty


@register.simple_tag(takes_context=True)
def page_blocks(context, page_key, part="after"):
    """UC6-7: C-блоки страницы (хост site_config.page_blocks[page_key]) —
    рендер как на главной (ряды узких блоков + _section_block: клик→лента,
    📷, инлайн работают). При ?preview=1 — черновик сессии (live-preview).

    LB-2: `part` — какая часть блоков листинга: "before" — над основным списком
    (до маркера `main`), "after" — под ним. Без маркера всё под списком, как раньше.
    Пунктирный якорь пустого хоста в превью рисует только "after" — иначе на пустой
    странице было бы два «＋»."""
    request = context.get("request")
    tenant = getattr(request, "tenant", None)
    if request is None or tenant is None:
        return ""
    # M21.11: один читатель «что показывать» с остальной витриной (черновик Студии,
    # превью шаблона кабинета, превью сохранённого `stand=saved`).
    from apps.core import page_settings

    try:
        raw = page_settings.raw_config(request)
    except Exception:  # noqa: BLE001 — превью не должно ронять витрину
        raw = tenant.site_config
    # Аудит переводов 2026-08-13: блоки берём из ЛОКАЛИЗОВАННОГО конфига — раньше
    # тег читал их из голого normalize, и текст C-блоков страниц («Über uns»,
    # корзина) оставался немецким на любой локали даже при готовом оверлее.
    # ревью P5: один разбор конфига на запрос (деталь зовёт тег на каждый кусок блоков)
    cache_key = ("_pb_site", get_language())
    cached = getattr(request, "_page_blocks_site", None)
    if cached and cached[0] == cache_key and cached[1] is raw:
        site = cached[2]
    else:
        site = siteconfig.localize(siteconfig.normalize(raw), get_language())
        try:
            request._page_blocks_site = (cache_key, raw, site)
        except AttributeError:
            pass
    # FB-33 M5a: строки — через `page_rows` (умолчание страницы 404 считает она); у прочих
    # хостов тег получает уже выбранный хост, для них это прежнее чтение ключа
    stored = siteconfig.page_rows(site, page_key)
    above, below = siteconfig.split_at_main(stored)
    if isinstance(part, str) and part.startswith("ids:"):
        # FB-31 P5: кусок блоков детали между разделами (по id, в порядке хранения)
        wanted = set(part[4:].split(","))
        chunk = [b for b in stored if b.get("id") in wanted and b.get("enabled", True)]
        if not chunk and part != "ids:":
            return ""  # ревью P5: без пустого «＋» посреди страницы в превью
        above, below = [], chunk
        part = "after"
    before = part == "before"
    # FB-31 P0: встроенные строки-списки (блок «Kategorien» каталога) рисует сама страница
    # листинга в своих местах (шаг R2), не общий цикл блоков — иначе вид сайта сдвинулся бы.
    builtin = siteconfig.page_builtin_keys(page_key)
    blocks = [
        b
        for b in (above if before else below)
        if b.get("enabled", True) and b.get("key") not in builtin
    ]
    if context.get("pb_hide_promo_lists"):
        # LB-3 (план §12.4): на странице типа и в результатах поиска/фильтра блоки
        # «Liste» с акциями — композиция ОБЗОРА: там они дублировали бы выдачу.
        # Прочие блоки (текст, кнопка, товары) остаются, как раньше.
        blocks = [b for b in blocks if not _is_promo_list(b)]
    is_preview = bool(context.get("is_preview"))
    if not is_preview:
        blocks = _drop_empty_faq(blocks, page_key, context.get("site") or site, context, raw)
    # FB-33 M2h / M5a / стопка 14 E8: запреты блоков хоста — один вопрос с normalize и «+ Block»
    # (`banned_blocks`), для ВСЕХ хостов: «Suche» вне 404, блоки с формами на подтверждении.
    # Фильтр ДО проверки пустоты (ревью L2): у `FORMLESS_HOSTS` части `before` нет — 404 зовёт
    # тег без части, подтверждение кусками `ids:` (они идут как `after`), да и строк над
    # списком у них нет; плейсхолдер превью «＋» рисует только часть `after`, как прежде
    banned = siteconfig.banned_blocks(page_key)
    blocks = [b for b in blocks if b.get("key") not in banned]
    if not blocks and (before or not is_preview):
        return ""
    if page_key in siteconfig.FORMLESS_HOSTS:
        # FB-33 M2h (ПДн): на подтверждении блоки с полями ввода не рисуются, а остальные — с
        # ЧИСТЫМ контекстом: сделка и данные клиента вьюхи в блоки не попадают. FB-33 M5a: то
        # же на странице 404 (её отдают анониму на любом адресе — без форм и без cookie)
        if not blocks and not is_preview:
            return ""
        clean = {"pb_rows": siteconfig.group_block_rows(blocks), "pb_page_key": page_key}
        clean.update({"site": site, "is_preview": is_preview})
        return mark_safe(render_to_string("storefront/_page_blocks.html", clean, request=request))
    rows = siteconfig.group_block_rows(blocks)
    ctx = {**context.flatten(), "pb_rows": rows, "pb_page_key": page_key}
    # UC2-3(b): ссылочным секциям (faq_ref/…) нужен глобальный `site` — на
    # страницах его нет в контексте (в отличие от главной); отдаём тот же
    # локализованный конфиг, НЕ переопределяя, если вьюха уже положила свой.
    ctx.setdefault("site", site)
    ctx.setdefault("pb_raw", raw)  # FB-33 M2b-2b: черновик своих вопросов в превью
    html = render_to_string("storefront/_page_blocks.html", ctx, request=request)
    return mark_safe(html)


def _drop_empty_faq(blocks: list, page_key, site, context=None, raw=None) -> list:
    """FB-33 M2b-2a: на детальной блок FAQ без общих вопросов не рисуется совсем — ни обёртки,
    ни места в ряду узких блоков (фильтр ДО `group_block_rows`). В превью он остаётся.
    FB-33 M2b-2b: по каждому блоку и его источнику — блок своих вопросов объекта без вопросов
    (`object_faq.drop_empty`) тоже не рисуется."""
    from apps.core import faq_views, object_faq

    if context is not None:
        blocks = object_faq.drop_empty(blocks, context, page_key, raw)
    if not faq_views.is_detail_host(page_key):
        return blocks
    faq = site.get("faq") if isinstance(site, dict) else getattr(site, "faq", None)
    if any(isinstance(f, dict) and (f.get("q") or f.get("a")) for f in faq or ()):
        return blocks  # записи с пустыми вопросом и ответом — всё равно пустой FAQ
    return [
        b for b in blocks if b.get("key") != "faq_ref" or object_faq.is_object_source(b.get("data"))
    ]


@register.simple_tag(takes_context=True)
def form_field_modes(context, form):
    """FB-33 M2i: какие поля формы `form` спрашивать, какие обязательны и их подписи
    (`apps.core.form_spec.view`). Без настроек — прежний состав формы (замки M2i-0)."""
    from apps.core import form_spec

    request = context.get("request")
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return form_spec.view({}, form)
    return form_spec.view(_form_site(request, tenant), form)


def _form_site(request, tenant) -> dict:
    """Нормализованный конфиг формы заявки — с учётом превью (FB-33 M2i-5: черновик вкладки
    «Felder» `?preview=1&aufbau=anfrage` — через `page_settings.raw_config`, единый читатель
    витрины). Одна нормализация на запрос: форма бывает и в блоке, и в модалке, и на странице."""
    site = getattr(request, "_form_fields_site", None)
    if site is None:
        from apps.core import page_settings

        raw = page_settings.raw_config(request) if hasattr(request, "GET") else None
        site = siteconfig.normalize(raw if raw is not None else tenant.site_config)
        try:
            request._form_fields_site = site
        except AttributeError:  # неизменяемая заглушка запроса — без кеша
            pass
    return site


@register.simple_tag(takes_context=True)
def anfrage_event_choices(context):
    """AF-1 + аудит переводов 2026-08-13: пары (value, подпись) для «Art der
    Veranstaltung».

    value ОСТАЁТСЯ немецким (базовый список): вьюха `/anfrage/` валидирует
    присланное значение по `site_config["anfrage"]["event_types"]` fail-closed и
    кладёт его в `Job.event_type` — запись бизнеса, как и снимок заказа в I18N-10,
    живёт на базовом языке. Переводится ТОЛЬКО показ — FB-33 M2i-5b: по тексту варианта
    (`form_spec.event_type_choices`), старый позиционный оверлей — запасной путь.
    """
    request = context.get("request")
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return []
    from apps.core import form_spec

    cfg = _form_site(request, tenant)  # FB-33 M2i-5: превью черновика — как и поля формы
    return form_spec.event_type_choices(cfg, get_language())


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
def category_blocks(context, category_host="", part="after"):
    """FB-27 R7 (решение владельца Q2): своя схема категории ЗАМЕНЯЕТ блоки каталога на
    её странице. Своей схемы нет (хост пуст) — страница показывает блоки каталога."""
    host = "catalog"
    request = context.get("request")
    if category_host and request is not None:  # корень каталога — без лишней нормализации
        from apps.core import page_settings

        try:
            raw = page_settings.raw_config(request)
        except Exception:  # noqa: BLE001 — превью не должно ронять витрину
            raw = getattr(getattr(request, "tenant", None), "site_config", None)
        cfg = siteconfig.normalize(raw)
        if siteconfig.has_own_schema(cfg, category_host):
            host = category_host
        else:
            # FB-30.16 R5: общие блоки «Alle Kategorien», если сохранены; иначе каталог
            host = siteconfig.shared_category_host(cfg)
    return page_blocks(context, host, part)


@register.simple_tag(takes_context=True)
def promo_blocks(context, group_key="", part="after"):
    """FB-31 P3 R6: блоки страниц акций. Обзор — свои; страница группы — своя схема
    группы, иначе «Alle Angebotsgruppen», иначе блоки обзора (как до R6)."""
    host = "promos"
    request = context.get("request")
    if group_key and request is not None:
        from apps.core import page_settings

        try:
            raw = page_settings.raw_config(request)
        except Exception:  # noqa: BLE001 — превью не должно ронять витрину
            raw = getattr(getattr(request, "tenant", None), "site_config", None)
        cfg = siteconfig.normalize(raw)
        own = siteconfig.promo_group_host(group_key)
        if own and own in (cfg.get("page_blocks") or {}):
            host = own
        else:
            host = siteconfig.shared_promo_group_host(cfg)
    return page_blocks(context, host, part)


@register.simple_tag(takes_context=True)
def place_banners(context, kind, obj):
    """FB-29.2c: баннеры, которым эта страница задана в «Wo zeigen» (категория, товар,
    услуга, акция). Рисует тот же блок, что «Banner» в схеме: один баннер — баннер,
    несколько — слайдер. Баннеров нет — пусто."""
    from apps.core import banners

    request = context.get("request")
    key = banners.place_key(kind, obj) if request else ""
    if not key:
        return ""
    picks = banners.picks_for_place(key)
    if not picks:
        return ""
    # S6: место баннеров задаёт структура — блок «Banner» с источником «баннеры этой
    # страницы». Стоит такой блок — это место по умолчанию молчит. Структуру читаем,
    # только когда баннеры для страницы есть (обычная страница — один запрос, без разбора).
    if kind in banners.SHOW_ON_TYPES:
        tenant = getattr(request, "tenant", None)
        try:
            from apps.core import page_settings

            config = siteconfig.normalize(page_settings.raw_config(request))
        except Exception:  # noqa: BLE001 — превью не должно ронять витрину
            config = siteconfig.normalize(getattr(tenant, "site_config", None))
        if kind == "category":
            own = siteconfig.category_host(getattr(obj, "slug", ""))
            hosts = [own if siteconfig.has_own_schema(config, own) else "catalog"]
        else:  # блок-место — в блоках типа страницы либо в своих блоках объекта (R5)
            hexed = getattr(getattr(obj, "pk", None), "hex", "")
            # вид объекта: акция — «promo»; тип страницы: тур делит его с событием
            from apps.core import site_schema

            own = {"promotion": "promo"}.get(kind, kind)
            shared = site_schema.OBJECT_PAGE_TYPES.get(own, own)
            hosts = [f"{shared}_detail", f"{own}:{hexed}"]
        if banners.place_block_present(config, hosts):
            return ""
    # `auto_place`: баннер стоит здесь сам, блока в схеме нет — без меток правки Студии
    block = {"pick": picks, "height": "sm", "arrows": len(picks) > 1, "auto_place": True}
    ctx = {**context.flatten(), "block": block, "is_preview": False}
    html = render_to_string("storefront/sections/_block_banner.html", ctx, request=request)
    return mark_safe(html)


@register.simple_tag(takes_context=True)
def object_blocks(context, kind, obj, part="after"):
    """FB-29.4b: СВОИ блоки объекта (товар, услуга) — только на его странице. Стоят под
    общими блоками страницы либо (R3, выбор на вкладке объекта) над ними: шаблон зовёт
    тег с обеих сторон, рисует та, что выбрана. Блоков нет — пусто."""
    from apps.core import detail_parts, object_structure, page_settings

    request = context.get("request")
    host = object_structure.object_host(kind, obj)
    if not host or request is None:
        return ""
    try:
        raw = page_settings.raw_config(request)
    except Exception:  # noqa: BLE001 — превью не должно ронять витрину
        logger.warning("object_blocks: raw_config failed, using saved config", exc_info=True)
        raw = getattr(getattr(request, "tenant", None), "site_config", None)
    if not ((raw or {}).get("page_blocks") or {}).get(host):
        return ""
    # FB-31 P5 R8: свои блоки стоят между разделами (строки разделов в схеме объекта) —
    # здесь только хвост после последнего раздела; остальное рисует поток тела
    tail = detail_parts.own_tail(raw, kind, obj)
    if tail is not None:
        return page_blocks(context, host, tail) if tail and part != "before" else ""
    if (part == "before") != object_structure.blocks_first(obj, kind):
        return ""
    return page_blocks(context, host)


def _shown_raw(request):
    """Показываемый сырой конфиг: черновик в превью (`page_settings.raw_config`, «Vorschau»
    окна видит перевод до «Speichern»), иначе сохранённый."""
    from apps.core import page_settings

    tenant = getattr(request, "tenant", None)
    try:
        return page_settings.raw_config(request)
    except Exception:  # noqa: BLE001 — превью не должно ронять витрину
        logger.warning("siteui: raw_config failed, using saved config", exc_info=True)
        return getattr(tenant, "site_config", None) or {}


@register.simple_tag(takes_context=True)
def page_seo(context, host):
    """FB-27 «Seiten»: свои заголовок, описание и noindex текстовой страницы (`{}` — нет).
    Стопка 16 T1b: заголовок и описание — на языке посетителя (перевод окна по полю, без
    него — немецкое), `noindex` — из базы; в превью — из черновика."""
    from django.utils.translation import get_language

    from apps.core import content_pages

    request = context.get("request")
    if request is None:
        return {}
    # ревью D2: тег стоит в трёх блоках шаблона (title, description, robots) — одно чтение
    # (и одно предупреждение о битом оверлее) на запрос; копия — шаблон не правит запись
    key = (host or "", get_language() or "")
    memo = getattr(request, "_page_seo_memo", None)
    if memo is None:
        memo = {}
        request._page_seo_memo = memo
    if key not in memo:
        memo[key] = content_pages.page_seo(
            getattr(request, "tenant", None), key[0], locale=key[1], config=_shown_raw(request)
        )
    return dict(memo[key])


@register.simple_tag(takes_context=True)
def usp_lang(context, index, field="label"):
    """Стопка 16 T1b (долг T1a, a11y №14, WCAG 3.1.2): у пункта полосы доверия без перевода на
    язык посетителя — ` lang="de"` (показан немецкий), с переводом — пусто."""
    return item_lang(context, "usp_bar", index, field)


@register.simple_tag(takes_context=True)
def item_lang(context, section, index, field):
    """Стопка 16 T6 (a11y №14): у пункта списка `section` (шаги, команда, отзывы, полоса
    доверия) без перевода поля `field` на язык посетителя — ` lang="de"`, с переводом — пусто.
    Одно правило с `usp_lang`: позиционный оверлей `i18n.<язык>.<секция>` показываемого конфига."""
    from django.conf import settings
    from django.utils.html import format_html
    from django.utils.translation import get_language

    from apps.tenants import siteconfig

    base = settings.LANGUAGE_CODE[:2]
    loc = (get_language() or base)[:2]
    request = context.get("request")
    if loc == base or request is None:
        return ""
    raw = _shown_raw(request)
    root = raw.get("i18n") if isinstance(raw, dict) else None
    node = root.get(loc) if isinstance(root, dict) else None
    rows = node.get(str(section)) if isinstance(node, dict) else None
    try:
        entry = rows[int(index)] if isinstance(rows, list) else None
    except (IndexError, TypeError, ValueError):
        entry = None
    text = entry.get(field) if isinstance(entry, dict) else None
    if isinstance(text, str) and text.strip() and loc in siteconfig.overlay_locales():
        return ""
    return format_html(' lang="{}"', base)


@register.filter
def has_page_block(site, spec) -> bool:
    """FB-27 R6: стоит ли на странице включённый блок типа (`"хост:тип"`). «Über uns» не
    рисует свою фикс-карточку контактов, если владелец поставил блок «Kontakt» сам."""
    host, _sep, key = str(spec).partition(":")
    blocks = (site.get("page_blocks") or {}).get(host, []) if isinstance(site, dict) else []
    return any(
        isinstance(b, dict) and b.get("key") == key and b.get("enabled", True) for b in blocks
    )


@register.simple_tag(takes_context=True)
def page_title(context, host):
    """FB-33 M2d: свой заголовок и вступление страницы ({title, intro, center, custom});
    пусто — прежний текст шаблона. Читает контекст витрины (черновик в превью, язык
    посетителя — `storefront_page_titles`)."""
    from apps.core import page_title as _page_title

    titles = context.get("storefront_page_titles") or {}
    return _page_title.get({"page_titles": titles}, host)


@register.simple_tag(takes_context=True)
def quick_links_html(context, link_set, hidden=None, labels=None):
    """FB-33 M2c: плитки набора (та же разметка, что в баннере); пусто — когда у набора нет
    ни одной плитки (модули выключены или все скрыты, M3-5b) — блок тогда не рисует пустую
    область. `hidden`/`labels` — скрытые плашки и свои подписи блока (ключи набора)."""
    from apps.core import hero_tiles as registry

    if not link_set:
        return ""
    keys = registry.tile_keys(link_set)
    html = render_to_string(
        "storefront/sections/_hero_widget.html",
        {
            **context.flatten(),
            "hero_widget": link_set,
            "ql_hidden": [k for k in hidden or () if k in keys] if isinstance(hidden, list) else [],
            "ql_labels": registry.shown_labels(link_set, labels),
        },
        request=context.get("request"),
    )
    return mark_safe(html) if html.strip() and "<a " in html else ""


@register.simple_tag(takes_context=True)
def ql_visible(context, deal):
    """FB-33 M3-5b: сколько плашек рукописного набора видно (`hero_tiles.visible_count`) —
    пустая сетка не рисуется, одна плашка из скрытых — узкой колонкой."""
    from apps.core import hero_tiles as registry

    hidden = context.get("ql_hidden") or ()
    return registry.visible_count(context.get("hero_widget"), context, deal, hidden)


@register.simple_tag(takes_context=True)
def embedded_page(context, data):
    """FB-27 R6: текст своей страницы для блока «Textseite» ({title, body|teaser, url})
    либо None. Хост берём из контекста страницы — блок не выводит страницу на ней самой."""
    from apps.core import content_pages

    request = context.get("request")
    host = context.get("pb_host") or ""
    if not host:
        name = getattr(getattr(request, "resolver_match", None), "url_name", "") or ""
        host = {"storefront-about": "info", "storefront-shipping": "versand"}.get(name, "")
    # Одна и та же страница в нескольких блоках — одна выборка и одна чистка на запрос.
    data = data if isinstance(data, dict) else {}
    memo = getattr(request, "_embedded_pages", None)
    if memo is None:
        memo = {}
        if request is not None:
            request._embedded_pages = memo
    key = (data.get("page"), data.get("mode"), host)
    if key not in memo:
        memo[key] = content_pages.embedded(data, host, getattr(request, "tenant", None))
    return memo[key]


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
        # FB-33 M2b: свой вид блока (FAQ, команда, галерея, отзывы) — как у секции главной
        data = block.get("data") if isinstance(block, dict) else None
        row = {"key": base}
        if isinstance(data, dict) and data.get("style"):
            row["style"] = data["style"]
        if base == "faq" and isinstance(data, dict) and data.get("source"):
            # FB-33 M2b-2b: свои вопросы объекта страницы — свой партиал (без data-edit канвы)
            from apps.core import object_faq

            if object_faq.is_object_source(data):
                return mark_safe(object_faq.render_block(context, row, request))
        if base == "faq":
            # FB-33 M2b-2a: на детальной общий FAQ без FAQPage (вопросы не об объекте) и с
            # заглушкой в превью, когда вопросов нет
            from apps.core import faq_views

            host = context.get("pb_page_key") or ""
            if not faq_views.emits_ld(host):
                row["no_ld"] = True
            if faq_views.is_detail_host(host):
                row["detail"] = True
        html = render_to_string(tpl, {**context.flatten(), "section_row": row}, request=request)
        return mark_safe(html)
    # D.2: C-блок — рендерим партиал с данными самого блока.
    if key in CBLOCK_TEMPLATES:
        # FB-33 M3-3d: партиал видит только поля активного вида — запомненный текст
        # «Eigener Text» у «Von einer Seite» (и страница у своего текста) не на сайте
        data = block_catalog.active_data(
            siteconfig.cblock_type(key) or key,  # легаси-псевдоним → канонический вид
            block.get("data") if isinstance(block, dict) else {},
        )
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


#: STU-8: ширина текстовой колонки. Классы ПЕРЕЧИСЛЕНЫ литералами — Tailwind
#: собирает CSS сканированием исходников, и составленная в рантайме строка в
#: сборку не попадёт (грабля класса «новый arbitrary-класс требует пересборки»).
_TEXT_WIDTHS = {
    # STU-11: «narrow» — ЯВНЫЙ выбор владельца, а не дефолт: на страницах без
    # исторического ограничителя (команда/галерея/отзывы/лента блога) только он и
    # даёт узкую колонку.
    "narrow": "max-w-2xl mx-auto",
    "wide": "max-w-4xl mx-auto",
    "full": "",
}

#: Ширина, если владелец ничего не выбрал. Зависит от страницы: у «О нас» и
#: правовых узкая колонка была ВСЕГДА, а у команды/галереи/отзывов/блог-ленты
#: ограничителя не было вовсе — навязать им max-w-2xl «по умолчанию» значило бы
#: сузить страницу задним числом (STU-9).
_TEXT_WIDTH_DEFAULTS = {
    "narrow": "max-w-2xl mx-auto",
    "none": "",
}


@register.simple_tag(takes_context=True, name="text_width_class")
def text_width_class(context, default="narrow"):
    """Классы контейнера текстовых страниц («О нас», правовые, блог, команда…).

    Значение берём из контекст-процессора витрины: он уже учёл черновик
    `?preview=1`, поэтому выбор виден вживую, и работает на страницах, куда вьюха
    не кладёт `site` (правовые). Нет значения — ширина страницы такая же, какой
    была до появления настройки (аргумент `default`).
    """
    value = context.get("storefront_text_width") or ""
    if value in _TEXT_WIDTHS:
        return _TEXT_WIDTHS[value]
    return _TEXT_WIDTH_DEFAULTS.get(default, _TEXT_WIDTH_DEFAULTS["narrow"])


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
    хвоста — spread (листинги контент не прячут, неполный ряд распределяется).

    LAY-7d: литеральный `cols` здесь описывает ПРЕЖНЮЮ жёсткую вёрстку шаблона,
    то есть это ФОЛБЭК на случай «владелец раскладку не задавал» (ключи страниц
    presence-minimal → приходит None). Раньше литерал побеждал всегда, и на 13
    колл-сайтах, где передаются ОБА аргумента, класс шёл от владельца (напр. 4
    колонки), а `data-sf-cols` — от литерала (3): CSS «полных рядов» считал ряды
    не для той сетки, и хвост обрезался/распределялся неверно. У секций главной
    (`grid_attrs`) семантика ДРУГАЯ — там раскладка есть всегда, а литерал метит
    стиль с жёсткой сеткой, поэтому правило живёт здесь, а не в `grid_attr_string`.
    """
    lay = layout if isinstance(layout, dict) and layout else None
    return mark_safe(
        siteconfig.grid_attr_string(
            lay,
            None if lay else (cols or None),
            tail or None,
            count=int(count or 0),
            more=bool(more),
            default_tail=default_tail,
        )
    )


@register.simple_tag(name="sf_slider_attrs")
def sf_slider_attrs(layout=None):
    """LAY-7b: параметры слайдера для ГОТОВОЙ flex-ленты (не сетки).

    Лента групп на /aktionen/ рисуется своей разметкой (`flex overflow-x-auto`,
    ширина карточки классом), поэтому общий `sf_grid_attrs` ей не подходит: он
    навесил бы `data-sf-cols`/`data-sf-tail`, которые на flex-полосе ничего не
    значат, и увёл бы разметку от паритета. Отдаём ровно два атрибута оси —
    «сколько строк» и «с какой паузой крутить». Ключей нет → пусто, лента
    прежняя.
    """
    lay = layout if isinstance(layout, dict) else {}
    out = ""
    if lay.get("rows"):
        out += f' data-sf-rows="{int(lay["rows"])}"'
    if lay.get("speed"):
        out += f' data-sf-speed="{int(lay["speed"])}"'
    return mark_safe(out.strip())


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


@register.simple_tag(takes_context=True, name="row_card")
def row_card(context, row, kind=card_forms.PRODUCT):
    """LB-4: форма карточки встроенного списка главной — своя у строки, иначе дефолт
    сайта из контекст-процессора.

    Тегом, а не `|default:storefront_card_style`: отсутствующая переменная в
    АРГУМЕНТЕ фильтра бросает VariableDoesNotExist (а не пустую строку), и главная
    без контекст-процессора витрины падала бы целиком."""
    own = ""
    if isinstance(row, dict) and isinstance(row.get("data"), dict):
        own = row["data"].get("card", "") or ""
    key = "storefront_promo_card" if kind == card_forms.PROMO else "storefront_card_style"
    return own or context.get(key, "") or ""


@register.simple_tag(name="builtin_all_url")
def builtin_all_url(row, fallback=""):
    """LB-4: адрес «View all» встроенного списка главной — листинг с ТЕМ ЖЕ фильтром
    строки (категория → её страница, тип акции → страница типа…). Не встроенная
    строка или сбой — `fallback` (прежний адрес шаблона)."""
    from apps.core import list_blocks

    try:
        return list_blocks.section_all_url(row) or fallback
    except Exception:  # noqa: BLE001 — витрина не падает из-за ссылки
        return fallback


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


@register.simple_tag(takes_context=True)
def business_card_data(context):
    """SP-9: данные карточки «So finden Sie uns» для колонки рядом с формой сообщения/
    заявки (`{% business_card_data as bc %}`); None — ни адреса, ни телефона."""
    from apps.core import business_card

    request = context.get("request")
    return business_card.card_context(getattr(request, "tenant", None))


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


@register.inclusion_tag("storefront/_holiday_banner.html", takes_context=True)
def holiday_banner(context):
    """KA-12 E4.1a: «Betriebsferien vom … bis …» — идёт сейчас или скоро начнётся."""
    request = context.get("request")
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return {"closure": None}
    from django.utils import timezone

    from apps.core import closures

    return {"closure": closures.current_or_next(timezone.localdate(), tenant)}


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
def sample_price_groups(products):
    """FB-30.10: прайс-лист из товаров-примеров предпросмотра (без запросов к базе)."""
    return _price_group_rows(products or [])


@register.simple_tag
def price_list_groups(limit=40, rows=0, row=None):
    """Секция главной в стиле «preisliste»: активные товары группами по
    категориям (собственный запрос — выполняется ТОЛЬКО при выбранном стиле;
    лимит секции-превью намеренно шире карточного — прайс сканируется).

    MEN-24c: rows>0 — кап СТРОК на группу (настройка секции «Zeilen»); срез
    помечается g["more"] → под списком появляется «Mehr anzeigen». Запрос при
    капе расширяется: 40 товаров не хватает «по 3 в каждой из многих групп».

    LB-4: `row` — строка секции; её фильтр («ЧТО»: категория, подборка, «только…»)
    действует и на прайс-вид, иначе выбор владельца менял бы лишь сетку."""
    from apps.catalog.models import Product

    try:
        rows = max(0, int(rows or 0))
    except (TypeError, ValueError):
        rows = 0
    if rows:
        limit = max(limit, 200)
    if isinstance(row, dict) and row.get("data"):
        from apps.core import list_blocks

        base = list_blocks.price_list_products(row)
    else:
        base = Product.objects.filter(is_active=True).select_related("category")
    qs = base.order_by("category__sort_order", "-is_featured", "created_at")[:limit]
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
def additive_legend(groups):
    """KA-12 WR-2 (E3.12): легенда номеров Zusatzstoffe по фактически встреченным
    добавкам выдачи — [(номер, метка)], тот же маппинг, что PDF-Speisekarte."""
    try:
        from apps.catalog.food import ADDITIVES, additive_numbers

        seen: set = set()
        for g in groups or []:
            for p in g.get("items", []):
                seen.update(getattr(p, "additives", None) or [])
        numbers = additive_numbers()
        return [(numbers[code], label) for code, label in ADDITIVES if code in seen]
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


@register.filter(name="is_menu_business")
def is_menu_business(tenant) -> bool:
    """SF-11: «Speisekarte» как заголовок каталога — только у кухни с меню.

    У пекарни, мясной и продуктового каталог — ассортимент, а не меню; реестр
    кухонь один — `core.nav_registry.KITCHEN_TYPES` (кафе, ресторан, кейтеринг).
    """
    from apps.core.nav_registry import KITCHEN_TYPES

    return getattr(tenant, "business_type", "") in KITCHEN_TYPES


#: AIS W4-5d: вид продаваемой сущности → направление гейта готовности.
_SELL_KIND_DIRECTION = {"stay": "zimmer", "service": "termine", "event": "tickets"}


@register.simple_tag(takes_context=True)
def sell_closed(context, kind):
    """AIS W4-5d: касса этого направления закрыта гейтом готовности — показать фразу ВМЕСТО
    формы, чтобы клиент не вводил данные зря. `kind` — вид сущности или "goods"."""
    from apps.core import readiness

    request = context.get("request")
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return False
    direction = (
        readiness.goods_direction(tenant)
        if kind == "goods"
        else _SELL_KIND_DIRECTION.get(kind, kind)
    )
    return not readiness.sell_allowed(tenant, direction)


@register.simple_tag
def hero_lead(site, slides):
    """FB-30.1: чем наполнен приветственный баннер — один источник для всех его видов.

    Баннеры выбраны из библиотеки (`hero_banners.pick`) → заголовок, текст, кнопка, ссылка
    и фото первого показываемого сегодня; старые поля главной в этом случае не подмешиваются
    (иначе на сайте фото одного баннера и текст другого). Выбранные не показываются
    (выключены, вне срока) → старые поля главной БЕЗ фото прежних слайдов. Выбора нет —
    как раньше: старые поля, фото — своё либо первого прежнего слайда."""
    site = site if isinstance(site, dict) else {}
    slides = list(slides or [])
    old = {
        "title": site.get("hero_title") or "",
        "text": site.get("hero_text") or "",
        "image": site.get("hero_image") or "",
        # своё фото главной (без фото прежних слайдов): вид «фото-баннер» берёт только его
        "own_image": site.get("hero_image") or "",
        "button_label": "",
        "href": "",
        "from_banner": False,
    }
    picked = bool((site.get("hero_banners") or {}).get("pick"))
    if picked and slides:
        first = slides[0]
        return {
            "title": first.get("title") or "",
            "text": first.get("text") or "",
            "image": first.get("image") or "",
            "own_image": first.get("image") or "",
            "button_label": first.get("button_label") or "",
            "href": first.get("href") or "",
            "from_banner": True,
        }
    if not picked and not old["image"]:
        heroes = site.get("heroes") or []
        first = slides[0] if slides else (heroes[0] if heroes else {})
        old["image"] = (first.get("image") if isinstance(first, dict) else "") or ""
    return old


@register.simple_tag(takes_context=True)
def hero_slides(context, heroes, choice=None):
    """FB-22: слайды баннера, активные СЕГОДНЯ (`starts`/`ends`), со ссылкой `href`.

    Ссылка: выбранная из списка целей (`link` = «type:target» — тот же резолвер, что
    меню: скрытая запись/выключенный модуль → ссылки нет) → иначе своя `button_url`
    (только безопасные схемы). Слайд без активных дат выпадает — витрина покажет
    одиночный hero, как без слайдов."""
    from django.utils import timezone

    from apps.tenants import menu, siteconfig

    request = context.get("request")
    tenant = getattr(request, "tenant", None)
    today = timezone.localdate().isoformat()
    # FB-29.2: баннеры выбраны из библиотеки — показываем их (в порядке владельца,
    # активные сегодня); выбора нет — прежние слайды настроек.
    if isinstance(choice, dict) and choice.get("pick"):
        import logging

        from django.db import DatabaseError, transaction

        from apps.core import banners

        try:
            with transaction.atomic():
                heroes = banners.resolve(choice["pick"])
        except DatabaseError:
            # библиотека недоступна (например, миграция в этой схеме ещё не применена) —
            # главная показывает прежние слайды, а не ошибку
            logging.getLogger(__name__).exception("banners: library lookup failed")
    out = []
    for h in heroes or []:
        if h.get("starts") and h["starts"] > today:
            continue
        if h.get("ends") and h["ends"] < today:
            continue
        href = ""
        if h.get("link") and tenant is not None:
            ntype, target = h["link"].split(":", 1)
            node = {"label": "x", "type": ntype, "target": target, "enabled": True, "children": []}
            try:
                href = menu._node_url(tenant, node) or ""
            except Exception:  # noqa: BLE001 — битая цель не роняет главную
                href = ""
        if not href:
            href = siteconfig._menu_href(h.get("button_url"))
        out.append({**h, "href": href})
    if isinstance(choice, dict) and choice.get("single"):
        return out[:1]  # FB-32 S3: «Ein Banner» — первый активный из выбранных
    return out


@register.simple_tag(takes_context=True)
def banner_block_slides(context, block):
    """FB-29.2 S4: слайды блока «Banner», когда из библиотеки выбрано НЕСКОЛЬКО баннеров
    (слайдер). Один баннер или свой слайд блока рисует прежняя ветка (`banner_slide`)."""
    pick = _block_picks(context, block)
    if len(pick) < 2 or (isinstance(block, dict) and block.get("single")):
        return []  # FB-32 S3: «Ein Banner» — прежняя ветка одного баннера
    slides = hero_slides(context, [], {"pick": pick})
    return slides if len(slides) > 1 else []


def _block_picks(context, block) -> list:
    """Баннеры блока «Banner»: выбранные в нём либо (S6, источник «баннеры этой страницы»)
    те, которым текущая страница задана в «Wo zeigen»."""
    if not isinstance(block, dict):
        return []
    if block.get("from_page"):
        from apps.core import banners

        return banners.picks_for_place(banners.page_place_key(context))
    return list(block.get("pick") or [])


@register.simple_tag(takes_context=True)
def banner_slide(context, block):
    """FB-22b: C-блок «Banner» → слайд (как у главной) или None вне дат показа."""
    if not isinstance(block, dict):
        return None
    if block.get("pick") or block.get("from_page"):
        # FB-29.2: баннер выбран из библиотеки — он вместо своего слайда блока (вне срока
        # блок пуст; свой слайд его не подменяет: владелец выбрал именно этот баннер)
        pick = _block_picks(context, block)
        slides = hero_slides(context, [], {"pick": pick}) if pick else []
        if not slides:
            return None
        first = slides[0]
        return {**first, "url": first.get("image", ""), "height": block.get("height", "")}
    slides = hero_slides(context, [{**block, "image": block.get("url", "")}])
    return slides[0] if slides else None


def _confirmation_site(request):
    """Локализованный конфиг подтверждения либо None — у сайта ничего своего на этой странице
    (без нормализации: горячий путь, страница прежняя). Один разбор на запрос."""
    from apps.core import confirmation_page, page_settings

    cached = getattr(request, "_confirmation_site", False)
    if cached is not False:
        return cached
    try:
        raw = page_settings.raw_config(request)
    except Exception:  # noqa: BLE001 — превью не должно ронять подтверждение
        logger.warning("confirmation: draft config unreadable", exc_info=True)
        raw = getattr(getattr(request, "tenant", None), "site_config", None)
    raw = raw if isinstance(raw, dict) else {}
    blocks = raw.get("page_blocks") if isinstance(raw.get("page_blocks"), dict) else {}
    own = (
        bool(blocks.get(confirmation_page.HOST))
        or bool(raw.get(confirmation_page.NEXT_KEY))
        or raw.get(confirmation_page.RECOMMEND_FLAG) is True
    )
    site = siteconfig.localize(siteconfig.normalize(raw), get_language()) if own else None
    try:
        request._confirmation_site = site
    except AttributeError:
        pass
    return site


@register.simple_tag(takes_context=True)
def confirmation_lead(context):
    """FB-33 M2h: свои блоки над карточкой подтверждения (хост `confirmation`)."""
    from apps.core import confirmation_page

    request = context.get("request")
    if request is None or getattr(request, "tenant", None) is None:
        return ""
    site = _confirmation_site(request)
    part = confirmation_page.parts(site)["lead"] if site else ""
    return page_blocks(context, "confirmation", part) if part else ""


@register.simple_tag(takes_context=True)
def confirmation_after(context):
    """FB-33 M2h: под карточкой подтверждения — свои блоки, «Was passiert jetzt» (только свой
    текст), «Empfehlungen» (только включённые владельцем), хвост. Пусто — ничего (страница
    прежняя)."""
    from apps.core import confirmation_page

    request = context.get("request")
    if request is None or getattr(request, "tenant", None) is None:
        return ""
    site = _confirmation_site(request)
    if not site:
        return ""
    parts = confirmation_page.parts(site)
    nxt = confirmation_page.clean_next(site.get(confirmation_page.NEXT_KEY))
    rec = []
    order = context.get("order")
    if confirmation_page.recommend_on(site) and not getattr(order, "is_quote", False):
        # запрос на просчёт — не покупка: рекомендаций покупки на нём нет
        rec = confirmation_page.recommend_products(confirmation_page.deal_product_ids(context))
    if not (nxt or rec or any(parts[k] for k in ("after_summary", "after_next", "tail"))):
        return ""
    # чистый контекст: только места блоков, свой текст и товары (без сделки и клиента)
    ctx = {"cp_parts": parts, "cp_next": nxt, "cp_recommend": rec, "site": site}
    ctx["is_preview"] = bool(context.get("is_preview"))
    return mark_safe(render_to_string("storefront/_confirmation_after.html", ctx, request=request))
