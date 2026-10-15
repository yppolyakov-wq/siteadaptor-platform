# План реализации: T-8.19 «Entdecke Solingen», главная портала города

> Составлен агентом planner 2026-10-15. Миграций нет. Источники: `docs/t8-roadmap-2026-10-10.md:40`, `docs/tz-siteadaptor-2-0-phase0-2026-10-10.md:60`.

## 0. Коротко

Корень городского портала (`kind=city`, без `business_type`, без facet и района, без параметров ленты) становится главной: заголовок, поиск, вкладки, плитки разделов, полоса «Anzeigen» и шесть блоков. Всё прочее остаётся лентой: `?kind=`/`?kat=`/`?merkmal=`/`?q=`/`?neu=1`, районы, facet-страницы, вертикальные и combo-порталы.

Главный принцип: у каждого блока один объект `FeedScope`. По нему строится и выборка блока, и ссылка «Alle →». Лента разбирает ту же ссылку обратно в тот же `FeedScope`. Поэтому «Alle →» всегда ведёт на набор, который содержит все карточки блока, и это проверяется замком.

## 1. Текущее состояние

**Маршрут.** `config/urls_portal.py:21` — `path("", portal_views.portal_home, name="portal-home")`. Тот же `portal_home` обслуживает `stadtteil/<district>/` (`:58-63`) и catch-all `<str:facet>/` (`:66`). Поискового маршрута на портале нет.

**Вьюха** `apps/aggregator/portal_views.py:115-281` `portal_home(request, facet=None, district=None)` под `@cache_public_page`:
- `:123-141` — район (404 на неизвестный) и facet по свободной оси `_free_axis` (`:29`). У городского портала свободная ось — `business_type`.
- `:147` — `category_facets.selected()` → `kat`, `tag`.
- `:151-153` — `kind` из `?kind=`, допустимы только значения `AggregatorListing.KINDS`. Без `kind` выборка ограничена `OFFER_KINDS` (`models.py:62`: promotion/stay/event/menu). Комментарий там прямо говорит: «полная главная с блоками — T-8.19».
- `:154-160` — `whole_pool` и `_kind_chips` (`:313-340`): чипы «Angebote» (ссылка `path` без параметра) + Produkte/Dienstleistungen/Unternehmen, только непустые, при одной группе не показываются. Чипа Events нет: события входят в «Angebote».
- `:168` — `category_facets.chips(base_pool, path, kat, tag, extra={"kind": kind})`. Разделы и категории считаются по пулу без `kat`/`tag` (`category_facets.py:34-92`).
- `:182-190` — «рядом» (`?lat/lng`), иначе `split_featured` (`views.py:234-253`: featured сверху первой страницы, исключены из ленты, инкремент `featured_impressions`) + `paginate(... created_at, limit=24)`.
- `:192-217` — отель (H8a/H8b), к городскому порталу не относится.
- `:220` — `reviews.attach_ratings` (один запрос). `:221-280` — canonical, CollectionPage LD, `other_portals`, избранное, `shows_demo`, `map_points`.
- Каждая выборка идёт через `views.listings_for` (`views.py:49-140`). Там `AggregatorListing.objects.public()` (`models.py:17-37`: активные, без `hidden_at`, не истёкшие по `ends_at`, без `withheld_schemas()` — это подзапрос, лишнего запроса не даёт), `include_demo` → `is_demo=False`, исключение прошедших событий, `q` через icontains, `city_category` через `keys_for_filter`, `city_tag`.

**Шаблон** `templates/aggregator/portal_home.html`: h1 и intro (`:8-15`), полоса демо (`:18-20`), чипы районов (`:23-33`), `kind_chips` (`:35-41`), чипы категорий (`:42`), форма отеля (`:45-64`), facet-чипы «Branche» (`:66-76`), карта (`:78`), `_cards.html` + «Show more» (`:80-91`), `other_portals` (`:94-104`). База — `portal_base.html`: в шапке `portal.title_text`, переключатель языка, вход. Карточки — `_cards.html`: «★ Anzeige» при `is_featured_now` (`:27-30`), клик по featured идёт через счётчик (`:9`), бейдж Demo (`:23-26`), Neu/наличие (`:49-50`).

**Кэш** (`apps/core/pagecache.py:193-205`): кэшируется только GET без query и без сессии; ключ `pubpage2:{host}:{path}:{lang}`. Корень без параметров кэшируется, любой `?…` идёт мимо кэша.

**Новизна.** `tasks.py:849` `NEW_PRODUCT_DAYS = 14`; `is_new` у товара ставится при синке (`:926`), у прочих видов всегда False.

**Поиск** есть только на `/entdecken/` (`views.discover_index`, `views.py:338-502`): `q` через `listings_for(q=)`, лимит `ratelimit.hit("entdecken-search", …, SEARCH_RATE_LIMIT=60, window=60)` (`:383-389`). Форма `_search_form.html` постит на `aggregator-index`, на хосте портала такого маршрута нет.

## 2. Решения и развилки (рекомендации)

**Р-1. Где живёт главная.** Рекомендую режим главной внутри `portal_home` при условии `portal.kind == KIND_CITY and portal.city and not portal.business_type and facet is None and district is None and not (set(request.GET) & FEED_PARAMS)`.
- `FEED_PARAMS = {"kind","kat","merkmal","q","neu","cursor","lat","lng"}`. Посторонние `?ch=`, `?utm_*`, `?fbclid` главную не выключают: иначе ссылка из соцсети открывала бы ленту.
- Вертикальные, combo, отельные порталы, районы и facet-страницы не меняются (меньше переписок тестов). Главную районов можно сделать позже тем же кодом.
- Альтернатива — новый URL `/entdecken/` на портале. Отвергнута: корень — то, что человек видит по QR и ссылке.

**Р-2. Вкладки = группы значения `kind`.** Один параметр, без второго `?tab=` (прецедент LAY-7c — два контрола на один смысл). Реестр групп:

| Вкладка | URL | Виды |
|---|---|---|
| Alle | `/` (главная); лента «всё» — `?kind=alle` | все `KINDS` |
| Produkte | `?kind=product` | product |
| Angebote | `?kind=angebote` | promotion, menu, stay |
| Dienstleistungen | `?kind=service` | service |
| Unternehmen | `?kind=business` | business |
| Events | `?kind=event` | event |

- Так каждый вид листинга достижим ровно одной вкладкой. Номера (stay) попадают в Angebote, потому что отдельной вкладки по ТЗ нет.
- Старые одиночные `?kind=promotion|menu|stay` продолжают работать (обратная совместимость), активной подсвечивается группа Angebote.
- Вкладка показывается, если её виды есть в пуле портала. «Alle» есть всегда, когда пул не пуст. Если кроме «Alle» нет ни одной группы, полоса не показывается.
- Вкладки рисуются на главной и в ленте городского портала. Там они заменяют `_kind_chips`; на прочих порталах `_kind_chips` остаётся.
- Без `kind` вне режима главной (район/facet) сохраняется прежняя семантика «предложения» (`OFFER_KINDS`).

**Р-3. Блоки — реестр в коде** (`apps/aggregator/portal_home_blocks.py`), порядок как в ТЗ:

| key | Заголовок | `FeedScope` (выборка и «Alle →») | Сортировка | Видов на бизнес | «Alle →» |
|---|---|---|---|---|---|
| `angebote` | Aktuelle Angebote | kinds=(promotion, menu) | `ends_at` asc nulls last → `-discount_percent` → `-created_at` (срочное первым, как O-4) | 2 | `?kind=angebote` |
| `produkte` | Produkte aus {city} | kinds=(product,), без `sold_out` | сначала с признаком `regional` (Case/When `city_tags__contains=["regional"]`), затем `-created_at` | 2 | `?kind=product` |
| `essen` | Essen & Trinken | kat=`essen-gastronomie`, все виды кроме business | `-created_at` | 2 | `?kind=alle&kat=essen-gastronomie` |
| `freizeit` | Freizeit | kat=`freizeit-erlebnisse`, все кроме business | `starts_at` asc nulls last → `-created_at` | 2 | `?kind=alle&kat=freizeit-erlebnisse` |
| `unternehmen` | Lokale Unternehmen | kinds=(business,) | дневная ротация `MD5(Concat(Cast(id), Value(date_iso)))` — честно ко всем бизнесам и стабильно в пределах TTL кэша | 1 | `?kind=business` |
| `neu` | Neu | new_only (`Q(is_new=True) \| Q(created_at__gte=now-NEW_DAYS)`), все виды | `-created_at` | 1 | `?kind=alle&neu=1` |

Обоснования:
- «Produkte aus Solingen» — все товары города. Портал и так ограничен городом. Признак `regional` только поднимает товар выше, а не отбирает: иначе блок почти всегда был бы пуст, ведь признак ставит только владелец (`city_categories.py:8-10`). Распроданное на главной не продвигаем; в ленте `?kind=product` оно остаётся, и включение «блок ⊆ ленты» не нарушается.
- «Essen & Trinken» берёт только раздел `essen-gastronomie`. `?kat=` принимает одно значение, а два раздела дали бы ссылку «Alle →» без своей ленты. Продуктовые акции (`lebensmittel-getraenke`) и так видны в «Aktuelle Angebote» и «Produkte». Альтернатива — разрешить `?kat=` списком — относится к T-8.20.
- «Freizeit» — только раздел `freizeit-erlebnisse`. Отдельные события любых разделов видны во вкладке Events.
- `NEW_DAYS = tasks.NEW_PRODUCT_DAYS` (14), одна константа.
- Лимит — 6 карточек на блок: полные ряды при сетке 2/3 колонки `_cards.html` (урок DL-11). Блок выбирает до `6 × 4` строк, затем в Python ограничивает число карточек на бизнес (иначе 200 товаров одного магазина вытеснят всех, урок T-8.11) и убирает дубли между блоками: карточка, показанная в блоке выше, ниже не повторяется. Дедупликация только удаляет, поэтому включение в ленту сохраняется.
- Пустой блок не рендерится. Если пусты все блоки и плитки, показываются поиск и «Noch keine Angebote».

**Р-4. Плитки разделов.** 15 разделов `city_categories.SECTIONS` (иконка + подпись + число). Показываются только разделы с карточками; порядок — по справочнику. Ссылка — `?kind=alle&kat=<section>`. Числа берутся из того же запроса, что и наличие видов (см. §3).

**Р-5. Featured (UWG §5a, FD-4).** Над блоками — отдельная полоса «Anzeigen» с явной подписью. В ней `split_featured(offer_pool, first_page=True, limit=3)` по пулу Angebote + Produkte + Dienstleistungen; показ увеличивает `featured_impressions`, как сейчас. Сами блоки органические: featured в них не поднимается. Карточки из полосы «Anzeigen» исключаются из блоков, как `split_featured` исключает их из ленты. Бейдж «★ Anzeige» и клик через счётчик дают общие `_cards.html`. Известное ограничение, оно уже есть сегодня: при попадании в кэш показ не считается.

**Р-6. Строка поиска.** Форма GET на `{% url 'portal-home' %}` с полем `q`. В `portal_home` при `q` открывается лента по всем видам: при пустом `kind` группа «alle», потому что «Brot» должен находить товары. Выборка — `listings_for(q=…)` (icontains, как на `/entdecken/`). Перед выборкой — `ratelimit.hit("portal-search", client_ip, limit=views.SEARCH_RATE_LIMIT, window=60)` → 429. `q` (обрезанный до 100 символов) переносится в `page_carry` и в чипы категорий. Это минимальный поиск; полнотекст, опечатки и общие фильтры — T-8.20, он заменит только бэкенд функции.

**Р-7. Заголовок.** h1 «Entdecke {city}», как в ТЗ. Подзаголовок — `portal.tagline_text`, по умолчанию «Angebote, Produkte, Dienstleistungen und Unternehmen aus {city}» (нейтрально, без du/Sie). `portal.intro_text` выводится под ним, если задан. `<title>` остаётся `portal.title_text`, канонический адрес — корень. На главной сохраняются чипы районов и «Branche» (facets). Они нужны для перелинковки и sitemap, и на них опирается тест `test_city_portal_lists_type_chips`. Ставим их компактно, под плитками.

**Р-8. Прочее на главной.** Карты на главной нет (она остаётся в ленте и в «рядом»). Есть CollectionPage/ItemList LD по объединению карточек блоков (тест `test_portal_seo:75`), полоса `shows_demo` по карточкам главной, избранное (`fav_ids`) и `other_portals`.

## 3. Инкременты

### 19.1 Модуль реестра (без шаблонов)
Файл: `apps/aggregator/portal_home_blocks.py` (новый).

```python
NEW_DAYS = tasks.NEW_PRODUCT_DAYS  # импортировать константу, не копировать
BLOCK_LIMIT = 6
OVERFETCH = 4
FEED_PARAMS = frozenset({"kind", "kat", "merkmal", "q", "neu", "cursor", "lat", "lng"})

@dataclass(frozen=True)
class FeedScope:
    kind_key: str = ""                 # "alle"|"angebote"|<kind>|""(offers default)
    kat: str = ""
    tag: str = ""
    new_only: bool = False
    exclude_kinds: tuple[str, ...] = ()
    exclude_sold_out: bool = False     # только для блока; в URL не попадает

@dataclass(frozen=True)
class Tab:   key: str; label: object; kinds: tuple[str, ...]
@dataclass(frozen=True)
class Block: key: str; title: object; scope: FeedScope; order: str; per_business: int

TABS: tuple[Tab, ...]                  # таблица Р-2; label через gettext_lazy
BLOCKS: tuple[Block, ...]              # таблица Р-3; title "Produkte aus %(city)s" — python-format, НЕ f-строка

def kinds_for(kind_key: str) -> tuple[str, ...] | None   # None = мусор → игнор
def parse_scope(request) -> FeedScope                    # kind/kat/merkmal/neu → тот же объект
def scope_url(path: str, scope: FeedScope, **extra) -> str
def apply_scope(qs, scope: FeedScope, *, now=None) -> QuerySet  # kinds/kat(keys_for_filter)/tag/new/exclude/sold_out
def is_home_request(portal, facet, district, request) -> bool   # Р-1
def presence(base_qs) -> dict   # ОДИН запрос: values("listing_kind","city_category").annotate(n=Count("id"))
def tabs(presence: dict, active_key: str, path: str) -> list[dict]
def section_tiles(presence: dict, path: str) -> list[dict]      # [{key,icon,label,count,url}]
def home_blocks(base_qs, *, city: str, exclude_pks: set[int], path: str) -> list[dict]
    # [{key,title,items,more_url}] — только непустые; 1 запрос на блок; cap per tenant; dedupe
```

- Для блоков `apply_scope` принимает уже готовый `listings_for(city=…, include_demo=portal.show_demo)` (через `public()`). Фильтры `kat`/`tag` повторяют `listings_for` (`keys_for_filter`, `normalize_tags`). Лучше вынести их из `listings_for` (`views.py:97-109`) в `_apply_city_filters(qs, city_category, city_tag)` и вызывать из обоих мест, чтобы семантика фильтра была одна.
- Сортировки — именованные ключи (`"urgent"`, `"regional_first"`, `"newest"`, `"upcoming"`, `"daily_rotation"`) со словарём `_ORDERS` выражений `order_by`. Строк ORM в реестре нет.
- Ротация: `from django.db.models.functions import MD5, Cast, Concat` + `Value(timezone.localdate().isoformat())`.

### 19.2 Лента городского портала понимает группы, `neu` и `q`
Файл `apps/aggregator/portal_views.py`:
- `:151-153` — заменить разбор `kind` на `scope = portal_home_blocks.parse_scope(request)`. При `kind_key in {"alle","angebote"}` или одиночном виде — `kinds=`. При пустом `kind_key` без `q` — `OFFER_KINDS` (прежняя семантика); при `q` — все виды. `neu=1` применяется через `apply_scope` поверх `pool`.
- При `q` перед любыми выборками стоит ratelimit (429).
- `:160` — для городского портала (условие Р-1 без проверки GET) `tabs(...)` вместо `_kind_chips`. Для остальных порталов `_kind_chips` без изменений.
- `:168` — `extra={"kind": kind_key, "neu": "1" if scope.new_only else "", "q": q}`.
- `:264-266` — `page_carry` += `neu`, `q`.
- Длину функции разгрузить: тело ленты вынести в `_render_feed(request, portal, facet, district, …)`, вьюха станет диспетчером.

Шаблон `portal_home.html:35-41`: при наличии `tabs` подключать новый партиал `aggregator/_portal_tabs.html` (`data-portal-tab="{{ t.key }}"`), иначе прежние `kind_chips`.

### 19.3 Рендер главной
- `portal_views.py` — `_render_home(request, portal) -> HttpResponse`, вызывается в начале `portal_home` при `is_home_request`. Он строит `base = listings_for(city=portal.city, include_demo=portal.show_demo)`, затем `presence(base)`, «Anzeigen» через `split_featured(apply_scope(base, FeedScope("angebote+products+services")), first_page=True, limit=3)` и `home_blocks(base, exclude_pks=featured_pks)`. Один раз вызывается `reviews.attach_ratings(all_cards)`, плюс `_district_choices`, `_facet_choices`, `other_portals`, `fav_ids` и LD по `all_cards`.
- Новый шаблон `templates/aggregator/portal_discover.html` (extends `portal_base.html`): h1/подзаголовок → `_portal_search.html` → `_portal_tabs.html` → полоса демо → «Anzeigen» (`_cards.html with items=featured`) → `_section_tiles.html` → `{% for b in blocks %}` `_home_block.html` (h2 + «Alle anzeigen →» + `_cards.html with items=b.items`) → районы/Branche → `other_portals`.
- Новые партиалы: `_portal_search.html`, `_portal_tabs.html`, `_section_tiles.html`, `_home_block.html`. Комментарии `{# #}` только однострочные, многострочные — через `{% comment %}`.

**Бюджет запросов главной** (не зависит от объёма данных):

| # | Запрос |
|---|---|
| 1 | presence (виды × категории, с подзапросом withheld) |
| 2–3 | featured: SELECT и UPDATE impressions (только если что-то есть) |
| 4–9 | шесть блоков по одному запросу |
| 10 | ratings_for |
| 11 | `_district_choices` |
| 12 | `_facet_choices` |
| 13 | `other_portals` |
| (+1) | `fav_ids` только у вошедших |

Итого не больше 14 для анонима. Резолв портала — в middleware с кэшем. Замок `django_assert_max_num_queries(14)`, плюс сравнение: одинаковое число запросов при 1 и 30 листингах. Это и есть защита от N+1.

**Кэш.** Корень без query кэшируется `cache_public_page` (TTL настройки), ключ по хосту и языку. CSRF-форм на главной нет: поиск — GET, сердечки только под логином, а при логине сессия обходит кэш. Тест `test_portal_home_stays_cached_after_csrf_guard` (`test_portal_pages.py:211-220`) обязан остаться зелёным. Вкладки, поиск и «Alle →» несут query и идут мимо кэша, это ожидаемо.

### 19.4 i18n, CSS, стенд, доки
- Новые msgid в 5 каталогах `locale/{de,en,tr,ru,uk}/LC_MESSAGES/django.po`. Уже существуют: «Neu», «Events», «Produkte», «Suchen», «Alle», «Alle anzeigen», «Aktuelle Angebote», «Dienstleistungen», «Unternehmen», «Anzeige». Добавить:
  - «Entdecke %(city)s»
  - «Angebote, Produkte, Dienstleistungen und Unternehmen aus %(city)s»
  - «Produkte aus %(city)s»
  - «Essen & Trinken»
  - «Freizeit»
  - «Lokale Unternehmen»
  - «Anzeigen»
  - «Bereiche entdecken»
  - «Was suchen Sie in %(city)s?»
  - «Noch keine Angebote in %(city)s»
  - строка 429 переиспользуется
- В Python — `gettext_lazy` с именованными плейсхолдерами, без f-строк и без псевдонимов `_l`/`_t` (уроки I18N-13 и ревью Кабинет-X). Перед пушем — `scripts/i18n_quickcheck.py` и сверка новых msgid напрямую с .po: CI-гейт `i18n_gap` строже quickcheck.
- Новые классы Tailwind (например `grid-cols-3 sm:grid-cols-5` у плиток, `snap-x overflow-x-auto` у вкладок на мобильном) → `npm run build:css`, закоммитить `static/css/app.css`.
- Стенд Playwright: `solingen.<base>` (show_demo=True) при 390 и 1440 px, de/ru. Проверить: нет пустых блоков и плиток, каждая «Alle →» открывает непустую ленту, вкладки переключаются, поиск «Brot» находит товары, нет горизонтального переполнения.
- Доки: строка в `docs/build-log.md`, статус в `docs/task-catalog.md` и `docs/t8-roadmap-2026-10-10.md:40`, верхний статус в `CLAUDE.md` §3.

## 4. Тесты (замки)

Новый файл `apps/aggregator/tests/test_portal_discover.py`, через `RequestFactory` + `req.portal`, `@override_settings(ROOT_URLCONF="config.urls_portal")`.

1. **Режим:** `/` городского портала → главная (`data-portal-home`). `/?utm_source=x` и `/?ch=qr` → тоже главная. `/?kind=product`, `/?q=a`, `/?kat=…`, `/?neu=1` → лента. Вертикальный/combo-портал, район, facet → прежняя лента.
2. **Пустой блок скрыт:** есть только акции → на странице только `data-home-block="angebote"`, остальных `data-home-block` нет. Пустой пул → нет ни блоков, ни вкладок, есть поиск и «Noch keine…».
3. **Вкладка без данных скрыта:** без событий нет `data-portal-tab="event"`; с событием есть. Остался только один вид → полосы вкладок нет.
4. **Плитки:** показываются только разделы с карточками, число верное, ссылка `?kind=alle&kat=<section>`.
5. **`objects.public()` на всех чтениях главной** (параметризовать по блоку): в блоки, плитки, вкладки и presence не попадают `is_active=False`, `hidden_at` задан, `ends_at` в прошлом, тенант suspended/`email_pending`/`in_city_catalog=False` (через `TenantFactory`), прошедшее событие.
6. **Демо:** настоящий портал (`show_demo=False`) с демо-листингом — нет ни карточки, ни счёта в плитке, ни вкладки, которую дал бы только демо. Превью-портал (`show_demo=True`) — карточка и полоса «Vorschau» есть.
7. **Featured:** платный листинг в полосе «Anzeigen» с «★ Anzeige» и ссылкой через `aggregator-featured-click`, выше органики. В блоках он не дублируется. Органический порядок блока не меняется от `featured_until` (поменять `featured_until` у двух органических карточек — порядок в блоке тот же). `featured_impressions` +1 за рендер. Существующий `test_featured.py:84-94` остаётся зелёным без правок.
8. **«Alle →» ведёт на работающую фильтрацию** (класс-замок по `BLOCKS`): для каждого блока ссылку разобрать через `parse_scope`, построить пул ленты тем же кодом, что `_render_feed`, и проверить, что `pk` карточек блока ⊆ pk ленты. Плюс рендер `portal_home` по этому URL даёт 200 и содержит заголовок первой карточки блока.
9. **Лимиты:** не больше 6 карточек в блоке; один бизнес с 20 товарами даёт не больше 2 карточек в «Produkte»; в «Lokale Unternehmen» и «Neu» — 1 на бизнес; между блоками дублей нет.
10. **«Neu»:** листинг старше 14 дней без `is_new` не попадает; с `is_new` попадает; `?neu=1` в ленте фильтрует так же.
11. **«Produkte»:** распроданное не на главной, но есть в `?kind=product`; товар с `regional` идёт первым.
12. **Группы ленты:** `?kind=angebote` = promotion+menu+stay; `?kind=alle` = все виды; старый `?kind=promotion` работает, активна вкладка Angebote; мусор `?kind=zzz` → прежняя лента, не 500.
13. **Поиск:** `/?q=winterjacke` находит товар (все виды). Превышение лимита → 429. `q` переносится в «Show more» и в чипы категорий.
14. **Число запросов:** `django_assert_max_num_queries(14)`, одинаковое число при 1 и 30 листингах.
15. **Кэш:** главная без CSRF-токена кладётся в `pubpage2:<host>:/:de`. Существующий замок `test_portal_pages.py:211` — без изменений.
16. **SEO:** CollectionPage/ItemList на главной содержит заголовки карточек блоков (`test_portal_seo.py:75` без правок).
17. **Гигиена:** `apps/core/tests/test_template_comments.py`, `scripts/i18n_quickcheck.py`, замок свежести `app.css`.

**Осознанная переписка существующих тестов** (сначала прогнать весь `apps/aggregator`; ниже — то, что известно до кода):
- `test_city_products.py:204-223`: на корне теперь есть блок «Produkte», и «Winterjacke» распроданная — на главную она не попадёт, но утверждение «лента без товаров» переносится на `/?kind=angebote`. Утверждения про `data-kind-chip="product"` переписываются на `data-portal-tab="product"`.
- Вероятно, без правок: `test_portal_pages.py` (98, 120 — «Branche» остаётся на главной), `test_districts_portal.py`, `test_reviews.py:191`, `test_favorites.py:128/136`, `test_interlinking.py`, `test_city_categories.py:179/191` (`?kat=` → лента), `test_portal_quickfixes.py:85`. Каждый перепроверить; любую переписку вносить в коммит с объяснением.

## 5. Риски

- **`created_at` листинга ≠ дата появления объекта.** При реконсиляции с удалением и пересозданием (`visibility.apply_visibility` удаляет всё при не-listable) бизнес, вернувшийся в каталог, снова становится «Neu». Для пилота приемлемо; отметить в roadmap «Отложено».
- **`is_new` у товара не устаревает** без ресинка (`tasks.py:926`). Допустимо: явный бейдж «neu» владельца законен; «свежесть» по времени дополнительно ограничена `created_at`.
- **Плотность Золингена.** Блоки «Essen & Trinken»/«Freizeit» могут быть пустыми на настоящем портале — так и задумано (скрыты). Демо T-8.22 покрывает все 15 разделов, их проверяем стендом.
- **Счётчик показов featured** занижен при попаданиях в кэш (то же, что сегодня). Не трогаем.
- **Рост `portal_home`.** Снимается разделением на `_render_home`/`_render_feed` (19.2/19.3).
- **Канонический адрес вкладок** = корень (query отрезается). Дубли для SEO не плодим, в sitemap ничего не добавляем.

## 6. Что НЕ делаем

- **T-8.20** — полнотекст german, pg_trgm, синонимы, веса, общие фильтры (район/цена/дата/наличие/«открыто») в поиске портала, `?kat=` списком. Здесь только icontains через `listings_for(q=)` + rate-limit.
- **T-8.21** — журнал запросов и «ничего не найдено».
- Главная для районов, вертикальных и combo-порталов; карта на главной; настраиваемые оператором блоки (реестр остаётся кодом до T-8.12); миграции и новые индексы; изменения `/entdecken/` на основном домене.

## Ключевые файлы

- `apps/aggregator/portal_views.py` (`portal_home` `:115-281`, `_kind_chips` `:313-340`)
- `apps/aggregator/views.py` (`_KIND_LABELS` `:23`, `listings_for` `:49-140`, `split_featured` `:234`, `SEARCH_RATE_LIMIT` `:335`)
- `apps/aggregator/models.py` (`public()` `:17-37`, `OFFER_KINDS` `:62`, `availability`/`is_new` `:119-120`)
- `apps/aggregator/category_facets.py`
- `apps/core/city_categories.py` (`SECTIONS` `:36-52`, `keys_for_filter` `:272`)
- `apps/aggregator/tasks.py:849` (`NEW_PRODUCT_DAYS`)
- `apps/core/pagecache.py:193-205`
- `config/urls_portal.py:21`
- `templates/aggregator/portal_home.html`, `_cards.html`, `portal_base.html`
- Тесты: `apps/aggregator/tests/test_city_products.py:204`, `test_featured.py:84`, `test_portal_pages.py:97-220`, `test_portal_seo.py:59-87`
- Новые: `apps/aggregator/portal_home_blocks.py`, `templates/aggregator/portal_discover.html`, `_portal_search.html`, `_portal_tabs.html`, `_section_tiles.html`, `_home_block.html`, `apps/aggregator/tests/test_portal_discover.py`
