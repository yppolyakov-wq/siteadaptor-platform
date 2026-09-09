"""STU-1: единый реестр «тип страницы витрины → её настройки» для Studio.

Зачем. До этого редактор показывал ОДИН набор контролов на все страницы: настройки
страницы акций лежали в области «Тема» (видны везде, кроме своей страницы), раскладки
листингов писали два разных экрана, а объектный уровень (шаблон конкретной категории,
форма карточки конкретного товара) в Studio отсутствовал вовсе. Реестр — единственный
источник ответа на два вопроса:

1. **На какой странице стоит канва** — `resolve_page(path, query)` разбирает путь
   ШТАТНЫМ резолвером Django по `config.urls_tenant` (а не эвристикой по подстрокам):
   `url_name` → тип страницы, аргументы → объект (pk/slug), плюс хост блоков
   `page_blocks`. Незнакомый путь → тип `other`, панель показывает только общий уровень.
2. **Какие настройки к этой странице относятся** и на каком УРОВНЕ каждая живёт
   (решение владельца, вариант A: охват выбирается у каждой настройки отдельно):

   * `site`   — «для всех»: ключ в `site_config` (напр. `site_defaults.card_style`);
   * `object` — «только здесь»: поле самой сущности (`Product.card_style`,
     `Category.page_style`, `Promotion.card_style`) или запись
     `site_config["promo_groups"][<группа>]` у группы акций.

   Настройка, у которой `object_kind` пуст, объектного уровня НЕ имеет — пилюля охвата
   у неё не рисуется (честно: подменять её «только здесь» нечем).

Реестр ничего не сохраняет и ничего не рендерит: он только описывает. Запись значений
остаётся за формой Studio и точечными приёмниками — чтобы этот модуль можно было
свободно импортировать откуда угодно (в т.ч. из тестов) без побочных эффектов.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlsplit

from django.urls import Resolver404, resolve
from django.utils.translation import gettext_lazy as _

# ─────────────────────────── настройки ───────────────────────────

#: Виды сущностей, у которых есть СВОЯ настройка, побеждающая общую.
OBJECT_PRODUCT = "product"
OBJECT_CATEGORY = "category"
OBJECT_PROMOTION = "promotion"
OBJECT_PROMO_GROUP = "promo_group"

#: Параметр адреса, которым страница группы акций отличается от обзора.
GROUP_PARAM = "gruppe"

#: Параметры адреса, ЗАДАЮЩИЕ страницу (а не фильтр посетителя). STU-7: канва обязана
#: удерживать их вместе с путём — иначе перерисовка живого черновика уводит владельца
#: с настраиваемой страницы на обзор, а `?page=` не может её адресовать вовсе.
#: Реестр — единственный источник списка (клиент получает его же, см. site_home.html).
PAGE_QUERY_KEYS: tuple[str, ...] = (GROUP_PARAM,)


@dataclass(frozen=True)
class Setting:
    """Одна настройка панели «Эта страница».

    `form_field` — имя поля в форме Studio (уровень «для всех»); `site_key` — путь в
    нормализованном `site_config` (кортеж: `("site_defaults", "card_style")` или
    `("promo_page_style",)`). `object_kind`/`object_field` заполнены только у настроек,
    у которых есть объектный уровень.
    """

    code: str
    label: str
    form_field: str
    site_key: tuple[str, ...]
    object_kind: str = ""
    object_field: str = ""
    #: STU-12j (F9): у настройки может быть РАЗНЫЙ объектный уровень на разных типах
    #: страниц — форма карточки на странице товара пишет товар, а на странице
    #: категории категорию. Ключ — код типа страницы, значение — (вид, поле).
    object_by_type: tuple[tuple[str, tuple[str, str]], ...] = ()

    @property
    def has_object_scope(self) -> bool:
        return bool((self.object_kind and self.object_field) or self.object_by_type)

    def object_for(self, page_code: str) -> tuple[str, str]:
        """(вид объекта, поле) для этого типа страницы; ("", "") — объекта нет.

        Пустой `page_code` (старый клиент, прямой вызов сервиса) — прежний,
        единственный вид настройки: обратная совместимость важнее строгости.
        """
        if self.object_by_type and page_code:
            # карта ИСЧЕРПЫВАЮЩАЯ: тип, которого в ней нет, объектного уровня не имеет
            # (на главной у формы карточки объекта нет — только дефолт сайта).
            for code, pair in self.object_by_type:
                if code == page_code:
                    return pair
            return ("", "")
        if self.object_kind and self.object_field:
            return (self.object_kind, self.object_field)
        return ("", "")


def _s(*args, **kw) -> Setting:
    return Setting(*args, **kw)


#: Реестр настроек. Ключ = стабильный код, на который ссылаются типы страниц.
SETTINGS: dict[str, Setting] = {
    s.code: s
    for s in (
        # ── главная
        _s("home_sections", _("Abschnitte"), "order_*", ("sections",)),
        _s("home_hero", _("Banner"), "hero_style", ("hero_style",)),
        # ── каталог: корень и категория
        _s(
            "catalog_page_style",
            _("Vorlage der Seite"),
            "catalog_page_style",
            ("catalog_page_style",),
        ),
        _s("catalog_layout", _("Raster"), "catalog_preset", ("catalog_layout",)),
        _s("catalog_sort", _("Sortierung"), "catalog_sort", ("catalog_sort",)),
        _s("catalog_filters", _("Filter"), "catalog_show_filters", ("catalog_show_filters",)),
        _s(
            "catalog_subcats",
            _("Unterkategorien zuerst"),
            "catalog_subcats_first",
            ("catalog_subcats_first",),
        ),
        _s(
            "category_page_style",
            _("Vorlage der Seite"),
            "sd_category_page_style",
            ("site_defaults", "category_page_style"),
            OBJECT_CATEGORY,
            "page_style",
        ),
        # ── товар
        _s(
            "product_detail_layout",
            _("Aufbau der Detailseite"),
            "pd_layout",
            ("product_detail", "layout"),
        ),
        _s(
            "product_detail_sections",
            _("Abschnitte"),
            "pd_visible_*",
            ("product_detail", "hidden"),
        ),
        # STU-9: `site_defaults.card_style` рисует карточки товаров И карточки
        # услуг/номеров/событий (`_sellable_card`) — то есть действует на КАЖДОЙ
        # странице витрины. Пока настройка стояла только у типов category/product,
        # у отеля и салона (ни одной категории и ни одного товара) она была
        # недостижима из интерфейса вообще, продолжая менять вид их карточек.
        _s(
            "product_card_form",
            _("Kartenform"),
            "sd_card_style",
            ("site_defaults", "card_style"),
            OBJECT_PRODUCT,
            "card_style",
            # STU-12j: на странице категории «только здесь» пишет КАТЕГОРИЮ —
            # до этого пилюля обещала выбор, которого не существовало.
            object_by_type=(
                ("product", (OBJECT_PRODUCT, "card_style")),
                ("category", (OBJECT_CATEGORY, "card_style")),
            ),
        ),
        # ── акции
        _s("promo_page_style", _("Vorlage der Seite"), "promo_page_style", ("promo_page_style",)),
        _s("promo_layout", _("Darstellung der Gruppen"), "promo_layout", ("promo_layout",)),
        _s("promo_grouping", _("Gruppierung"), "promo_grouping", ("promo_grouping",)),
        _s(
            "promo_card_form",
            _("Kartenform"),
            "sd_promo_card",
            ("site_defaults", "promo_card"),
            OBJECT_PROMOTION,
            "card_style",
        ),
        _s(
            "promo_group_style",
            _("Vorlage der Gruppenseite"),
            "sd_promo_group_style",
            ("site_defaults", "promo_group_style"),
            OBJECT_PROMO_GROUP,
            "style",
        ),
        # STU-15a: у страницы одной акции шаблона не было вовсе — при том что у
        # товара, категории и группы акций он есть. «Только здесь» пишет саму
        # акцию: длинный рассказ у одной и короткий флаер у другой — норма.
        _s(
            "promo_detail_style",
            _("Vorlage der Seite"),
            "sd_promo_detail_style",
            ("site_defaults", "promo_detail_style"),
            OBJECT_PROMOTION,
            "page_style",
        ),
        # ── услуги / номера / события
        _s("service_layout", _("Raster"), "service_preset", ("service_index_layout",)),
        # STU-15c: дефолт сортировки листинга — у каталога он есть с UB2-2, у трёх
        # других листингов владелец не мог задать порядок вообще.
        _s("services_sort", _("Sortierung"), "services_sort", ("services_sort",)),
        _s(
            "service_detail_sections",
            _("Abschnitte"),
            "sd_visible_*",
            ("service_detail", "hidden"),
        ),
        # STU-15b: раскладка страницы — у услуги/номера/события её не было, хотя тело
        # у них устроено так же, как у товара (data-driven цикл секций UA4-2).
        _s(
            "service_detail_layout",
            _("Aufbau der Detailseite"),
            "sd_layout",
            ("service_detail", "layout"),
        ),
        _s("stay_layout", _("Raster"), "stay_preset", ("stay_index_layout",)),
        _s("stays_sort", _("Sortierung"), "stays_sort", ("stays_sort",)),
        _s("stay_detail_sections", _("Abschnitte"), "std_visible_*", ("stay_detail", "hidden")),
        _s(
            "stay_detail_layout",
            _("Aufbau der Detailseite"),
            "std_layout",
            ("stay_detail", "layout"),
        ),
        _s("events_layout", _("Raster"), "events_preset", ("events_index_layout",)),
        _s("events_sort", _("Sortierung"), "events_sort", ("events_sort",)),
        _s(
            "event_detail_sections",
            _("Abschnitte"),
            "ed_visible_*",
            ("event_detail", "hidden"),
        ),
        _s(
            "event_detail_layout",
            _("Aufbau der Detailseite"),
            "ed_layout",
            ("event_detail", "layout"),
        ),
        # ── корзина
        _s("cart_upsell", _("Passt dazu"), "cart_show_upsell", ("cart_show_upsell",)),
        # ── STU-8: настройки, которые панель показывала, а реестр не знал. Реестр —
        # единственный источник ответа «что настраивается на этой странице», поэтому
        # список обязан быть полным: замок test_registry_and_panel_agree сверяет его
        # с разметкой билдера в обе стороны.
        _s(
            "catalog_menu_prices",
            _("Preise in der Speisekarte anzeigen"),
            "menu_show_prices",
            ("menu_show_prices",),
        ),
        _s(
            "catalog_menu_labels",
            _("Kennzeichnung in der Speisekarte (Diäten, Allergene)"),
            "menu_labels",
            ("menu_labels",),
        ),
        _s(
            "product_related",
            _("Related products grid"),
            "related_preset",
            ("detail_related_layout", "preset"),
        ),
        # STU-8: ширина текстовой колонки — артборд «Тип: Текстовая страница».
        # Ключ presence-minimal ("" = прежняя узкая колонка → golden целы).
        _s(
            "text_width",
            _("Textbreite"),
            "sd_text_width",
            ("site_defaults", "text_width"),
        ),
    )
}


# ─────────────────────────── типы страниц ───────────────────────────


@dataclass(frozen=True)
class PageType:
    """Тип страницы витрины: как его узнать и что на нём настраивается."""

    code: str
    label: str
    url_names: tuple[str, ...]
    settings: tuple[str, ...] = ()
    #: хост `page_blocks` (пусто — своих блоков у типа нет)
    block_host: str = ""
    #: вид сущности на странице — им подписывается охват «только здесь»
    object_kind: str = ""
    #: имена url-аргументов, по которым находится сущность (первый непустой
    #: побеждает: один и тот же тип живёт на нескольких роутах — товар на uuid
    #: `pk` и на SEO-слаге `pslug`, KAT-3)
    object_args: tuple[str, ...] = ()


PAGE_TYPES: tuple[PageType, ...] = (
    PageType(
        "home",
        _("Startseite"),
        ("storefront-home",),
        # STU-9: форму карточки главной НЕ объявляем — её строка живёт в области
        # «page», а уровень «эта страница» на главной открывает «sections» (там её
        # собственные настройки). Обещать настройку, которую панель показать не
        # может, — тот же дефект, что и чинили. Задаётся с любой страницы списка
        # или детали, где карточки и видно.
        ("home_sections", "home_hero"),
    ),
    PageType(
        "catalog",
        _("Katalog"),
        ("storefront-products",),
        (
            "catalog_page_style",
            "catalog_layout",
            "catalog_sort",
            "catalog_filters",
            "catalog_menu_prices",
            "catalog_menu_labels",
            "product_card_form",
        ),
        block_host="catalog",
    ),
    PageType(
        "category",
        _("Kategorie"),
        ("storefront-category",),
        (
            "category_page_style",
            "catalog_layout",
            "catalog_filters",
            "catalog_subcats",
            "product_card_form",
            # STU-9: сортировка по умолчанию действует и в КАТЕГОРИИ — страницу
            # обслуживает та же вьюха product_list (KAT-1), `catalog_sort`
            # читается из конфига до фасетов. Раньше настройка была объявлена
            # только у корня, и в категории задать её было нечем.
            "catalog_sort",
            "catalog_menu_prices",
            "catalog_menu_labels",
        ),
        block_host="catalog",
        object_kind=OBJECT_CATEGORY,
        object_args=("slug",),
    ),
    PageType(
        "product",
        _("Produktseite"),
        ("storefront-product", "storefront-product-slug", "storefront-product-seo"),
        (
            "product_detail_layout",
            "product_detail_sections",
            "product_card_form",
            "product_related",
        ),
        block_host="product_detail",
        object_kind=OBJECT_PRODUCT,
        object_args=("pk", "pslug"),
    ),
    PageType(
        "promos",
        _("Aktionen"),
        ("storefront-aktionen",),
        ("promo_page_style", "promo_layout", "promo_grouping", "promo_card_form"),
    ),
    PageType(
        "promo_group",
        _("Aktionsgruppe"),
        ("storefront-aktionen",),  # тот же роут + ?gruppe=<ключ>
        # STU-8: раньше сюда же были записаны `promo_layout` и (в разметке) шаблон
        # обзора. На странице группы они не действуют: выбранная группа делает
        # `has_filters` истинным, секций групп нет вовсе (`grouped = []`), а шаблон
        # берётся групповой (public_views: page_style пуст при `?gruppe=`). Панель
        # предлагала настройки, которые здесь ничего не меняют.
        ("promo_group_style", "promo_card_form"),
        object_kind=OBJECT_PROMO_GROUP,
        object_args=("gruppe",),
    ),
    PageType(
        "promo",
        _("Aktionsseite"),
        ("storefront-promotion",),
        ("promo_detail_style", "promo_card_form"),
        object_kind=OBJECT_PROMOTION,
        object_args=("pk",),
    ),
    PageType(
        "services",
        _("Leistungen"),
        ("storefront-termin",),
        ("service_layout", "services_sort", "product_card_form"),
        block_host="services",
    ),
    PageType(
        "service",
        _("Leistung"),
        ("storefront-service-detail", "storefront-service-slots"),
        ("service_detail_sections", "service_detail_layout", "product_card_form"),
        block_host="service_detail",
    ),
    PageType(
        "stays",
        _("Zimmer"),
        ("storefront-unterkunft",),
        ("stay_layout", "stays_sort", "product_card_form"),
        block_host="stay_rooms",
    ),
    PageType(
        "stay",
        _("Zimmerseite"),
        ("storefront-unterkunft-unit",),
        ("stay_detail_sections", "stay_detail_layout", "product_card_form"),
        block_host="stay_detail",
    ),
    PageType(
        "events",
        _("Veranstaltungen"),
        ("storefront-events",),
        ("events_layout", "events_sort", "product_card_form"),
        block_host="events",
    ),
    # STU-9: у списка поездок СВОЙ тип. Раньше он был склеен с «Veranstaltungen»,
    # и панель предлагала там две вещи, которых на этой странице нет: раскладку
    # (`tour_index` её не читает — список строится группами по странам) и блоки
    # `page_blocks "events"` (шаблон их не выводит). Своих настроек у страницы пока
    # нет — честнее показать это, чем предлагать неработающее.
    # STU-14: раскладку страница по-прежнему не читает (список строится группами по
    # странам), но блоки и ширина текста ей доступны — панель больше не пуста.
    PageType("tours", _("Reisen"), ("storefront-tours",), ("text_width",), block_host="tours"),
    PageType(
        "event",
        _("Veranstaltungsseite"),
        ("storefront-event", "storefront-tour"),
        # LAY-4: `product_card_form` снят ОСОЗНАННО. На детали события и тура нет
        # ни одной карточки сущности: «Weitere Termine» — чипы дат, а не карточки.
        # Настройка там ничего не меняла (класс «обещание без исполнения», STU-9);
        # форма карточки событий задаётся со ЛИСТИНГА (`events`).
        ("event_detail_sections", "event_detail_layout"),
        block_host="event_detail",
    ),
    PageType("cart", _("Warenkorb"), ("storefront-cart",), ("cart_upsell",), block_host="cart"),
    PageType("text", _("Über uns"), ("storefront-about",), ("text_width",), block_host="info"),
    # STU-14: раньше все четыре страницы делили хост `info`, а выводился он ТОЛЬКО на
    # «О нас» — блок, поставленный на команду или галерею, не появлялся нигде.
    PageType("team", _("Team"), ("storefront-team",), ("text_width",), block_host="team"),
    PageType(
        "gallery", _("Galerie"), ("storefront-gallery",), ("text_width",), block_host="gallery"
    ),
    PageType(
        "reviews", _("Bewertungen"), ("storefront-reviews",), ("text_width",), block_host="reviews"
    ),
    PageType("blog", _("Blog"), ("storefront-blog",), ("text_width",), block_host="blog"),
    PageType(
        "blog_post",
        _("Blogbeitrag"),
        ("storefront-blog-post",),
        ("text_width",),
        block_host="blog_post",
    ),
    # STU-14: лендинги архетипа доступны из «Seite ▾» (modules.storefront_landing) —
    # без своего типа владелец переходил туда и упирался в пустую панель.
    PageType(
        "loyalty",
        _("Treueprogramm"),
        ("storefront-loyalty",),
        ("text_width",),
        block_host="loyalty",
    ),
    PageType(
        "gift", _("Gutscheine"), ("storefront-gutschein",), ("text_width",), block_host="gift"
    ),
    PageType(
        "anfrage", _("Anfrage"), ("storefront-anfrage",), ("text_width",), block_host="anfrage"
    ),
    PageType(
        "contact", _("Kontakt"), ("storefront-message",), ("text_width",), block_host="message"
    ),
    PageType(
        "wishlist",
        _("Merkzettel"),
        ("storefront-wishlist",),
        ("text_width",),
        block_host="wishlist",
    ),
    PageType(
        "combos",
        _("Kombis"),
        ("storefront-combos",),
        # Набор рисуется своей карточкой (`_combo_card`) — форму карточки ТОВАРА здесь
        # не обещаем (правило STU-9: не предлагать настройку, которой страница не читает).
        ("text_width",),
        block_host="combos",
    ),
    PageType("finder", _("Finder"), ("storefront-finder",), ("text_width",), block_host="finder"),
    PageType(
        "lookbook",
        _("Lookbook"),
        ("storefront-lookbook",),
        ("text_width", "product_card_form"),
        block_host="lookbook",
    ),
    PageType(
        "legal",
        _("Rechtliches"),
        (
            "storefront-impressum",
            "storefront-privacy",
            "storefront-withdrawal",
            "storefront-agb",
        ),
        ("text_width",),
        block_host="legal",
    ),
)

#: Тип-заглушка: путь не распознан. Панель покажет только общий уровень.
OTHER = PageType("other", _("Seite"), ())

_BY_CODE: dict[str, PageType] = {p.code: p for p in PAGE_TYPES}


def page_type(code: str) -> PageType:
    """Тип по коду; неизвестный код → `OTHER` (панель не падает на мусоре)."""
    return _BY_CODE.get(code or "", OTHER)


def settings_for(code: str) -> list[Setting]:
    """Настройки типа страницы, в порядке реестра."""
    return [SETTINGS[c] for c in page_type(code).settings if c in SETTINGS]


# ─────────────────────────── резолвер ───────────────────────────


@dataclass(frozen=True)
class PageContext:
    """Что именно открыто на канве."""

    type: PageType
    #: значение url-аргумента (pk/slug) или ключ группы акций
    object_ref: str = ""
    block_host: str = ""
    path: str = ""
    query: dict[str, str] = field(default_factory=dict)

    @property
    def code(self) -> str:
        return self.type.code

    @property
    def label(self):
        return self.type.label

    @property
    def settings(self) -> list[Setting]:
        return settings_for(self.type.code)


#: url_name → тип. Строится один раз; `storefront-aktionen` намеренно указывает на
#: «Aktionen» — группа отличается наличием `?gruppe=` (см. `resolve_page`).
_BY_URL_NAME: dict[str, PageType] = {}
for _pt in PAGE_TYPES:
    if _pt.code == "promo_group":
        continue
    for _name in _pt.url_names:
        _BY_URL_NAME.setdefault(_name, _pt)


def resolve_page(path: str, query: dict | None = None) -> PageContext:
    """Путь канвы → контекст страницы.

    Разбираем ШТАТНЫМ резолвером по `config.urls_tenant`: подстроки в пути (`/sortiment/`,
    `/p/`) совпадают у разных типов, а url_name однозначен. Любая ошибка резолва —
    тип `other`: редактор обязан открыться и на незнакомом пути.
    """
    parts = urlsplit(path or "/")
    clean = parts.path or "/"
    q: dict[str, str] = dict(query or {})
    if not q and parts.query:
        from urllib.parse import parse_qsl

        q = dict(parse_qsl(parts.query))

    try:
        match = resolve(clean, urlconf="config.urls_tenant")
    except (Resolver404, ValueError):
        return PageContext(OTHER, path=clean, query=q)

    return resolve_match(match, q, path=clean)


def resolve_match(match, query: dict | None = None, path: str = "") -> PageContext:
    """То же, но по УЖЕ разобранному `request.resolver_match`.

    На витрине Django резолвит путь сам, ещё до вьюхи, — второй разбор ради
    `data-stu-page` был бы платой на каждом рендере страницы. `match` может быть
    `None` (страница вне urlconf) — это честный `other`, а не ошибка.
    """
    q: dict[str, str] = dict(query or {})
    if match is None:
        return PageContext(OTHER, path=path, query=q)

    pt = _BY_URL_NAME.get(getattr(match, "url_name", "") or "")
    if pt is None:
        return PageContext(OTHER, path=path, query=q)

    # Группа акций — тот же роут, что обзор, но с выбранной группой.
    if pt.code == "promos" and (q.get(GROUP_PARAM) or "").strip():
        group = _BY_CODE["promo_group"]
        return PageContext(
            group,
            object_ref=q[GROUP_PARAM].strip(),
            block_host=group.block_host,
            path=path,
            query=q,
        )

    ref = ""
    for arg in pt.object_args:
        raw = match.kwargs.get(arg)
        if raw not in (None, ""):
            ref = str(raw)
            break

    host = pt.block_host
    # KAT-1: у категории свой хост блоков на КАЖДУЮ категорию (валидацию слага
    # держит siteconfig — мусорный слаг даёт пустой хост, а не мусор в конфиге).
    if pt.code == "category" and ref:
        # Импорт отложенный: apps.tenants.siteconfig тянет apps.core на импорте
        # (card_forms/detail_sections) — конвенция apps/core, чтобы не замкнуть круг.
        from apps.tenants.siteconfig import category_host

        host = category_host(ref) or pt.block_host

    return PageContext(pt, object_ref=ref, block_host=host, path=path, query=q)
