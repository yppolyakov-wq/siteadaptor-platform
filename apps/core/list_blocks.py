"""LB-1: блок «Liste» — выборка источника и действующий вид.

План — `docs/lb-list-blocks-plan-2026-10-02.md` §9 (решения владельца §8). Модуль без
разметки: тег `{% list_block %}` (siteui) зовёт `resolve`, строка редактора — `view_hint`.

Блок отвечает на два вопроса:

* **ЧТО** — источник (акции | товары) × фильтр × сортировка × лимит. Фильтры и
  сортировки берутся У ПРОВАЙДЕРА фасетов источника (`core.facets.provider_for`), а не
  заводятся заново: блок показывает ровно то, что показал бы основной список с тем же
  фильтром, и ссылка «Alle N →» ведёт туда же.
* **КАК** — сетка/лента, колонки, ряды, форма карточки. Пустая ось = «как у всех»:
  тип акции → вид страницы источника → дефолт секции главной. Своя форма у самого
  объекта (DL-19) и у его категории (STU-12j) по-прежнему сильнее блока — блок задаёт
  лишь «дефолт сайта» для своих карточек.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.core import card_forms
from apps.tenants import siteconfig

# Вид без каких-либо настроек — как у одноимённой секции главной.
_DEFAULTS = {
    "promotions": siteconfig.GRID_SECTION_DEFAULTS["promotions"],
    "products": siteconfig.GRID_SECTION_DEFAULTS["products"],
    "services": siteconfig.GRID_SECTION_DEFAULTS["services"],
    "stays": siteconfig.GRID_SECTION_DEFAULTS["stay_rooms"],
    "events": siteconfig.GRID_SECTION_DEFAULTS["events"],
    "tours": siteconfig.GRID_SECTION_DEFAULTS["tours"],
    # у наборов секции главной нет — дефолт страницы `/kombi/` (2 в ряд, на lg 4)
    "combos": siteconfig.OPTIONAL_PAGE_LAYOUTS["combos_layout"],
    "categories": siteconfig.GRID_SECTION_DEFAULTS["categories"],
    "reviews": siteconfig.GRID_SECTION_DEFAULTS["reviews"],
    "blog": siteconfig.GRID_SECTION_DEFAULTS["blog"],
}
# LB-3d: раскладка страницы-листинга источника — слой «page» наследования вида, и
# его порядок по умолчанию (дефолт сортировки владельца, STU-15c).
_PAGE_LAYOUT_KEYS = {
    "services": "service_index_layout",
    "stays": "stay_index_layout",
    "events": "events_index_layout",
    "tours": "tours_layout",
    "combos": "combos_layout",
    "blog": "blog_index_layout",
}
_PAGE_SORT_KEYS = {"services": "services_sort", "stays": "stays_sort", "events": "events_sort"}
# Листинг источника — цель «Alle N →» (с теми же параметрами, что понимает его тулбар).
_LISTING_URLS = {
    "services": "storefront-termin",
    "stays": "storefront-unterkunft",
    "events": "storefront-events",
}


# Модуль, без которого источник не показывается: у выключенных акций нет ни страницы
# `/aktionen/`, ни карточек — блок с ними вёл бы в 404 (урок hero-плиток «Deals»).
SOURCE_MODULES = {key: spec["module"] for key, spec in siteconfig.LIST_SOURCES.items()}


_DEAL_MAX_COLS = 2  # «Deal» шириной меньше ~28rem нечитаем (см. effective_view)


def _source(data) -> str:
    source = (data or {}).get("source")
    return source if source in siteconfig.LIST_SOURCES else siteconfig.LIST_SOURCE_DEFAULT


def source_active(tenant, data) -> bool:
    """Включён ли у тенанта модуль источника блока (fail-closed без тенанта)."""
    if tenant is None:
        return False
    return bool(tenant.is_module_active(SOURCE_MODULES[_source(data)]))


def source_label(source: str, tenant=None) -> str:
    """Подпись источника. У наборов — по типу бизнеса: «Menü-Pakete» у гастро и
    «Sets & Pakete» прочим (`combo_labels` — одна подпись на все поверхности)."""
    if source == "combos" and tenant is not None:
        from apps.catalog.combos import combo_labels

        return str(combo_labels(getattr(tenant, "business_type", "") or "")["combos_title"])
    spec = (
        siteconfig.LIST_SOURCES.get(source)
        or siteconfig.LIST_SOURCES[siteconfig.LIST_SOURCE_DEFAULT]
    )
    return str(spec["label"])


def base_view(cfg: dict, data: dict) -> dict:
    """Вид, который блок получает, если своих осей не задал.

    Возвращает {layout, card, layout_from, card_from}; `*_from` — откуда пришло
    значение ("type" | "page" | "site" | "default"), его показывает строка редактора.
    """
    from apps.promotions import promo_types

    cfg = cfg or {}
    source = _source(data)
    site_defaults = cfg.get("site_defaults") or {}
    if source == "promotions":
        settings = {}
        if data.get("type"):
            settings = promo_types.settings_for(cfg.get("promo_groups"), data["type"])
        card, card_from = settings.get("card", ""), "type"
        if not card:
            card, card_from = site_defaults.get("promo_card", ""), "site"
        if settings.get("layout"):
            layout = siteconfig.normalize_layout(settings["layout"], _DEFAULTS[source])
            return {"layout": layout, "card": card, "layout_from": "type", "card_from": card_from}
        # Тот же путь, что у страницы акций (`_promo_output_ctx`): ось вывода страницы
        # + легаси-ключ `promo_layout`, который включает ленту (LAY-7c). Иначе блок
        # типа без своих настроек выглядел бы не так, как страница этого типа.
        page = siteconfig.optional_page_layout(cfg, "promo_index_layout")
        page = siteconfig.apply_legacy_promo_slider(page, cfg.get("promo_layout"))
        if page:
            layout = siteconfig.normalize_layout(page, _DEFAULTS[source])
            return {"layout": layout, "card": card, "layout_from": "page", "card_from": card_from}
        layout = siteconfig.normalize_layout(None, _DEFAULTS[source])
        return {"layout": layout, "card": card, "layout_from": "default", "card_from": card_from}
    # у источника без форм карточки (плитки категорий) формы нет и наследовать нечего
    card = site_defaults.get("card_style", "") if siteconfig.LIST_SOURCES[source]["card"] else ""
    if source in _PAGE_LAYOUT_KEYS:
        # LB-3d: вид страницы-листинга источника — только если владелец его менял.
        # Нетронутая страница событий — это список в одну колонку (пресет `list`),
        # а блок — витрина: без выбора владельца он берёт вид секции главной.
        # Прайс-виды услуг (`preisliste*`, MEN-18) — не сетка: их блок не наследует.
        key = _PAGE_LAYOUT_KEYS[source]
        page = cfg.get(key)
        if (
            isinstance(page, dict)
            and page.get("preset") in siteconfig.LAYOUT_PRESETS
            and not siteconfig.layout_is_untouched(page, key)
        ):
            layout = siteconfig.normalize_layout(page, _DEFAULTS[source])
            return {"layout": layout, "card": card, "layout_from": "page", "card_from": "site"}
        layout = siteconfig.normalize_layout(None, _DEFAULTS[source])
        return {"layout": layout, "card": card, "layout_from": "default", "card_from": "site"}
    catalog = cfg.get("catalog_layout") if source == "products" else None
    # Прайс-виды каталога (`preisliste*`) — не сетка: блок их не наследует. Сетка
    # каталога — сетка ТОВАРОВ: плиткам категорий она не указ (LB-3d-2).
    if isinstance(catalog, dict) and catalog.get("preset") in siteconfig.LAYOUT_PRESETS:
        layout = siteconfig.normalize_layout(catalog, _DEFAULTS[source])
        return {"layout": layout, "card": card, "layout_from": "page", "card_from": "site"}
    layout = siteconfig.normalize_layout(None, _DEFAULTS[source])
    card_from = "site" if siteconfig.LIST_SOURCES[source]["card"] else "default"
    return {"layout": layout, "card": card, "layout_from": "default", "card_from": card_from}


def effective_view(cfg: dict, data: dict) -> dict:
    """Действующий вид блока: база по наследованию + свои оси блока поверх."""
    base = base_view(cfg, data)
    source = _source(data)
    layout = dict(base["layout"])
    if data.get("out") == "slider":
        layout["scroll"] = True
    elif data.get("out") == "grid":
        layout.pop("scroll", None)
        layout.pop("balance", None)
    for axis in ("cols", "rows", "speed"):
        if data.get(axis):
            layout[axis] = data[axis]
    card = data.get("card") or base["card"]
    # «Deal» — строка «фото · текст · кнопка» (DL-19 N3): уже трёх колонок она
    # схлопывается до буквы (стенд LB-1). Колонки, которые блок УНАСЛЕДОВАЛ, для неё
    # ужимаются до двух, на телефоне — до одной; явный выбор владельца не трогаем.
    if card == "deal" and not layout.get("scroll"):
        if not data.get("cols") and int(layout.get("cols") or 0) > _DEAL_MAX_COLS:
            layout["cols"] = _DEAL_MAX_COLS
            layout.pop("tablet", None)
        layout["mobile"] = 1
    layout = siteconfig.normalize_layout(layout, _DEFAULTS[source])
    mode = siteconfig.output_mode(layout)
    # Сколько показать: явный «Höchstens» → свои ряды блока × колонки (только сетка:
    # у ленты «ряды» — строки в слайде) → дефолт. Наследованные ряды выдачу не режут:
    # на странице типа они значат «строк в слайде», а не «сколько показывать».
    if data.get("limit"):
        limit = data["limit"]
    elif mode == "grid" and data.get("rows"):
        limit = layout["cols"] * data["rows"]
    else:
        limit = siteconfig.LIST_LIMIT_DEFAULT
    return {
        "layout": layout,
        "grid": siteconfig.grid_class_string(layout),
        "mode": mode,
        "card": card,
        "limit": max(1, min(int(limit), siteconfig.LIST_LIMIT_MAX)),
    }


def _upcoming(data: dict, limit: int):
    """LB-3: «Demnächst» — запланированные акции с будущим стартом, ближайшие первыми.

    Та же выборка, что у встроенной «Vorschau» страницы акций (DL-17.4): активные и
    будущие не смешиваются — у будущих нет ни счётчика, ни покупки, а фильтры «Endet
    …» и «−N %+» им чужие. Тип сужает выборку, как везде (`?gruppe=`).
    """
    from django.utils import timezone

    from apps.promotions import promo_types
    from apps.promotions.models import Promotion
    from apps.promotions.public_views import _attach_lowest_30d

    items = (
        Promotion.objects.filter(status="scheduled", starts_at__gt=timezone.now())
        .select_related("product")
        .order_by("starts_at")
    )
    items = promo_types.apply_type(items, data.get("type", ""))
    shown, total = _cut(items, limit)
    return _attach_lowest_30d(shown), total


def _promotions(data: dict, limit: int):
    """Акции: тот же фильтрующий слой, что у `/aktionen/` (PromoFacets, SF-2)."""
    from apps.promotions.facets import PromoFacets
    from apps.promotions.models import Promotion
    from apps.promotions.public_views import _attach_lowest_30d

    if data.get("phase") == "upcoming":
        return _upcoming(data, limit)
    provider = PromoFacets()
    items = (
        Promotion.objects.filter(status="active").select_related("product").order_by("-created_at")
    )
    items = provider.apply(
        items,
        {
            "gruppe": data.get("type", ""),
            "endet": data.get("endet", ""),
            "rabatt": data.get("rabatt") or 0,
        },
    )
    if data.get("sort"):
        # сортировки акций — in-memory (скидка живёт в свойствах, не в БД)
        items = provider.sort(items, data["sort"])
    shown, total = _cut(items, limit)
    # §11 PAngV: карточка со скидкой анонсирует снижение — низшая цена 30 дней рядом.
    # Блок PT-6 этого не делал, и строка на его карточках отсутствовала.
    return _attach_lowest_30d(shown), total


def _products(data: dict, limit: int):
    """Товары: тот же фильтрующий слой, что у каталога (CatalogFacets, UB2-1)."""
    from apps.catalog.facets import CatalogFacets
    from apps.catalog.models import Product
    from apps.promotions.price_layer import attach_promos

    provider = CatalogFacets()
    params = {}
    if data.get("category"):
        params["kategorie"] = data["category"]
    if data.get("collection"):
        params["kollektion"] = data["collection"]
    only = data.get("only")
    if only == "sale":
        params["sale"] = "1"
    elif only == "available":
        params["nur_verfuegbar"] = "1"
    # KAT-3: category — для SEO-адреса карточки (как секция главной и каталог).
    items = provider.apply(
        Product.objects.filter(is_active=True).select_related("category"), params
    )
    if only == "featured":
        items = items.filter(is_featured=True)
    sort = data.get("sort") or provider.default_sort
    if sort == "featured":
        # порядок секции товаров главной: избранные вперёд, затем новые
        items = items.order_by("-is_featured", "-created_at")
    else:
        items = provider.sort(items, sort)
    shown, total = _cut(items, limit)
    if shown:
        # рейтинг ★ и промо-цена — по одному bulk-запросу, как в каталоге
        from apps.reviews import services as review_services

        rating = review_services.bulk_summary("product", [p.pk for p in shown])
        for p in shown:
            row = rating.get(p.pk)
            p.review_avg = row["avg"] if row else None
            p.review_count = row["count"] if row else 0
        attach_promos(shown)
    return shown, total


def _page_sort(cfg: dict, source: str) -> str:
    """Порядок страницы-листинга источника по умолчанию (дефолт владельца, STU-15c).

    Пустая сортировка блока = то, что покажет его «Alle N →» без `?sort=`.
    """
    key = _PAGE_SORT_KEYS.get(source)
    value = (cfg or {}).get(key) if key else ""
    return value if key and value in siteconfig.listing_sort_keys(key) else ""


def _services(data: dict, limit: int, cfg: dict):
    """LB-3d: услуги — тот же фильтрующий слой, что у `/termin/` (ServiceFacets)."""
    from apps.booking.facets import ServiceFacets
    from apps.booking.models import Service

    provider = ServiceFacets()
    params = {
        "kollektion": data.get("collection", ""),
        "video": "1" if data.get("only") == "video" else "",
    }
    items = provider.apply(Service.objects.filter(is_active=True), params)
    items = provider.sort(items, data.get("sort") or _page_sort(cfg, "services"))
    return _cut(items, limit)


def _stays(data: dict, limit: int, cfg: dict):
    """LB-3d: номера — обзорные карточки «ab X € / Nacht», как главная и `/unterkunft/`
    без дат. Поиск по датам (наличие, цена диапазона) — дело страницы номера: у
    движка он стоит несколько запросов на номер."""
    from apps.stays.facets import StayDateFacets
    from apps.stays.models import StayUnit

    provider = StayDateFacets()
    items = provider.apply(
        StayUnit.objects.filter(is_active=True), {"kollektion": data.get("collection", "")}
    )
    items = provider.sort(items, data.get("sort") or _page_sort(cfg, "stays"))
    return _cut(items, limit)


def _events(data: dict, limit: int, cfg: dict):
    """LB-3d: события — та же выдача, что у `/veranstaltung/` (`events/listing.py`):
    будущие опубликованные, фильтр провайдера, сортировка, серия одной карточкой."""
    from apps.events import listing
    from apps.events.facets import EventFacets

    provider = EventFacets()
    items = listing.upcoming_events()
    if data.get("event_category"):
        items = provider.apply(items, {"cat": data["event_category"]})
    if data.get("only") == "soon":
        items = [e for e in items if listing.starts_within(e)]
    items = provider.sort(items, data.get("sort") or _page_sort(cfg, "events"))
    shown, total = _cut(listing.group_dates(items), limit)
    listing.annotate_countdown(shown)
    listing.attach_seat_counts(shown)
    return shown, total


def _tours(data: dict, limit: int, cfg: dict):
    """LB-3d-2: туры — как `/touren/`: опубликованные в порядке владельца. Цена «ab» и
    число дат — из предзагрузки будущих заездов: без неё карточка спрашивала бы БД
    несколько раз на тур."""
    from apps.events.models import Tour

    items = Tour.objects.filter(is_published=True).prefetch_related(Tour.upcoming_prefetch())
    if data.get("country"):
        items = items.filter(country=data["country"])
    return _cut(items, limit)


def _combos(data: dict, limit: int, cfg: dict):
    """LB-3d-2: наборы — как `/kombi/`: активные в порядке владельца; категория — живая
    и активная (как `?kategorie=`). Карточка — общая `_combo_card`, а не
    `sellable_card`: та печатала «0,00 €» у свободной сборки."""
    from apps.catalog.models import Category, Combo

    items = (
        Combo.objects.filter(is_active=True)
        .select_related("category")
        .order_by("sort_order", "created_at")
    )
    if data.get("category"):
        items = items.filter(
            category__in=Category.objects.filter(slug=data["category"], is_active=True)
        )
    return _cut(items, limit)


def _categories(data: dict, limit: int, cfg: dict):
    """LB-3d-2: категории — направления, как на `/sortiment/` (только с товарами в
    поддереве: плитка без товаров вела бы на пустую страницу), или активные
    подкатегории выбранной категории, как на её странице. Мягко удалённый или
    выключенный родитель — пустая выдача (блока нет)."""
    from django.db.models import Q

    from apps.catalog.models import Category

    slug = data.get("category")
    if slug:
        parent = Category.objects.filter(slug=slug, is_active=True).first()
        if parent is None:
            return [], 0
        items = (
            Category.objects.filter(parent=parent, is_active=True)
            .select_related("parent")
            .order_by("sort_order", "slug")
        )
        return _cut(items, limit)
    items = (
        Category.objects.filter(is_active=True, parent__isnull=True)
        .filter(Q(products__is_active=True) | Q(children__products__is_active=True))
        .distinct()
        .order_by("sort_order", "slug")
    )
    return _cut(items, limit)


def _reviews(data: dict, limit: int, cfg: dict):
    """LB-3d-3: проверенные отзывы о сущностях — опубликованные; фильтры вид · «ab N ★»
    · «только с текстом»; порядок — новые или лучшие (оценка, затем новизна)."""
    from apps.reviews.models import Review

    items = Review.objects.filter(is_published=True)
    if data.get("entity"):
        items = items.filter(entity_kind=data["entity"])
    if data.get("stars"):
        items = items.filter(rating__gte=data["stars"])
    if data.get("only") == "text":
        items = items.exclude(comment="")
    if data.get("sort") == "best":
        items = items.order_by("-rating", "-created_at")
    else:
        items = items.order_by("-created_at")
    return _cut(items, limit)


def _blog(data: dict, limit: int, cfg: dict):
    """LB-3d-3: статьи блога — опубликованные, новые первыми; без даты — в конце
    (Postgres ставит NULL первыми при DESC, а «без даты» — это не «самое новое»)."""
    from django.db.models import F

    from apps.events.models import BlogPost

    items = BlogPost.objects.filter(is_published=True).order_by(
        F("published_at").desc(nulls_last=True), "-created_at"
    )
    return _cut(items, limit)


# LB-3d-3: сущность отзыва → (модуль, загрузчик, «живая ли», адрес, имя). Один запрос
# на вид; ссылка — только у живой сущности включённого модуля.
def _review_targets():
    from apps.booking.models import Service
    from apps.catalog.models import Combo, Product
    from apps.events.models import Event
    from apps.stays.models import StayUnit

    return {
        "product": (
            "catalog",
            lambda ids: Product.objects.filter(pk__in=ids).select_related("category"),
            lambda o: o.is_active,
            lambda o: o.get_absolute_url(),
            str,
        ),
        "service": (
            "booking",
            lambda ids: Service.objects.filter(pk__in=ids),
            lambda o: o.is_active,
            lambda o: reverse("storefront-service-detail", args=[o.pk]),
            lambda o: o.name_localized(),
        ),
        "stay": (
            "stays",
            lambda ids: StayUnit.objects.filter(pk__in=ids),
            lambda o: o.is_active,
            lambda o: reverse("storefront-unterkunft-unit", args=[o.pk]),
            lambda o: o.name_localized(),
        ),
        "event": (
            "events",
            lambda ids: Event.objects.filter(pk__in=ids),
            lambda o: o.status == Event.STATUS_PUBLISHED,
            lambda o: reverse("storefront-event", args=[o.pk]),
            lambda o: o.title_text,
        ),
        "combo": (
            "catalog",
            lambda ids: Combo.objects.filter(pk__in=ids),
            lambda o: o.is_active,
            lambda o: reverse("storefront-combo", args=[o.pk]),
            lambda o: o.name_localized(),
        ),
    }


def _attach_review_entities(reviews, tenant) -> None:
    """Имя и адрес отзываемой сущности на каждый отзыв: `entity_name`, `entity_url`
    ("" — без ссылки: сущность снята с витрины, модуль выключен или нет тенанта).
    Удалённая сущность — без имени; сам отзыв остаётся (он о бизнесе)."""
    by_kind: dict = {}
    for review in reviews:
        review.entity_name, review.entity_url = "", ""
        by_kind.setdefault(review.entity_kind, []).append(review)
    targets = _review_targets()
    for kind, rows in by_kind.items():
        spec = targets.get(kind)
        if spec is None:
            continue
        module, load, live, url, name = spec
        found = {o.pk: o for o in load([r.entity_id for r in rows])}
        linked = bool(tenant is not None and tenant.is_module_active(module))
        for review in rows:
            obj = found.get(review.entity_id)
            if obj is None:
                continue
            review.entity_name = name(obj)
            if linked and live(obj):
                review.entity_url = url(obj)


def _cut(items, limit: int):
    """Первые `limit` и сколько всего; COUNT — только когда показаны не все."""
    if isinstance(items, list):
        return items[:limit], len(items)
    shown = list(items[: limit + 1])
    if len(shown) <= limit:
        return shown, len(shown)
    return shown[:limit], items.count()


def _all_url(data: dict) -> str:
    """Где виден ВЕСЬ список с тем же фильтром (решение N-4: тип → страница типа)."""
    source = _source(data)
    params = {}
    if source == "promotions" and data.get("phase") == "upcoming":
        return ""  # LB-3: страницы «будущих акций» нет — и ссылке вести некуда
    if source == "promotions":
        for key, param in (("type", "gruppe"), ("endet", "endet"), ("rabatt", "rabatt")):
            if data.get(key):
                params[param] = data[key]
        if data.get("sort"):
            params["sort"] = data["sort"]
        base = reverse("storefront-aktionen")
    elif source in _LISTING_URLS:
        # LB-3d: листинг источника с ТЕМИ ЖЕ параметрами, что понимает его тулбар.
        # Без явной сортировки страница сама применит дефолт владельца.
        base = reverse(_LISTING_URLS[source])
        if data.get("collection"):
            params["kollektion"] = data["collection"]
        if data.get("event_category"):
            params["cat"] = data["event_category"]
        if data.get("only") == "video":
            params["video"] = "1"
        if data.get("sort"):
            params["sort"] = data["sort"]
    elif source == "tours":
        # LB-3d-2: туры одной страны — её секция на `/touren/` (якорь той же формы,
        # что строит `group_tours_by_country`; без разбивки по странам — верх страницы)
        from django.utils.text import slugify

        base = reverse("storefront-tours")
        if data.get("country"):
            return f"{base}#land-{slugify(data['country']) or 'weitere'}"
    elif source == "combos":
        base = reverse("storefront-combos")
        if data.get("category"):
            params["kategorie"] = data["category"]
    elif source == "categories":
        base = (
            reverse("storefront-category", args=[data["category"]])
            if data.get("category")
            else reverse("storefront-products")
        )
    elif source == "reviews":
        return ""  # LB-3d-3: страницы проверенных отзывов нет — ссылке вести некуда
    elif source == "blog":
        base = reverse("storefront-blog")
    else:
        base = (
            reverse("storefront-category", args=[data["category"]])
            if data.get("category")
            else reverse("storefront-products")
        )
        if data.get("collection"):
            params["kollektion"] = data["collection"]
        only = data.get("only")
        if only == "sale":
            params["sale"] = "1"
        elif only == "available":
            params["nur_verfuegbar"] = "1"
        # «featured» у каталога своего параметра нет; «newest» — его порядок по умолчанию
        if data.get("sort") in ("price_asc", "price_desc"):
            params["sort"] = data["sort"]
    return base + ("?" + urlencode(params) if params else "")


def _collection_label(slug: str) -> str:
    """Имя подборки на языке витрины; пусто — подборки нет (или она выключена)."""
    from django.utils.translation import get_language

    from apps.collections.models import Collection

    found = Collection.objects.filter(slug=slug, is_active=True).first()
    return found.name_localized(get_language()) if found else ""


def _label(data: dict, items, tenant=None) -> str:
    """Заголовок: свой у блока, иначе по выборке (тип, фильтр, категория)."""
    if data.get("title"):
        return data["title"]
    source = _source(data)
    if source == "tours":
        # LB-3d-2: страна на языке витрины (группа /touren/ — по базовому значению)
        if data.get("country"):
            for tour in items:
                if tour.country == data["country"]:
                    return tour.country_text or data["country"]
            return data["country"]
        return source_label(source, tenant)
    if source in ("reviews", "blog"):
        return source_label(source, tenant)
    if source in ("combos", "categories"):
        # направление наборов / родитель подкатегорий — на языке витрины
        if data.get("category") and items:
            owner = items[0].category if source == "combos" else items[0].parent
            if owner is not None and owner.slug == data["category"]:
                return str(owner)
        return source_label(source, tenant)
    if source in _LISTING_URLS:
        # LB-3d: подборка или тема говорят больше общего названия источника
        if data.get("collection"):
            named = _collection_label(data["collection"])
            if named:
                return named
        if data.get("event_category"):
            from apps.events import taxonomy

            return taxonomy.category_label(data["event_category"]) or data["event_category"]
        if data.get("only") == "video":
            return _("Video-Beratung")
        if data.get("only") == "soon":
            return _("In den nächsten 14 Tagen")
        return str(siteconfig.LIST_SOURCES[source]["label"])
    if source == "promotions":
        soon = _("Demnächst")
        if data.get("type"):
            from apps.promotions import promo_types

            own = {p.group: p.group_localized for p in items if p.group}
            label = promo_types.label_for(data["type"], own)
            # gettext — вне f-строки: xgettext выражения f-строк не извлекает (I18N-13)
            return f"{label} · {soon}" if data.get("phase") == "upcoming" else label
        if data.get("phase") == "upcoming":
            return soon
        if data.get("endet") == "heute":
            return _("Endet heute")
        if data.get("endet") == "woche":
            return _("Endet diese Woche")
        return _("Aktionen")
    if data.get("category") and items:
        cat = getattr(items[0], "category", None)
        if cat is not None and getattr(cat, "slug", "") == data["category"]:
            return str(cat)
        parent = getattr(cat, "parent", None) if cat is not None else None
        if parent is not None and getattr(parent, "slug", "") == data["category"]:
            return str(parent)
    if data.get("collection"):
        named = _collection_label(data["collection"])
        if named:
            return named
    only = data.get("only")
    if only == "featured" or data.get("sort") == "featured":
        return _("Empfehlungen")
    if only == "sale":
        return _("Reduziert")
    if only == "available":
        return _("Sofort verfügbar")
    if data.get("sort") == "newest":
        return _("Neu im Sortiment")
    return _("Produkte")


# LB-3d: выборка источника — одно место на источник (раньше всё, что не «products»,
# молча уходило в ветку акций).
_FETCHERS = {
    "promotions": lambda data, limit, cfg: _promotions(data, limit),
    "products": lambda data, limit, cfg: _products(data, limit),
    "services": _services,
    "stays": _stays,
    "events": _events,
    "tours": _tours,
    "combos": _combos,
    "categories": _categories,
    "reviews": _reviews,
    "blog": _blog,
}


def _tile_aspect(cfg: dict) -> str:
    """LB-3d-2: форма плитки категории — как у секции «Kategorien» главной."""
    return siteconfig.CATEGORY_TILE_ASPECTS.get(
        siteconfig.section_style(cfg, "categories"), "aspect-[4/3]"
    )


def resolve(cfg: dict, data: dict, tenant=None) -> dict:
    """Всё, что нужно разметке блока: карточки + вид + заголовок + «Alle N →».

    `tenant` нужен подписям по типу бизнеса («Menü-Pakete» у гастро); без него —
    подпись реестра."""
    data = data or {}
    source = _source(data)
    view = effective_view(cfg, data)
    items, total = _FETCHERS[source](data, view["limit"], cfg)
    if source == "reviews":
        _attach_review_entities(items, tenant)
    # LB-3: «Demnächst» — карточки-превью («ab <дата>», без счётчика и покупки) и без
    # «Alle N →»: страницы будущих акций нет.
    preview = source == "promotions" and data.get("phase") == "upcoming"
    url = _all_url(data)
    return {
        "source": source,
        "items": items,
        "total": total,
        # «Alle N →» — только когда показаны не все и есть КУДА вести (у отзывов и
        # «Demnächst» страницы всего списка нет)
        "more": total > len(items) and not preview and bool(url),
        "preview": preview,
        "url": url,
        "label": _label(data, items, tenant),
        "intro": data.get("intro", ""),
        "aspect": _tile_aspect(cfg) if source == "categories" else "",
        "type": data.get("type", "") if source == "promotions" else "",
        # у блока ОДНОГО типа метка типа на карточке — шум (все одинаковые); у
        # смешанной выдачи она говорит, откуда акция (как в результатах, N-2)
        "in_group": bool(data.get("type")),
        **{k: view[k] for k in ("layout", "grid", "mode", "card")},
    }


def resolve_for(request, cfg: dict, data: dict) -> dict:
    """`resolve` с кэшем на запрос: одна выборка на блок, сколько бы раз её ни спросили.

    LB-3: чипам Sprungleiste страницы акций нужны подписи и счётчики блоков, а сами
    блоки потом рисует тег `list_block`. Конфиг у них один (черновик при `?preview=1`,
    та же локализация), поэтому ключом служат данные блока. Без `request` — без кэша.
    """
    import json

    data = data or {}
    try:
        memo = request._list_block_memo
    except AttributeError:
        memo = {}
        try:
            request._list_block_memo = memo
        except AttributeError:  # чужой объект без атрибутов — считаем без кэша
            return resolve(cfg, data, getattr(request, "tenant", None))
    key = json.dumps(data, sort_keys=True, default=str)
    if key not in memo:
        memo[key] = resolve(cfg, data, getattr(request, "tenant", None))
    return memo[key]


def _is_list(block) -> bool:
    return (
        isinstance(block, dict)
        and block.get("enabled", True)
        and siteconfig.cblock_type(block.get("key")) == "list"
        and isinstance(block.get("data"), dict)
    )


def overview_blocks(cfg: dict) -> dict:
    """LB-3: блоки «Liste» страницы акций и что из встроенного обзора они заменяют.

    План §12.2/§12.8. Режим блоков включает ВКЛЮЧЁННЫЙ блок с акциями (над списком
    или под ним); блок товаров его не включает. Встроенное гасит только РАВНОЗНАЧНЫЙ
    блок — показывающий то же множество акций (лимит и сортировка не в счёт):

    * `types` — рубрики, чья секция уходит из основного списка: блок «тип X» без
      сужающих фильтров. Встроенные типы (`sys:*`) ничего не гасят — они пересекают
      рубрики, и секций по ним нет;
    * `ending` — блоки «Endet …» без типа и без «−N %»: кандидаты погасить полосу
      «Ending soon» (гасят, только если им есть что показать — решает вьюха по выдаче);
    * `ends` — их значения (`heute`/`woche`): при группировке «по времени» акции этих
      сроков уходят из остатка — по фильтру, а не по названию бакета;
    * `upcoming` — есть блок «Demnächst» без типа: «Vorschau» не нужна.
    """
    from apps.promotions import promo_types

    cfg = cfg or {}
    rows = (cfg.get("page_blocks") or {}).get("promos") or []
    above, below = siteconfig.split_at_main(rows)
    above = [b for b in above if _is_list(b)]
    below = [b for b in below if _is_list(b)]
    types: set = set()
    ending: list = []
    upcoming = False
    for block in above + below:
        data = block["data"]
        if _source(data) != "promotions":
            continue
        kind = str(data.get("type") or "")
        if data.get("phase") == "upcoming":
            upcoming = upcoming or not kind
        elif kind:
            narrowed = data.get("endet") or data.get("rabatt")
            if not narrowed and not promo_types.is_builtin(kind):
                types.add(kind)
        elif data.get("endet") and not data.get("rabatt"):
            # «Endet … · ab −50 %» — уже выборка, чем «Ending soon» и срок целиком:
            # такой блок — витрина поверх, а не замена (ревью LB-3)
            ending.append(block)
    active = any(_source(b["data"]) == "promotions" for b in above + below)
    return {
        "active": active,
        "above": above,
        "below": below,
        "types": types,
        "ending": ending,
        "ends": {b["data"]["endet"] for b in ending},
        "upcoming": upcoming,
    }


_FROM_LABELS = {
    "type": gettext_lazy("wie der Typ"),
    "page": gettext_lazy("wie die Seite"),
    "site": gettext_lazy("wie die Website"),
    "default": gettext_lazy("Standard"),
}


def view_hint(cfg: dict, data: dict) -> dict:
    """Всё, что нужно строке редактора: подписи «пустых» пунктов вида (ОТКУДА придёт
    значение и какое) и наборы пунктов с отметкой источника.

    Без подписи «пусто» читалось бы как «ничего», хотя блок показывает вид своего
    типа или страницы — владелец не видел бы, что именно он наследует.
    """
    from apps.promotions.facets import DISCOUNT_PRESETS

    base = base_view(cfg, data)
    layout = base["layout"]
    source = _source(data)
    kind = siteconfig.LIST_SOURCES[source]["card"]
    mode_key = siteconfig.output_mode(layout)
    return {
        "layout_from": str(_FROM_LABELS[base["layout_from"]]),
        "card_from": str(_FROM_LABELS[base["card_from"]]),
        "mode_key": mode_key,
        "mode": _("Slider") if mode_key == "slider" else _("Raster"),
        "cols": layout["cols"],
        "rows": layout.get("rows") or "",
        "card": str(card_forms.label_for(base["card"], kind) or _("Standard")),
        "limit": siteconfig.LIST_LIMIT_DEFAULT,
        "discounts": DISCOUNT_PRESETS,
        "sorts": sort_options(cfg),
        "cards": card_options(),
        "source_label": str(siteconfig.LIST_SOURCES[source]["label"]),
        # LB-3d-2: строки, которым у источника нечего предложить, скрыты (STU-9):
        # сортировки нет у туров/наборов/категорий, формы карточки — у категорий
        "sort_sources": " ".join(
            s for s in siteconfig.LIST_SOURCES if siteconfig.list_sort_keys(s)
        ),
        "card_sources": " ".join(s for s, spec in siteconfig.LIST_SOURCES.items() if spec["card"]),
    }


# LB-3d-3: источники без провайдера фасетов, но со своим порядком («пусто» — первый).
_OWN_SORTS = {
    "reviews": (("", gettext_lazy("Neueste zuerst")), ("best", gettext_lazy("Beste zuerst"))),
}


def sort_options(cfg: dict | None = None) -> list[tuple[str, str, str]]:
    """[(ключ, подпись, источники)] сортировок — подписи у провайдеров фасетов, те же,
    что видит посетитель на витрине. Сортировка провайдера по умолчанию = пустой ключ.

    LB-3d: строки сводятся по паре (ключ, подпись), а не по ключу: пустой пункт значит
    у каждого источника СВОЁ («новые» у акций, «по имени» у услуг, «по дате» у событий),
    и общая подпись соврала бы. Если у страницы источника есть порядок владельца,
    пустой пункт так и подписан — «wie die Seite: …», как пустые оси вида.
    """
    from apps.core.facets import provider_for

    merged: dict[tuple[str, str], list] = {}
    for source, spec in siteconfig.LIST_SOURCES.items():
        provider = provider_for(spec["facets"])
        options = list(_OWN_SORTS.get(source) or provider.sort_options())
        default = "" if source in _OWN_SORTS else provider.default_sort
        if source == "products":
            options.insert(1, ("featured", _("Empfohlene zuerst")))
        labels = {key: str(label) for key, label in options}
        page = _page_sort(cfg, source) if cfg else ""
        for key, label in options:
            key = "" if key == default else key
            label = str(label)
            if key == "" and page:
                label = f"{_FROM_LABELS['page']}: {labels.get(page, page)}"
            merged.setdefault((key, label), []).append(source)
    return [(key, label, " ".join(srcs)) for (key, label), srcs in merged.items()]


def card_options() -> list[tuple[str, str, str]]:
    """[(ключ, подпись, источники)] форм карточки — реестр `core.card_forms` (DL-19)."""
    out = []
    for key, label, _hint, kinds in card_forms.CARD_FORMS:
        if not key:
            continue
        srcs = [s for s, spec in siteconfig.LIST_SOURCES.items() if spec["card"] in kinds]
        if srcs:
            out.append((key, str(label), " ".join(srcs)))
    return out


# ─────────────────── LB-1b: пилюля охвата «Den ganzen Typ» ───────────────────
#
# План — `docs/lb-list-blocks-plan-2026-10-02.md` §10. Хранение не новое: тот же
# `promo_groups[тип].layout/card`, что пишут экран «Aktionstypen» и страница типа.

_VIEW_AXES = ("out", "cols", "rows", "speed", "card")
_LAYOUT_AXES = ("out", "cols", "rows", "speed")


def _list_blocks_of(cfg: dict) -> list[dict]:
    """Блоки «Liste» конфига в порядке обхода: главная, затем страницы."""
    found: list = []
    sections = cfg.get("sections")
    if isinstance(sections, list):
        found.extend(sections)
    pages = cfg.get("page_blocks")
    if isinstance(pages, dict):
        for rows in pages.values():
            if isinstance(rows, list):
                found.extend(rows)
    return [
        item
        for item in found
        if isinstance(item, dict)
        and siteconfig.cblock_type(item.get("key")) == "list"
        and isinstance(item.get("data"), dict)
    ]


def _axis_int(raw, low: int, high: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    return value if low <= value <= high else 0


def _type_layout(cfg: dict, data: dict) -> dict:
    """Раскладка типа из осей блока; {} — у типа своей раскладки нет.

    Слой раскладки у типа «всё или ничего»: `base_view` берёт раскладку типа ЦЕЛИКОМ
    и страницу уже не читает. Поэтому основа — действующая раскладка СТРАНИЦЫ, а оси
    блока ложатся поверх: пустое «Spalten» с подписью «wie die Seite: 4» обязано дать
    4, а не дефолт нормализации, и «Raster» поверх ленты страницы — сетку.
    """
    if not any(data.get(axis) for axis in _LAYOUT_AXES):
        return {}
    layout = dict(base_view(cfg, {"source": "promotions"})["layout"])
    if data.get("out") == "slider":
        layout["scroll"] = True
    elif data.get("out") == "grid":
        layout.pop("scroll", None)
        layout.pop("balance", None)
    cols = _axis_int(data.get("cols"), 1, 6)
    if cols:
        # как экран «Aktionstypen» (`promo_type_save`) — одно хранение, одна форма
        layout["preset"] = f"cols{cols}"
        layout["cols"] = cols
    for axis, low, high in (("rows", 1, 6), ("speed", 3, 15)):
        value = _axis_int(data.get(axis), low, high)
        if value:
            layout[axis] = value
    return layout


def apply_type_scope(cfg: dict) -> None:
    """LB-1b: блоки в режиме «Den ganzen Typ» отдают свой вид ТИПУ акции.

    Одна функция для Save билдера и для живого черновика — превью показывает ровно то,
    что сохранится. Для блока `list` с `scope="type"`, источником «Aktionen» и типом:
    оси вида уходят в `promo_groups[тип]` (пустые — тип снова наследует страницу), а у
    блока очищаются — он следует за типом, как все блоки этого типа. Шаблон страницы
    типа (`style`) и чужие типы не трогаются. `scope` — служебное поле формы и в
    конфиге не остаётся ни у одного блока. Два блока одного типа в этом режиме —
    побеждает последний по порядку обхода (главная, затем страницы).
    """
    if not isinstance(cfg, dict):
        return
    from apps.promotions import promo_types

    types = None
    for item in _list_blocks_of(cfg):
        data = item["data"]
        if data.pop("scope", None) != "type":
            continue
        kind = str(data.get("type") or "").strip()
        if _source(data) != "promotions" or not kind:
            continue
        if types is None:
            raw = cfg.get("promo_groups")
            types = dict(raw) if isinstance(raw, dict) else {}
        entry = dict(promo_types.settings_for(types, kind))
        layout = _type_layout(cfg, data)
        if layout:
            entry["layout"] = layout
        else:
            entry.pop("layout", None)
        card = str(data.get("card") or "").strip()
        if card and card in card_forms.keys_for(card_forms.PROMO):
            entry["card"] = card
        else:
            entry.pop("card", None)
        types[kind] = entry
        for axis in _VIEW_AXES:
            data.pop(axis, None)
    if types is not None:
        cfg["promo_groups"] = types


def type_views(cfg: dict, keys=()) -> dict:
    """LB-1b: карта для пилюли охвата в строке редактора (один JSON на страницу).

    `types` — что покажут контролы вида в режиме «Den ganzen Typ» (значения самого
    типа, пусто = тип наследует); `page` — подписи пустых пунктов в этом режиме: тип
    без своей оси берёт её у страницы акций.
    """
    from apps.promotions import promo_types

    cfg = cfg or {}
    per_type = cfg.get("promo_groups") if isinstance(cfg.get("promo_groups"), dict) else {}
    names = [*keys, *per_type, *(b["data"].get("type") for b in _list_blocks_of(cfg))]
    types: dict = {}
    for key in dict.fromkeys(str(k or "").strip() for k in names):
        if not key:
            continue
        settings = promo_types.settings_for(per_type, key)
        layout = settings.get("layout") or {}
        types[key] = {
            "out": ("slider" if layout.get("scroll") else "grid") if layout else "",
            "cols": str(layout.get("cols") or "") if layout else "",
            "rows": str(layout.get("rows") or ""),
            "speed": str(layout.get("speed") or ""),
            "card": settings.get("card", ""),
        }
    page = view_hint(cfg, {"source": "promotions"})
    return {
        "types": types,
        "page": {
            "out": f"{page['layout_from']}: {page['mode']}",
            "cols": f"{page['layout_from']}: {page['cols']}",
            "rows": (
                f"{page['layout_from']}: {page['rows']}" if page["rows"] else _("automatisch")
            ),
            "card": f"{page['card_from']}: {page['card']}",
            "mode": page["mode_key"],
        },
    }


def editor_options(
    data: dict,
    live_types=None,
    categories=None,
    sources=None,
    collections=None,
    themes=None,
    countries=None,
    review_kinds=None,
) -> dict:
    """Пункты селекторов строки, которых нет в живых списках (класс W0).

    Селектор типа строится из ЖИВЫХ типов, категорий — из активных. Без своего пункта
    значение блока не было бы выбрано, браузер отправил бы первый пункт («Alle»), и
    Save молча превратил бы блок «Räumung» в блок «все акции». Плюс подпись типа для
    пилюли охвата.
    """
    from apps.promotions import promo_types

    data = data if isinstance(data, dict) else {}
    out: dict = {}
    kind = str(data.get("type") or "")
    if kind:
        label = dict(live_types or []).get(kind)
        if label is None:
            # gettext — вне f-строки: xgettext выражения f-строк не извлекает (I18N-13)
            empty = _("derzeit leer")
            label = f"{promo_types.label_for(kind)} ({empty})"
            out["orphan_type"] = (kind, label)
        out["type_label"] = label
    category = str(data.get("category") or "")
    if category and category not in {slug for slug, _label in (categories or [])}:
        gone = _("nicht verfügbar")
        out["orphan_category"] = (category, f"{category} ({gone})")
    # LB-3d: источник выключенного модуля, удалённая подборка, тема без событий —
    # значение блока остаётся в селекторе выбранным (иначе Save молча сменил бы его
    # на первый пункт: блок номеров стал бы блоком акций).
    source = _source(data)
    if sources is not None and source not in {key for key, _label in sources}:
        off = _("derzeit aus")
        label = siteconfig.LIST_SOURCES[source]["label"]
        out["orphan_source"] = (source, f"{label} ({off})")
    collection = str(data.get("collection") or "")
    if collection and collection not in {row[0] for row in (collections or [])}:
        gone = _("nicht verfügbar")
        out["orphan_collection"] = (collection, f"{collection} ({gone})", source)
    theme = str(data.get("event_category") or "")
    if theme and theme not in {key for key, _label in (themes or [])}:
        empty = _("derzeit leer")
        from apps.events import taxonomy

        named = taxonomy.category_label(theme) or theme
        out["orphan_theme"] = (theme, f"{named} ({empty})")
    # LB-3d-2: страна, по которой больше нет опубликованных туров
    country = str(data.get("country") or "")
    if country and country not in {key for key, _label in (countries or [])}:
        empty = _("derzeit leer")
        out["orphan_country"] = (country, f"{country} ({empty})")
    # LB-3d-3: отзывы о сущностях выключенного модуля
    entity = str(data.get("entity") or "")
    if entity and entity not in {key for key, _label in (review_kinds or [])}:
        off = _("derzeit aus")
        out["orphan_entity"] = (entity, f"{review_kind_label(entity)} ({off})")
    return out


# LB-3d-3: подписи видов отзываемых сущностей (как источники блока) и их модули.
_REVIEW_KIND_SOURCES = {
    "product": "products",
    "service": "services",
    "stay": "stays",
    "event": "events",
    "combo": "combos",
}


def review_kind_label(kind: str, tenant=None) -> str:
    """Подпись вида сущности отзыва — подпись одноимённого источника блока."""
    source = _REVIEW_KIND_SOURCES.get(kind)
    return source_label(source, tenant) if source else kind


def review_kinds(tenant) -> list[tuple[str, str]]:
    """[(вид, подпись)] видов сущностей отзыва с включённым модулем — пункты фильтра."""
    out = []
    for kind, source in _REVIEW_KIND_SOURCES.items():
        module = siteconfig.LIST_SOURCES[source]["module"]
        try:
            active = bool(tenant is not None and tenant.is_module_active(module))
        except Exception:  # noqa: BLE001
            active = False
        if active:
            out.append((kind, review_kind_label(kind, tenant)))
    return out
