# План реализации T-8.20: единый поиск по каталогу города (портал + /entdecken/)

> Статус: план для согласования, кода нет. Миграции: ⚠️ `aggregator/0023` (расширение `pg_trgm`, два поля, два GIN-индекса) и `aggregator/0024` (бэкфилл). Обе в SHARED, только public-схема.
> Источники: `docs/t8-roadmap-2026-10-10.md:41`, `docs/tz-siteadaptor-2-0-phase0-2026-10-10.md:61`, `docs/t8-19-portal-home-plan-2026-10-15.md` §6 (строка 219).

---

## 1. Как поиск работает сейчас

### 1.1 Сопоставление: одно место, `icontains`
`apps/aggregator/views.py:49-132` — `listings_for(..., q=None, ...)`. Сам поиск в строках `:122-129`:
```python
Q(business_name__icontains=q) | Q(title__icontains=q) | Q(city__icontains=q) | Q(dish_names__icontains=q)
```
- `title__icontains` ищет по сериализованному JSON сразу во всех локалях. Тизер, категория, район и признаки в поиск не попадают.
- Нет стемминга (форма `Messern` не находит `Messer`), нет обработки опечаток, нет ранжирования.
- Слова запроса не делятся: `"Wiener Schnitzel"` ищется как одна подстрока.
- Базовые инварианты выборки уже работают, и поиск их наследует:
  - `objects.public()` (`models.py:35-54`): активный, не скрыт модерацией, `ends_at` в будущем или пуст, бизнес не исключён (`withheld`);
  - прошедшие события отсекаются в `:131`;
  - демо-листинги — через `include_demo` (`:83-84`).

### 1.2 Портал: `portal_views.portal_home` (`apps/aggregator/portal_views.py:118-326`)
- Общий лимит `portal-feed` 120 в минуту на любой запрос с параметрами (`:127-136`).
- `q = home.search_query(request)` (`portal_home_blocks.py:132-133`, обрезка до `SEARCH_MAX=100`, `:32`). Лимит `portal-search` — `SEARCH_RATE_LIMIT=60` (`:168-178`).
- `whole_pool = listings_for(..., q=q)` (`:186-192`) → вкладки и `presence` (`:193-199`) → `apply_scope` (`:200-213`) → `split_featured` + keyset-`paginate(order_field="created_at")` (`:219-222`).
- Карта «рядом»: `geo.nearest` (`:214-217`).
- Для пагинации переносятся параметры из `page_carry` (`:299-311`); шаблон `portal_home.html:87` добавляет `cursor=`.
- `FEED_PARAMS` (`portal_home_blocks.py:31`) решает, когда корень портала показывает ленту, а когда главную.
- `FeedScope` (`:42-47`) — область блоков главной: `kind_key`, одно значение `kat`, `tag`, `new_only`. Разбирается в `parse_scope` (`:136-144`), берётся из `category_facets.selected` (`category_facets.py:17-25`, всегда одно значение).
- Форма поиска: `templates/aggregator/_portal_search.html` (GET на `portal-home`, поля `q` и `kind`).

### 1.3 Основной домен: `views.discover_index` (`views.py:330-478`)
- Свой лимит `entdecken-search` 60 в минуту (`:375-381`).
- `listings_for(q=..., city=, type=, kind=, cat=, month=, gaeste=, anlass=, diet=, preis_von=, preis_bis=, kat, merkmal)` (`:383-397`). Для чипов — отдельная выборка `chips_base` без `kat`/`merkmal` (`:411-424`).
- Выдача: `split_featured` + keyset по `created_at` (`:425-428`); `base_qs` в шаблоне `search.html:13`.

### 1.4 «Открыто сейчас»
- `views._open_now_schemas(schemas)` (`:174-193`): один запрос к `Tenant` по набору схем, `openinghours.open_status` считается в Python. Используется только в `city_listing` (`:517-520`).
- `_attach_open_status(cards)` (`:196-223`) — бейджи на карточках, тоже одним запросом.
- Запросов на каждую строку (N+1) нет — механизм переиспользуем как есть.

### 1.5 Инфраструктура
- `pg_trgm`, `SearchVector`, `TrigramSimilarity` и `RunSQL` в проекте не используются нигде (проверено grep'ом). `django.contrib.postgres` не подключён в `SHARED_APPS` (`config/settings/base.py:17-47`).
- CI: `postgres:16-alpine` (`.github/workflows/ci.yml:31`). В официальном образе есть contrib (`pg_trgm`) и встроенные snowball-конфигурации (`german`, `english`, `russian`, `turkish`, `french`, `italian`, `spanish`, `dutch`, `portuguese`). Конфигураций для `ukrainian` и `polish` во встроенных нет.
- Права на расширение:
  - локально: роль `platform` — SUPERUSER (`scripts/dev-services.sh:25`);
  - прод: `POSTGRES_USER` образа — суперпользователь (`docker-compose.prod.yml:18-23`);
  - `pg_trgm` — trusted-расширение с PG13, его может создать и владелец БД. Это важно на будущее, когда Postgres вынесут на отдельный сервер.
- Последняя миграция: `apps/aggregator/migrations/0022_t8_11_city_products.py`.
- Все записи листингов идут через `update_or_create`, а значит через `save()`, в `tasks.py`: `:160` (promotion), `:231` (stay), `:334` (группа событий), `:396` (event), `:751` (menu), `:952` (product), `:1025` (service), `:1075` (business).
- Единственный массовый `.update()` индексируемых полей — `refresh_tenant_fields` (`tasks.py:821-838`: имя, город, район).
- Прочие `.update()` (`views.py:242,262`, `reports.py:40`, `admin.py:116,124`) меняют счётчики и `hidden_at` и в индекс не попадают.

---

## 2. Решения (рекомендация отмечена ✅)

### Р-1. Вектор: хранимый `SearchVectorField` + GIN ✅ (не вычислять на лету и не через `GeneratedField`)
- На лету: при каждом запросе `to_tsvector` по 11 локалям на весь пул, и GIN-индекс не используется. Отвергнуто.
- `GeneratedField(db_persist=True)` (Django 5.1) был бы удобнее всего: всегда актуален, даже при `.update()`. Но выражение обязано быть IMMUTABLE, а `Concat`/`concat_ws` в Postgres — STABLE, и вокруг `SearchVector` в Django есть известные проблемы. Подписи категорий и районов живут в Python-реестрах, в SQL их не достать. Риск неудачи при `migrate` выше пользы.
- ✅ Поле `search_vector = SearchVectorField(null=True, editable=False)` + `GinIndex(name="agg_search_vector_gin")`. Заполняется одной функцией `search_index.refresh(qs)` (см. §4, инкремент 20.1).

### Р-2. Мультиязычность
✅ Отдельный `to_tsvector` на каждую локаль `title`/`teaser` со своей конфигурацией. Реестр в `apps/aggregator/search.py`:
```python
TS_CONFIG = {"de": "german", "en": "english", "ru": "russian", "tr": "turkish",
             "fr": "french", "it": "italian", "es": "spanish", "nl": "dutch",
             "pt": "portuguese"}  # uk, pl и прочие → "simple"
def ts_config(locale) -> str: return TS_CONFIG.get(locale, "simple")
```
- Список локалей берётся из `settings.LANGUAGES`: появится новая локаль — она автоматически попадёт в индекс как `simple`.
- Запрос строится по ИЛИ трёх конфигураций: `german` (база DACH) | `simple` (точная форма, имена собственные, стоп-слова) | конфигурация языка посетителя (`translation.get_language()`, если это не de).
- Почему не одна конкатенация всех локалей под `german`: русские и английские слова под немецким стеммером дают мусорные лексемы, морфология ломается.
- Склейка всех локалей под `simple` — допустимый упрощённый вариант на случай, если индекс разрастётся (§6).

### Р-3. Веса: метки зашиты в вектор, числа задаются в настройках ✅
| Метка | Поля |
|---|---|
| A | `title` — все локали |
| B | `business_name` (german + simple), `dish_names` (jsonb, приведённый к text) |
| C | `teaser` — все локали; подписи раздела и категории справочника, тема события (`category`), признаки `city_tags` |
| D | `city`, подпись района |

- Числовые веса передаются в момент запроса: `SearchRank(F("search_vector"), query, weights=[D, C, B, A])`. Поменять их можно без миграции и без переиндексации.
- ✅ Где хранить: `settings.AGGREGATOR_SEARCH` в `config/settings/base.py`, рядом с константами агрегатора. Модель и админку не заводим: меняется редко, на изменение нужен тест, а операторские настройки появятся только в T-8.12.
```python
AGGREGATOR_SEARCH = {
    "weights": {"A": 1.0, "B": 0.6, "C": 0.3, "D": 0.1},
    "trigram_threshold": 0.3,   # word_similarity; «mesesr»→«messer» ≈ 0.43 (подтвердить в 20.0)
    "max_tokens": 8,
    "prefix_min_len": 3,        # префикс «brot:*» только для последнего слова длиной ≥3
    "max_results": 240,         # 10 страниц по 24 — глубже ранжированная выдача бессмысленна
}
```

### Р-4. FTS и опечатки: сначала FTS, триграммы — только если FTS ничего не нашёл ✅
- Режим определяется ОДИН раз за запрос: `mode = "fts" if fts_pool.exists() else "trigram"`, это +1 лёгкий запрос по GIN. От режима строятся вкладки, `presence`, чипы и выдача — иначе вкладки показали бы «0», а лента что-то нашла бы.
- Триграммный режим: `search_text__trigram_word_similar=q_folded` (оператор `%>`, использует индекс `gin_trgm_ops`) внутри `transaction.atomic()` + `SET LOCAL pg_trgm.word_similarity_threshold = <threshold>`. Сортировка — по `TrigramWordSimilarity` по убыванию.
- Почему не объединять FTS и триграммы всегда: триграммы шумят («Wiener Schnitzel» начнёт цеплять похожие блюда — регрессия `test_menu_listings.py:114`), а ранги двух шкал несопоставимы.
- `search_text` — новое `TextField(default="", editable=False)`. В нём свёрнутый (`fold`) текст: `lower` + ä→a, ö→o, ü→u, ß→ss по title во всех локалях, `business_name` и `dish_names`. Тизер не включаем: триграммный индекс держим маленьким. Индекс — `GinIndex(fields=["search_text"], opclasses=["gin_trgm_ops"], name="agg_search_text_trgm")`.
- Тот же `fold` применяется к запросу в Python. Поэтому «muller» находит «Müller». Расширение `unaccent` не нужно.

### Р-5. Синонимы: словарь в коде, запрос расширяется в Python ✅ (не thesaurus Postgres)
- Thesaurus Postgres требует файлов в `$SHAREDIR/tsearch_data` на сервере: не деплоится через git, и в CI-образ его не положить.
- ✅ Модуль `apps/aggregator/search_synonyms.py`:
  ```python
  GROUPS: tuple[tuple[str, ...], ...] = (
      ("handy", "smartphone", "mobiltelefon"),
      ("fahrrad", "rad", "velo", "e-bike"),
      ("brot", "brötchen", "backwaren"),   # stem «brot» ≠ «brotch»: связь только синонимом
      ("friseur", "frisör", "haarschnitt"),
      ...
  )
  def expand(token: str) -> tuple[str, ...]  # свёрнутый токен → группа (вкл. сам токен)
  ```
- Группы двусторонние, индекс строится при импорте модуля (`dict` свёрнутый токен → группа). Многословные синонимы и синонимы через дефис в v1 заменяются до токенизации: `e-bike` → `ebike`.
- Сопровождение ведётся в коде с замком: каждый термин в одной группе, без пустых групп и дублей.

### Р-6. Построение tsquery — безопасное
Токенизация: `re.findall(r"[^\W_]+", fold(q))[:max_tokens]` — только буквы и цифры, поэтому кавычки, `&`, `|`, `!`, `:` и SQL-спецсимволы в `to_tsquery` не попадают по построению.
```python
def build_query(q: str, *, lang: str) -> SearchQuery | None:
    # токены → для каждого: OR по synonyms.expand(tok) × configs(german, simple, ts_config(lang))
    # последний токен (len ≥ prefix_min_len) — raw-префикс f"{tok}:*"
    # между токенами — AND (&). Нет токенов → None (q игнорируется, см. §5)
```
Используются `SearchQuery(term, search_type="raw", config=cfg)`. Сырая строка — только `[a-z0-9…]+` с необязательным `:*`.

### Р-7. Сортировка
- С запросом по умолчанию: `-rank, -created_at, -pk` (`relevanz`). Без запроса — как сейчас: keyset по `-created_at`.
- `?sort=neu` с запросом: `-created_at`. «Рядом» (`lat`/`lng`) — `geo.nearest` по найденному, как сейчас.
- **Featured не поднимается (UWG §5a).** `SearchRank` от `featured_until` не зависит. Полоса «Anzeige» остаётся отдельной: `split_featured` по уже найденному пулу показывает только релевантные платные позиции и исключает их из органики (`views.py:226-245`). Порядок органики от оплаты не меняется — это проверяет замок.

### Р-8. Пагинация ранжированной выдачи — без правок шаблонов ✅
Новая `apps/core/pagination.py::paginate_ranked(qs, *, limit, cursor) -> Page`:
- курсор — тот же `_encode({"o": offset})`, то есть параметр `cursor` прежний;
- `Page.next_cursor` кодирует следующий сдвиг; `qs[o:o+limit+1]`; верхняя граница сдвига — `max_results`;
- курсор чужого формата (keyset `{"v","pk"}`) считается первой страницей.

Шаблоны `portal_home.html:87` и `search.html:13` не меняются.

### Р-9. Фильтры: `FeedScope` остаётся областью блоков, новые фильтры — в `SearchFilters` ✅
`FeedScope` (`portal_home_blocks.py:42-47`) — идентичность блока главной и ссылки «Alle →». Его семантику не раздуваем, только мягко расширяем `kat` (ниже). Новый frozen dataclass в `apps/aggregator/search.py`:
```python
@dataclass(frozen=True)
class SearchFilters:
    kats: tuple[str, ...] = ()        # ?kat=a&kat=b — ИЛИ (объединение keys_for_filter)
    tags: tuple[str, ...] = ()        # ?merkmal=a&merkmal=b — И (city_tags__contains=[...])
    district: str = ""                # ?stadtteil=<slug> (валидация districts.normalize(city, v))
    price_from: Decimal | None = None # ?preis_von= (views._money, немецкая запятая)
    price_to: Decimal | None = None   # ?preis_bis=
    date: tuple[datetime, datetime] | None = None  # ?datum=heute|wochenende|YYYY-MM-DD
    available: bool = False           # ?verfuegbar=1 → exclude(availability="sold_out")
    open_now: bool = False            # ?offen=1 (имя как у A8 city_listing)
    sort: str = ""                    # "" | "neu"
def parse_filters(request, *, city: str) -> SearchFilters
def apply_filters(qs, f: SearchFilters, *, now=None) -> QuerySet
def carry(q: str, f: SearchFilters) -> list[tuple[str, str]]  # для page_carry/base_qs/пилюль ✕
```

**URL и параметры:**
- `kat`: `category_facets.selected` → `selected_many(request)` на `getlist`, каждое значение проверяется по справочнику, мусор отбрасывается. `FeedScope.kat` = `kats[0]`, если значение одно, — чипы работают как раньше: раскрывают один раздел. Несколько значений — только через URL: ссылки блоков вроде «Essen & Lebensmittel» = `?kat=essen-gastronomie&kat=lebensmittel-getraenke`.
- Район: на портале путь `/stadtteil/<slug>/` (`portal_views.py:142-147`) имеет приоритет над `?stadtteil=`. Параметр нужен, чтобы сочетать район с поиском на корне и на `/entdecken/` (там `city` обязателен для валидации).
- Дата:
  - `heute` — [начало дня, конец дня), `wochenende` — Сб 00:00 … Пн 00:00 по Berlin, `YYYY-MM-DD` — один день;
  - фильтр «листинг действует в окне»: `(starts_at IS NULL OR starts_at < end) AND (ends_at IS NULL OR ends_at >= start)`;
  - фильтр ограничивает виды теми, у которых есть даты (`promotion`, `event`), — **развилка Р-О1 для владельца** (§2 конец). Альтернатива — не отсекать бездатные виды.
- `FEED_PARAMS` (`portal_home_blocks.py:31`) пополняется: `stadtteil, preis_von, preis_bis, datum, verfuegbar, offen, sort`. Пустые значения главную не ломают — это уже держит `test_empty_feed_params_keep_home`.
- Конфликт имён: hotel-портал использует `von`/`bis`/`gaeste` (`portal_views.py:233-236`), поэтому дата называется `datum`.

### Р-10. «Открыто сейчас» без N+1 ✅
- `_open_now_schemas` переезжает в `apps/aggregator/open_now.py` (`views` реэкспортирует для `city_listing`).
- В `apply_filters`: `schemas = qs.values_list("tenant_schema", flat=True).distinct()` (1 запрос) → `Tenant...values_list("schema_name", "opening_hours_structured")` (1 запрос) → `qs.filter(tenant_schema__in=open_set)`. Итого +2 запроса при `offen=1`, независимо от объёма данных.
- Бизнесы без часов в «открыто» не попадают — это честно.

### Р-11. Отсечка `ends_at`
Уже в `objects.public()` (`models.py:50-53`) и в `listings_for:131`. Поиск ВСЕГДА стартует от `listings_for(...)`, поэтому отдельной логики не нужно. Замок проверяет, что истёкшие не находятся ни в FTS-, ни в триграммном режиме.

### Р-12. Одна функция для обеих поверхностей + шов для T-8.21 ✅
```python
# apps/aggregator/search.py
@dataclass(frozen=True)
class SearchOutcome:
    qs: QuerySet          # отфильтрованный и упорядоченный пул (без featured-логики)
    mode: str             # "none" (без q) | "fts" | "trigram" | "empty"
    query: str            # нормализованный q
    ranked: bool          # True → paginate_ranked, False → keyset
def execute(base_qs, q: str, filters: SearchFilters, *, surface: str, lang: str) -> SearchOutcome
def match(qs, q: str, *, lang: str) -> QuerySet   # FTS-only, без ранга; для listings_for(q=)
def _record(outcome: SearchOutcome, *, surface: str, filters: SearchFilters) -> None:
    """Шов T-8.21: единственная точка, куда повесится журнал запросов/«ничего не найдено».
    Сейчас — no-op. Вызывается ровно один раз в execute() после определения mode."""
```
- `surface` ∈ {`"portal"`, `"entdecken"`} — для будущего журнала.
- `listings_for(q=)` (`views.py:122-129`) делегирует в `search.match`. Внешний контракт сохраняется для finder и тестов, правило сопоставления в проекте одно.
- `/entdecken/` переводим на тот же движок: в `discover_index` это `pool = listings_for(<без q>)` → `search.execute(pool, q, filters, surface="entdecken")`.

### Развилки для владельца
- **Р-О1. `?datum=` и бездатные виды.** Рекомендую: только виды с датами (событие/акция). «Что в эти выходные» — это вопрос про события.
- **Р-О2. Признаки списком: И или ИЛИ.** Рекомендую И (сужение: «vegan» и «bio»). Разделы — ИЛИ.
- **Р-О3. Начальный словарь синонимов.** Предлагаю ~40 групп по 15 разделам справочника. Владелец правит список в `search_synonyms.py` или присылает свой.

---

## 3. Миграции

### `0023_t8_20_search.py`
```python
from django.contrib.postgres.operations import TrigramExtension
from django.contrib.postgres.search import SearchVectorField
from django.contrib.postgres.indexes import GinIndex
operations = [
    TrigramExtension(),  # CREATE EXTENSION IF NOT EXISTS pg_trgm
    AddField("aggregatorlisting", "search_vector", SearchVectorField(null=True, editable=False)),
    AddField("aggregatorlisting", "search_text", TextField(default="", blank=True, editable=False)),
    AddIndex("aggregatorlisting", GinIndex(fields=["search_vector"], name="agg_search_vector_gin")),
    AddIndex("aggregatorlisting", GinIndex(fields=["search_text"], name="agg_search_text_trgm",
                                           opclasses=["gin_trgm_ops"])),
]
```

**django-tenants:**
- `aggregator` — SHARED, поэтому `migrate_schemas` применяет миграцию только к public. Расширение создаётся в схеме `public`.
- django-tenants выставляет `search_path = <tenant>, public`, так что `gin_trgm_ops` и функции доступны и из запросов в tenant-контексте. Синк пишет в public явно — проблем нет.
- Тесты: `config/settings/test.py` делает все приложения SHARED, pytest-django мигрирует одну public-БД, на CI роль `postgres` — суперпользователь.
- ⚠️ `--reuse-db` локально: после этой миграции один раз прогнать с `--create-db`.

**`django.contrib.postgres`:** добавить в `SHARED_APPS` (`base.py:17-47`). Своих моделей и миграций у приложения нет; оно регистрирует лукапы `trigram_word_similar` и `search`. Без него остались бы только функции.

Индексы на пилотном объёме (сотни–тысячи строк) строятся за секунды, `CONCURRENTLY` не нужен (§6).

### `0024_t8_20_search_backfill.py` — RunPython
Вызывает `search_index.refresh(AggregatorListing.objects.all(), batch=500)` (импорт рабочего модуля — осознанно: «перестроить по текущему правилу», комментарий в миграции); reverse — `noop`.

Дублирующая команда `python manage.py rebuild_search_index [--schema X]` нужна для смены правила индекса (новая локаль, новые поля) без миграции.

---

## 4. Инкременты (батч-режим: локальный гейт на каждом шаге, один прогон CI на верхушке)

### 20.0 — Спайк и замки до кода (тесты + заметки, без прод-кода)
- Проверить на CI-образе:
  - `to_tsvector('german','Brötchen Messern')` → ожидается `'brotch'`, `'mess'` (немецкий snowball снимает умлауты);
  - `word_similarity('mesesr','messer')` ≥ 0.3;
  - `to_tsquery('german','der')` с ИЛИ `simple` не роняет запрос.
- Числа закрепить в плане (порог — в настройки).
- Написать красные замки из §5.

### 20.1 — Индекс (миграции + заполнение)
Новый модуль `apps/aggregator/search_index.py`:
```python
def fold(text: str) -> str                               # lower + ä/ö/ü→a/o/u, ß→ss
def fold_expr(expr) -> Func                               # то же в SQL: Lower + Replace×4
def extra_text(city, district, city_category, category) -> str
    # подписи раздела/категории (de+en через translation.override), тема события, имя района
def vector_expr(extra: str) -> CombinedExpression
    # Σ SearchVector(KeyTextTransform(loc,"title"), config=ts_config(loc), weight="A") по LANGUAGES
    # + SearchVector("business_name", config="german"/"simple", weight="B")
    # + SearchVector(Cast("dish_names", TextField()), config="german", weight="B")
    # + Σ teaser по локалям weight="C" + SearchVector(Value(extra), config="german", weight="C")
    # + SearchVector(Cast("city_tags", TextField()), config="simple", weight="C")
    # + SearchVector("city", config="simple", weight="D")
def text_expr() -> Func   # fold_expr(title по локалям || business_name || dish_names)
def refresh(qs, *, batch: int | None = None) -> int
    # combos = qs.values("city","district","city_category","category").distinct()  (1 запрос)
    # для каждого combo: qs.filter(**combo).update(search_vector=vector_expr(extra_text(**combo)),
    #                                              search_text=text_expr())       (k UPDATE)
```
- Подписи района и категории передаются как `Value(...)` прямо в выражение, а не через отдельную колонку: Postgres в `UPDATE SET b=f(a)` видит СТАРОЕ значение `a`.

**Точки вызова:**
- `models.py:181-186` `AggregatorListing.save()`: после `super().save()` → `search_index.refresh(type(self).objects.filter(pk=self.pk))`. Пропускать, если в `update_fields` нет индексируемых полей. Покрывает все 8 `update_or_create` в `tasks.py` (`:160,231,334,396,751,952,1025,1075`), админку и `objects.create` в тестах. Стоимость: +2 запроса на синк в Celery.
- `tasks.py:821-838` `refresh_tenant_fields`: в конце `search_index.refresh(AggregatorListing.objects.filter(tenant_schema=...))`.
- Команда `apps/aggregator/management/commands/rebuild_search_index.py`.
- `reconcile_schema` (`tasks.py:586-677`) отдельного вызова не требует: работает через `sync_*` → `save()`.

**Замки:** вектор заполнен после каждого `sync_*`; правка имени бизнеса через `refresh_tenant_fields` обновляет вектор; `.update()` счётчиков featured вектор не трогает.

### 20.2 — Движок `apps/aggregator/search.py` + `search_synonyms.py` + `paginate_ranked`
- `tokenize`, `build_query` (Р-6), `match`, `rank_order`, `trigram_match` (с `SET LOCAL`), `execute` (Р-12), `_record` (no-op).
- `listings_for(q=)` (`views.py:122-129`) → `qs = search.match(qs, q, lang=get_language())`.
- `apps/core/pagination.py`: `paginate_ranked` (Р-8).
- **Бюджет запросов на одну выдачу с `q`:** `exists` режима (1) + выборка страницы (1, LIMIT ≤ 25) + featured (≤2) + рейтинги (1) + чипы/`presence` (как сейчас). Итого прирост +1 к текущему.

### 20.3 — Фильтры
- `SearchFilters`, `parse_filters`, `apply_filters`, `carry` в `search.py`.
- `category_facets.selected_many(request)` (новая функция рядом с `:17-25`, `selected` оставить).
- `open_now.py` (перенос из `views.py:174-193`).
- `portal_home_blocks.py:31` — расширить `FEED_PARAMS`; `parse_scope` (`:136-144`) берёт `kat` из `selected_many` (первое значение, если одно).

### 20.4 — Портал
`portal_views.portal_home` (`:118-326`):
- `q` и фильтры разбираются один раз; лимит `portal-search` (`:168-178`) срабатывает при `q` ИЛИ любом фильтре из `SearchFilters`.
- `whole_pool = listings_for(... без q ...)` → `outcome = search.execute(whole_pool, q, filters, surface="portal", lang=...)` и дальше всё от `outcome.qs` (`presence`/вкладки/чипы `:193-213`).
- `paginate_ranked`, если `outcome.ranked`, иначе прежний keyset (`:219-222`).
- `page_carry` (`:299-311`) ← `search.carry(q, filters)` + `kind`/`neu`.

Шаблоны:
- новый `templates/aggregator/_portal_filters.html`: `<details>` без JS — Stadtteil (только районы с данными, `_district_choices` `portal_views.py:64-82`), Preis von/bis, Datum (Heute/Wochenende/Datum), «Nur verfügbare», «Jetzt geöffnet», Sortierung (Relevanz/Neueste); пилюли активных фильтров с ✕ (паттерн OS-1);
- `_portal_search.html` переносит активные фильтры hidden-полями — иначе новый `q` их сбросит.

Плюс: `npm run build:css`, новые msgid × 5 `.po`, `scripts/i18n_quickcheck.py`.

### 20.5 — `/entdecken/`
`views.discover_index` (`:330-478`):
- `pool`/`chips_base` без `q` → `search.execute(..., surface="entdecken")`;
- ранжирование + `paginate_ranked` (`:425-427`);
- `base_qs` (`:430-450`) дополняется `carry`; в `search.html` те же поля фильтров (партиал общий с порталом, если разметка совпадает, иначе тонкая копия формы).

### 20.6 — Стенд и доводка
- Playwright-стенд на демо Золингена (`solingen.<base>`): опечатка, синоним, фильтры, «Weitere», мобильный 390px.
- Сравнить `EXPLAIN ANALYZE` FTS- и триграммного запроса на пуле демо (~20 бизнесов, ~1500 листингов).
- Запись в `build-log.md`, `task-catalog.md`, CLAUDE.md §3.

Независимые шаги: 20.3 можно вести параллельно 20.2 (разные функции одного модуля — лучше последовательно); 20.4 и 20.5 последовательны, общий партиал.

---

## 5. Тесты — `apps/aggregator/tests/test_unified_search.py`
Листинги создаются через `objects.create`, вектор заполняет хук `save()`.

| # | Замок | Ожидание |
|---|---|---|
| 1 | Стемминг | `q="Messern"` находит «Messer Santoku»; `q="Brötchen"` находит «Brötchen»; `q="brot"` (префикс) находит «Brötchen» и «Brot». `q="Brötchen"` НЕ обязан находить «Brot» — их связывает только синоним (если «brot/brötchen» в словаре — находит; замок фиксирует выбранное поведение) |
| 2 | Опечатка | `q="Mesesr"` → FTS 0 → триграммы находят «Messer», `outcome.mode == "trigram"` |
| 3 | Опечатка не шумит при попадании FTS | `q="Messer"` при наличии «Messe Köln» — режим `fts`, «Messe» не в выдаче |
| 4 | Синоним | `q="Handy"` находит листинг «Smartphone-Reparatur»; обратно тоже |
| 5 | Веса | A: «Messer» в title; B: в teaser → A выше B; изменение `AGGREGATOR_SEARCH["weights"]` через `override_settings` меняет порядок без переиндексации |
| 6 | UWG §5a | featured-листинг с более низким рангом не поднимается в органике; виден только в полосе «Anzeige» и только если соответствует запросу |
| 7 | Фильтры по одному | `kat` (раздел; категория; два значения = ИЛИ), `merkmal` (два = И), `stadtteil`, `preis_von`/`preis_bis` (вкл. «45,50»), `datum=heute`/`wochenende`/дата, `verfuegbar=1`, `offen=1` |
| 8 | Фильтры вместе | `q` + `kat` + `stadtteil` + `preis_bis` + `offen` — пересечение |
| 9 | «Открыто сейчас» | бизнес с часами «сейчас открыт» — да; закрыт — нет; без часов — нет; `freezegun`/фиксированное `now` |
| 10 | Невидимые | скрытый (`hidden_at`), `is_active=False`, `withheld`, демо на настоящем портале, истёкший `ends_at`, прошедшее событие не находятся ни в `fts`, ни в `trigram` |
| 11 | Мультиязычность | ru-title «Свежий хлеб» находится по `q="хлеба"` (russian-стемминг) при `translation.override("ru")`; de-запрос по de-title при ru-языке посетителя — тоже (german всегда в ИЛИ) |
| 12 | Пустой запрос | `q=""` / `q="   "` → поведение как без поиска (главная портала; индекс `/entdecken/`) |
| 13 | Мусор и длина | `q="!!!:*&|"` — 200, без 500, `mode == "empty"` или выдача без фильтра (зафиксировать); `q` длиной 500 обрезается до 100, токенов ≤ 8 |
| 14 | Спецсимволы SQL | `q="'; DROP TABLE x; --"` → 200, таблица цела, ищется «drop»/«table» |
| 15 | Число запросов | лента портала с `q` + 3 фильтрами: `django_assert_max_num_queries(N)` (N фиксируем в 20.0), не растёт при +30 листингах |
| 16 | Паритет поверхностей | одинаковые `q` + фильтры на портале Solingen и `/entdecken/?city=Solingen` дают одинаковый набор `pk` (без featured) |
| 17 | Пагинация | 30 совпадений → первая страница 24 по рангу, `cursor` → оставшиеся 6, без дублей; курсор keyset-формата на ранжированной выдаче = страница 1 |
| 18 | Шов T-8.21 | `search._record` вызывается ровно один раз на запрос с `q` (mock), с `surface`/`mode` |
| 19 | Rate-limit | фильтр без `q` тоже упирается в `portal-search`/`entdecken-search` |
| 20 | Индекс | `refresh_tenant_fields` после смены имени бизнеса → `q=<новое имя>` находит; `sync_*` заполняет вектор у всех 7 видов |

**Регрессия, должна остаться зелёной без правок:**
- `test_search.py:35-63` («müller», «grillpaket», «hilden» — город в весе D);
- `test_menu_listings.py:107-114` (Rinderfilet да / «Wiener Schnitzel» нет — FTS-only `match`);
- `test_portal_discover.py:317-335` (поиск товаров, перенос `q`, лимит), `:340-349` (≤14 запросов на главной без `q`), `:417-432`;
- `test_city_categories.py`, `test_districts_portal.py`, `test_kind_filter.py`, `test_featured.py`.

Гейт перед пушем: `ruff check .`, `ruff format --check .` (целиком), `pytest apps/aggregator apps/core/tests/test_template_comments.py --reuse-db` (после 0023 — `--create-db`), `scripts/i18n_quickcheck.py`, `npm run build:css` при новых классах.

---

## 6. Риски и чего НЕ делаем

**Риски:**
- **Размер индекса.** 11 локалей × title/teaser. Сейчас у большинства листингов заполнены только de (+ en/ru/uk/tr у демо). Пустые локали дают пустой tsvector, вклад нулевой. Ожидаемо ≈ 1–3 КБ вектора на строку. При росте пула до 100k+ — свести не-de локали в одну `simple`-часть (Р-2, запасной вариант).
- **Стоимость записи.** +2 запроса на синк в Celery, а `refresh_tenant_fields` даёт k UPDATE по числу комбинаций. На пилоте несущественно.
- **Расширение `pg_trgm` на внешнем Postgres.** Нужна роль-владелец БД (trusted с PG13). Добавить в чек-лист Stage 0 (вынос Postgres).
- **Конфигурации tsearch на CI и проде.** Встроены в любой сборке Postgres 16, alpine тоже — проверяем в спайке 20.0. У `uk`/`pl` стемминга нет (`simple`): ру-подобное словоизменение украинского не ловится — ограничение v1.
- **Триграммы и `SET LOCAL`.** Работают только внутри транзакции: обёртка в `atomic()`. При пуле соединений без транзакций (PgBouncer transaction mode) `SET LOCAL` корректен, `SET` — нет; используем только `LOCAL`.
- **Хук `save()` и `bulk_create`.** Если где-то появится `bulk_create`/`.update()` индексируемых полей, вектор устареет. Защита: команда `rebuild_search_index` + замок «каждый `sync_*` заполняет вектор» + комментарий у модели.
- **Импорт рабочего кода в data-миграции.** Осознанно: «перестроить по текущему правилу», комментарий в миграции.
- **Ранг на «Weitere».** Offset-пагинация может дать дубль или пропуск, если листинг обновился между страницами. Для поиска приемлемо, глубина ограничена 240.
- **Кэш.** Запросы с параметрами `cache_public_page` не кэширует — это защищают лимиты частоты. Главная без query кэшируется как раньше.

**НЕ делаем:**
- T-8.21 — журнал запросов и «ничего не найдено». Оставляем только шов `search._record`.
- T-8.10d — ИИ-поиск фразой, подписка на запрос.
- Внешние движки (Meilisearch, Elasticsearch) и thesaurus/ispell-словари на сервере.
- Поиск внутри витрин тенантов (UB2-2 — отдельный механизм).
- Подсветка совпадений (`ts_headline`), автодополнение и подсказка «Meinten Sie …» — кандидаты v2.
- Операторский UI весов и синонимов — T-8.12.
- Радиусный фильтр по расстоянию: «рядом» остаётся сортировкой.

## Ключевые файлы
- Новые:
  - `apps/aggregator/search.py`, `search_index.py`, `search_synonyms.py`, `open_now.py`;
  - `management/commands/rebuild_search_index.py`;
  - `migrations/0023_t8_20_search.py`, `0024_t8_20_search_backfill.py`;
  - `templates/aggregator/_portal_filters.html`;
  - `tests/test_unified_search.py`.
- Правятся:
  - `apps/aggregator/models.py` (`:57-186` — поля, `Meta.indexes`, `save`);
  - `views.py` (`:49-132`, `:174-193`, `:330-478`);
  - `portal_views.py` (`:118-326`);
  - `portal_home_blocks.py` (`:31`, `:136-144`);
  - `category_facets.py` (`:17-25`);
  - `tasks.py` (`:821-838`);
  - `apps/core/pagination.py`;
  - `config/settings/base.py` (`SHARED_APPS` + `AGGREGATOR_SEARCH`);
  - `templates/aggregator/_portal_search.html`, `search.html`;
  - `locale/*/LC_MESSAGES/django.po`.

## Решения владельца (2026-10-15)
- Р-О1: `?datum=` — только виды с датами (события, акции). ✅
- Р-О2: несколько `?merkmal=` — И (сужение); разделы `?kat=` — ИЛИ. ✅
- Р-О3: стартовый словарь синонимов составляет исполнитель (≈40 групп по 15 разделам). ✅
