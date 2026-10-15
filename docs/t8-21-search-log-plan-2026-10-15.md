# План реализации T-8.21: журнал поисковых запросов каталога города

> Сохранить как `docs/t8-21-search-log-plan-2026-10-15.md`. Задача описана в `docs/t8-roadmap-2026-10-10.md:41` и `docs/tz-siteadaptor-2-0-phase0-2026-10-10.md:63` (решение В5 — `:95`). Шов подготовлен в `docs/t8-20-unified-search-plan-2026-10-15.md:180-195, :370`.

## 0. Кратко
Пишем агрегатную SHARED-модель `aggregator.SearchQueryLog`: одна строка на «день × поверхность × портал × город × язык × запрос × фильтры», в ней счётчики `searches`, `zero_results` и `trigram_hits`. Запись идёт синхронно внутри `search.record()`, по образцу «UPDATE F()+1, при промахе CREATE» из `promotions/channels.py:30-37`, и не может уронить поиск. Персональных данных журнал не хранит: ни IP, ни пользователя, ни сессии, ни user-agent, ни точного времени запроса. E-mail, телефоны и IBAN вычищаются из текста запроса до записи. Смотрит журнал только суперпользователь платформы, в unfold-админке на public: фильтры, «Nichts gefunden», экспорт в CSV. Старые строки удаляет beat-задача по сроку хранения. Нужна миграция `aggregator/0025` (SHARED, аддитивная).

---

## 1. Текущее состояние

### 1.1 Шов
- `apps/aggregator/search.py:302-308`: `SearchOutcome(qs, mode, query, ranked, filters)`. `mode` принимает значения `none|fts|trigram|empty`.
- `search.py:311-352`, функция `execute(..., surface, lang="", track=True)`. При `track` она зовёт `record(outcome, surface=surface)` (`:350-351`). Язык вычисляется в `:322`, но в `outcome` не попадает.
- `search.py:355-363`, функция `record()`: возвращается, если нет ни `query`, ни `filters.active`, иначе ничего не делает.
- `search.py:157-180`, `SearchFilters`. `active` не учитывает `sort`, и это правильно: сама по себе сортировка поиском не является.

### 1.2 Где вызывается
| Поверхность | Место | Что известно |
|---|---|---|
| portal | `portal_views.py:197-208`: `execute(..., track=False)` (широкий пул без вида и категорий) | — |
| portal | `portal_views.py:233-236`: явный `record(SearchOutcome(pool, broad.mode, q, broad.ranked, filters), surface="portal")` | `pool` уже сужен видом, scope и категориями, то есть совпадает с тем, что видит посетитель. `request.portal` (host, city). После резолва фасета (`:158-161`) `city` может прийти и из сегмента пути. |
| entdecken | `views.py:402`: `execute(pool_base, q, filters, surface="entdecken")` (track=True) | `city` берётся из `?city=` (`:335`) как свободный текст. |
| entdecken | `views.py:417-419`: `execute(..., track=False)` для чипов | не пишем, это уже сделано |

Важно: **курсор следующих страниц.** `cursor` в portal читается в `:242`, в entdecken — в `:425`. Сейчас `record` срабатывает и на `?cursor=…`, поэтому листание выдачи раздувало бы счётчик. Решение — писать только первую страницу (см. Р-6).

Кэш: `@cache_public_page` не кэширует GET с параметрами (`apps/core/pagecache.py:201`), так что запросы с `q` всегда доходят до вьюхи и `record`. Лимит частоты на IP уже действует: `portal_views.py:178-187` (`portal-search`) и `views.py:383-389` (`entdecken-search`).

### 1.3 Что знает `record` и что ему не хватает
- Знает: `qs`, `mode`, `query`, `filters`, `surface`.
- Не знает: город, хост портала, язык, номер страницы. Объект `request` он не получает, и **так и должно остаться**: это структурный замок против утечки персональных данных (Р-2).
- Число результатов. `qs.count()` по ранжированному набору (fts с `SearchRank`, trigram с `CASE`) обходится в отдельный запрос. Решение — ограниченный подсчёт (Р-5).

---

## 2. Решения

### Р-1. Агрегат, а не лента событий ✅ (рекомендация)
Одна строка на ключ `(day, surface, portal_host, city, lang, query_norm, filters_key)` со счётчиками.
- Плюсы: таблица растёт по числу уникальных запросов в день, а не по трафику. Время внутри дня не хранится, поэтому восстановить сессию невозможно даже теоретически, и минимизация данных по DSGVO соблюдается без хэширования. «Топ» и «Nichts gefunden» считаются простыми `SUM`/`ORDER BY`.
- Минусы: теряем порядок и время внутри дня и не видим цепочку «запрос → уточнение». Для задачи это приемлемо.
- Отвергнуто: строка на каждое событие. Неограниченный рост таблицы, и метка времени вместе с текстом запроса уже почти персональные данные.

### Р-2. Персональные данные: не храним, а не хэшируем ✅
- В модели нет полей IP, user, session, user-agent, referer и точного времени. `updated_at` хранить не стоит, достаточно `day`.
- `record()` по сигнатуре не принимает `request`. Контекст приходит только примитивами `city: str` и `portal_host: str`.
- **Очистка текста запроса** (`scrub()`). Посетители иногда вставляют в поиск e-mail или телефон, поэтому:
  - e-mail (`\S+@\S+\.\w+`) заменяется на `‹email›`;
  - последовательность из 7 и более цифр, в том числе с пробелами, `+`, `/` и `-`, заменяется на `‹nummer›`. Почтовый индекс из 5 цифр и цены («2,50») остаются;
  - похожее на IBAN (`[A-Z]{2}\d{2}[A-Z0-9 ]{10,}`) заменяется на `‹iban›`.
  Замена на токен лучше пропуска: факт «люди ищут телефон» тоже полезен.
- `city` для entdecken — свободный текст из `?city=`. Его нормализуем так же: casefold, сжатие пробелов, обрезка до 100 символов и тот же `scrub()`.

### Р-3. Синхронная запись, с полной защитой от сбоев ✅
- Пишем прямо в запросе, по прецеденту `promotions/channels.py:30-37`:
  1. `rows.filter(key).update(searches=F+1, zero_results=F+z, trigram_hits=F+t, last_mode=..., last_results=...)`. На повторный ключ за день это 1 запрос.
  2. Если обновлено 0 строк, выполняется `transaction.atomic(): create(...)`. При `IntegrityError` (параллельный первый запрос) — повторный `update`.
- Всё это обёрнуто в `transaction.atomic()` (savepoint), а снаружи в `try/except Exception → logger.warning(..., exc_info=True)`. Сбой журнала откатывает только savepoint и поиск не ломает. `ATOMIC_REQUESTS` в проекте не используется (в `config/settings` ничего не найдено), но savepoint защищает и на случай будущего вызова внутри транзакции.
- Почему не `bulk_create(update_conflicts=True)`: он подставляет значения из `EXCLUDED`, а инкремент через `F()` ему не выразить.
- Почему не сырой `INSERT ... ON CONFLICT DO UPDATE SET searches = t.searches + 1`: это тоже один запрос, но выбивается из стиля проекта. Допустимая оптимизация на будущее (§6).
- Отвергнуто: буфер в Redis (`HINCRBY`) со сбросом по beat раз в 5 минут. Меньше записей в БД, но данные теряются при сбросе или вытеснении Redis, нужна вторая beat-задача и сериализация ключа. Объём уже ограничен rate-limit'ом (60 запросов в минуту на IP), а масштаб — город Золинген. Не окупается.

### Р-4. Нормализация запроса ✅
Функция `normalize_query(q)`: NFC, `casefold()`, сжатие пробельных символов в один пробел, `strip()`, затем `scrub()` и обрезка до 100 символов (`QUERY_MAX = 100`, в пару к `SEARCH_MAX`). Умляуты не сворачиваем (`fold()` из `search_index` не используем): журнал читает человек, «Brötchen» должен остаться читаемым.

### Р-5. Число результатов: ограниченный подсчёт, 1 запрос ✅
```python
def _count_capped(qs, cap: int) -> int:
    return len(qs.order_by().values_list("pk", flat=True)[: cap + 1])
```
- `cap = AGGREGATOR_SEARCH["max_results"]` (240). Значение `241` в отчёте означает «больше 240».
- `values_list("pk")` отбрасывает аннотации `rank`/`similarity_pos`, а `order_by()` убирает сортировку. Получается простой `SELECT pk … LIMIT 241`, дешевле `COUNT(*)` с ранжированием.
- В режиме `mode == "empty"` подсчёт пропускаем: `qs` там `.none()`, результат 0 и без запроса.
- Отвергнуто: только `exists()`. Тогда в отчёте не видно «нашлось 1–2», а это тоже сигнал. Цена — тот же один запрос.
- Известное отклонение: портал отелей дополнительно фильтрует выдачу по датам **после** `record` (`portal_views.py:252-275`). Счётчик показывает выдачу до проверки наличия. Фиксируем в docstring.

### Р-6. Что считается «поиском» и мусор ✅
`record()` пишет, когда выполнены все условия:
- `enabled`;
- есть `query` или `filters.active`;
- это первая страница (`first_page=True`). Вызывающий передаёт `not cursor`;
- `len(query_norm) >= min_len` (2) **или** `query_norm == ""` при активных фильтрах (поиск только фильтрами — законный случай).

Запрос из одних спецсимволов (`mode == "empty"`) пишем: он попадает в `zero_results` и виден в отчёте с `last_mode=empty`. Отдельной таблицы не заводим, админка фильтрует по `last_mode`. Одиночный символ («a») отбрасывается порогом `min_len`.

### Р-7. Фильтры в ключе ✅
- `filters_key` — каноническая строка из `search.carry("", filters)`, отсортированная, через `urlencode`, обрезанная до 255 символов. Например `kat=essen&merkmal=bio&stadtteil=ohligs`.
- `price_from/price_to` округляем до целых евро, иначе «2.49» и «2.50» размножили бы строки. Значение `sort` в ключ не входит: на поиск оно не влияет.
- `filters` (JSON) — тот же набор словарём, только непустые значения. Нужен для отображения.

### Р-8. Срок хранения ✅
Ежесуточная beat-задача удаляет строки с `day < today - retention_days`. По умолчанию 180 дней: хватает на полугодовой сезон. Значение настраивается через env, по прецедентам `RESERVATION_PII_RETENTION_DAYS` и `DOCUMENT_RETENTION_DAYS` (`config/settings/base.py:514-518`). Обход схем тенантов не нужен: таблица SHARED.

### Р-9. Только платформа ✅ (зафиксировать явно)
- Админка Django существует только в `urls_public`, а владельцы бизнеса — пользователи схемы тенанта, а не персонал public. Дополнительно `has_view_permission` и `has_module_permission` возвращают `request.user.is_superuser`: даже обычный staff журнал не видит.
- В кабинете тенанта нет ни вьюх, ни nav-записей, ни шаблонов журнала. Аналитика владельца («популярные запросы по его объектам») — отдельная задача T-8.8.

---

## 3. Модель

`apps/aggregator/models.py` — новый класс после `ListingReport` (`:246-285`).

```python
class SearchQueryLog(models.Model):
    """T-8.21: журнал поиска каталога города — АГРЕГАТ «день × запрос × город × поверхность».

    Без персональных данных: ни IP, ни пользователя, ни сессии, ни времени внутри
    дня (Р-2). Только для платформы (админка public, суперпользователь). Пишет
    `search.record()`, чистит beat `purge_search_log` (retention).
    """
    SURFACE_PORTAL = "portal"; SURFACE_ENTDECKEN = "entdecken"
    SURFACES = [(SURFACE_PORTAL, _("Stadtportal")), (SURFACE_ENTDECKEN, _("Entdecken"))]
    MODES = [("none", ...), ("fts", ...), ("trigram", ...), ("empty", ...)]

    day = models.DateField()
    surface = models.CharField(max_length=12, choices=SURFACES)
    portal_host = models.CharField(max_length=253, blank=True, default="")  # не FK: строка в ключе, NULL ломал бы unique
    city = models.CharField(max_length=100, blank=True, default="")
    lang = models.CharField(max_length=8, blank=True, default="")
    query_norm = models.CharField(max_length=100, blank=True, default="")
    filters_key = models.CharField(max_length=255, blank=True, default="")
    filters = models.JSONField(default=dict, blank=True)
    searches = models.PositiveIntegerField(default=0)
    zero_results = models.PositiveIntegerField(default=0)
    trigram_hits = models.PositiveIntegerField(default=0)   # нашлось только опечатками → кандидат в синонимы
    last_mode = models.CharField(max_length=10, choices=MODES, default="none")
    last_results = models.PositiveIntegerField(default=0)    # ≤ max_results+1

    class Meta:
        ordering = ["-day", "-searches"]
        constraints = [models.UniqueConstraint(
            fields=["day", "surface", "portal_host", "city", "lang", "query_norm", "filters_key"],
            name="agg_searchlog_uniq")]
        indexes = [models.Index(fields=["-day", "-zero_results"], name="agg_searchlog_zero_idx")]
```
- Уникальный индекс начинается с `day`, поэтому покрывает и фильтр периода, и purge.
- `portal_host` хранится строкой, а не FK. В FK с NULL Postgres считает NULL различными, и уникальность не сработала бы. Плюс после удаления портала история сохраняет его хост.
- Подписи (`verbose_name`, choices) — немецкие msgid через `gettext_lazy`. Добавить их во все 5 `.po`, иначе упадёт гейт i18n (`scripts/i18n_quickcheck.py`).

**Миграция** `apps/aggregator/migrations/0025_t8_21_search_log.py`: `CreateModel`, зависит от `0024_t8_20_search_backfill`. SHARED, аддитивная, data-шага нет. Сгенерировать через `makemigrations aggregator --name t8_21_search_log`. Проверить, что в неё не попал дрейф снимков других моделей. В CLAUDE.md §3 — пометка «⚠️ ЖДЁТ ДЕПЛОЯ».

---

## 4. Код

### 4.1 Новый модуль `apps/aggregator/search_log.py`
В `search.py` логику журнала не кладём: там уже около 360 строк движка, а журнал — отдельная ответственность. `search.record()` остаётся тонким швом и делегирует сюда (импорт ленивый, внутри функции).

```python
logger = logging.getLogger(__name__)
QUERY_MAX = 100
_EMAIL = re.compile(r"\S+@\S+\.\w+"); _PHONE = re.compile(r"\+?\d[\d \-/]{5,}\d"); _IBAN = ...

def _cfg(key): return settings.AGGREGATOR_SEARCH_LOG[key]
def scrub(text: str) -> str: ...                      # Р-2
def normalize_query(q: str) -> str: ...                # Р-4
def normalize_city(city: str) -> str: ...
def filters_key(f: SearchFilters) -> tuple[str, dict]: ...   # Р-7: (key, json)
def _count_capped(qs, cap: int) -> int: ...            # Р-5

def log(outcome, *, surface: str, city: str = "", portal_host: str = "",
        lang: str = "", first_page: bool = True) -> None:
    """Fail-safe: никакое исключение не выходит наружу (Р-3)."""
    try:
        _log(outcome, surface=..., ...)
    except Exception:
        logger.warning("search log write failed", exc_info=True)

def _log(...):
    if not _cfg("enabled") or not first_page: return
    query = normalize_query(outcome.query)
    if not (query or outcome.filters.active): return
    if query and len(query) < _cfg("min_len"): return
    results = 0 if outcome.mode == "empty" else _count_capped(outcome.qs, settings.AGGREGATOR_SEARCH["max_results"])
    key, fjson = filters_key(outcome.filters)
    ident = dict(day=timezone.localdate(), surface=surface, portal_host=portal_host[:253],
                 city=normalize_city(city), lang=(lang or "")[:8], query_norm=query, filters_key=key)
    deltas = dict(searches=F("searches") + 1,
                  zero_results=F("zero_results") + (results == 0),
                  trigram_hits=F("trigram_hits") + (outcome.mode == "trigram" and results > 0),
                  last_mode=outcome.mode, last_results=results)
    with transaction.atomic():
        rows = SearchQueryLog.objects.filter(**ident)
        if rows.update(**deltas): return
        try:
            with transaction.atomic():
                SearchQueryLog.objects.create(**ident, filters=fjson, searches=1,
                    zero_results=int(results == 0), trigram_hits=..., last_mode=..., last_results=results)
        except IntegrityError:
            rows.update(**deltas)

def purge(*, today=None) -> int:
    cutoff = (today or timezone.localdate()) - timedelta(days=_cfg("retention_days"))
    deleted, _ = SearchQueryLog.objects.filter(day__lt=cutoff).delete()
    return deleted
```
Поскольку у модели нет FK и каскадов, `delete()` превращается в один `DELETE`. Батчи не нужны, с ростом таблицы можно добавить.

### 4.2 `apps/aggregator/search.py`
- `SearchOutcome` (`:302-308`) получает поле `lang: str = ""`, `execute` заполняет его значением из `:322`. Поле со значением по умолчанию, поэтому явный конструктор в `portal_views.py:234` не ломается.
- `execute` (`:311-319`) получает keyword-аргументы `city: str = ""` и `portal_host: str = ""` и пробрасывает их в `record`.
- `record` (`:355-363`) получает новую сигнатуру:
  ```python
  def record(outcome: SearchOutcome, *, surface: str, city: str = "",
             portal_host: str = "", first_page: bool = True) -> None:
      if not (outcome.query or outcome.filters.active):
          return
      from . import search_log
      search_log.log(outcome, surface=surface, city=city, portal_host=portal_host,
                     lang=outcome.lang, first_page=first_page)
  ```
  Аргумента `request` нет, это замок Р-2.

### 4.3 `apps/aggregator/portal_views.py:233-236`
```python
search_engine.record(
    search_engine.SearchOutcome(pool, broad.mode, q, broad.ranked, filters, lang=broad.lang),
    surface="portal",
    city=city or "",                  # после резолва фасета (:158-161)
    portal_host=portal.host,
    first_page=not request.GET.get("cursor"),
)
```

### 4.4 `apps/aggregator/views.py`
- `:425`: чтение `cursor = request.GET.get("cursor")` поднять **выше** `:402`.
- `:402`: `search.execute(pool_base, q, filters, surface="entdecken", city=city)`. Отдельный kwarg `first_page` в `execute` не заводим, пропускаем через `track`:
  ```python
  outcome = search.execute(pool_base, q, filters, surface="entdecken", city=city, track=not cursor)
  ```
  `track=False` и так означает «не писать», то есть семантика остаётся одна.

### 4.5 Настройки `config/settings/base.py`
Рядом с `AGGREGATOR_SEARCH` (`:252-258`):
```python
# T-8.21: журнал поиска каталога города (без персональных данных, только для платформы).
AGGREGATOR_SEARCH_LOG = {
    "enabled": env.bool("SEARCH_LOG_ENABLED", default=True),
    "retention_days": env.int("SEARCH_LOG_RETENTION_DAYS", default=180),
    "min_len": 2,
}
```
Beat — в `CELERY_BEAT_SCHEDULE` после `purge-expired-documents` (`:473-476`):
```python
"purge-search-log": {
    "task": "apps.aggregator.tasks.purge_search_log",
    "schedule": 86400.0,  # раз в сутки — журнал поиска старше SEARCH_LOG_RETENTION_DAYS (T-8.21)
},
```
Учесть, что `DatabaseScheduler` синхронизирует расписание при старте beat.

### 4.6 `apps/aggregator/tasks.py`
По образцу `roll_aggregator_event_groups` (`:444-447`):
```python
@idempotent_task()
def purge_search_log():
    """Beat (раз в сутки): удалить агрегаты журнала поиска старше retention (T-8.21)."""
    from . import search_log
    return search_log.purge()
```
Задача работает на public, `schema_context` не нужен (прецедент `refresh_google_ratings`, `base.py:493-498`). Совместимость `idempotent_task` с beat без kwargs проверить по `apps/core/jobs.py`. Если дедуп требует ключа, использовать `@shared_task`, как `purge_expired_documents` (`apps/documents/tasks.py:22-29`).

### 4.7 Админка `apps/aggregator/admin.py`
Новый класс после `ListingReportAdmin` (`:94-130`), стиль unfold `ModelAdmin`:
```python
class PeriodFilter(admin.SimpleListFilter):          # 7 / 30 / 90 Tage  → day__gte
class ResultFilter(admin.SimpleListFilter):          # "Nichts gefunden" (zero_results>0) /
                                                     # "Immer ohne Treffer" (zero_results=F("searches")) /
                                                     # "Nur Tippfehler-Treffer" (trigram_hits>0)

@admin.register(SearchQueryLog)
class SearchQueryLogAdmin(ModelAdmin):
    list_display = ("day", "query_norm", "surface", "city", "portal_host", "lang",
                    "searches", "zero_results", "trigram_hits", "last_mode", "last_results")
    list_filter = (PeriodFilter, ResultFilter, "surface", "city", "lang", "last_mode")
    date_hierarchy = "day"
    search_fields = ("query_norm",)
    ordering = ("-day", "-searches")
    actions = ("export_csv", "export_csv_grouped")

    def has_module_permission(self, request): return request.user.is_superuser
    def has_view_permission(self, request, obj=None): return request.user.is_superuser
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return request.user.is_superuser

    @admin.action(description=_("CSV exportieren"))
    def export_csv(self, request, queryset): ...           # построчно
    @admin.action(description=_("CSV: Top-Suchen zusammengefasst"))
    def export_csv_grouped(self, request, queryset):
        # .values("query_norm","city","surface").annotate(Sum searches/zero/trigram).order_by("-searches")
```
- **«Top-Suchen / Nichts gefunden за 7/30 дней»** собирается без отдельной страницы: `PeriodFilter` + `ResultFilter`, сортировка по `searches`, затем «выбрать все → CSV zusammengefasst». Свой admin view с графиками — по спросу.
- **Защита от CSV-инъекции.** Запрос вводит посетитель, а CSV открывают в Excel. Значение, начинающееся с `= + - @ \t \r`, получает префикс `'`. Хелпер `_csv_safe()` с отдельным тестом. В админках проекта CSV-экспорта ещё нет (`text/csv` в `admin.py` не найден), так что прецедентом станет этот.
- `list_filter` по `city` через `AllValuesFieldListFilter` показывает DISTINCT по всей таблице. При 180 днях хранения это допустимо.

---

## 5. Инкременты (батч из двух коммитов, один прогон CI)

| # | Коммит | Файлы | Гейт |
|---|---|---|---|
| 1 | `T-8.21: журнал поиска — модель, запись в record()` | `models.py`, `migrations/0025_…`, `search_log.py` (новый), `search.py`, `portal_views.py`, `views.py`, `base.py` (AGGREGATOR_SEARCH_LOG), тесты записи | `pytest apps/aggregator --reuse-db --create-db` (новая миграция) |
| 2 | `T-8.21: журнал поиска — админка платформы, CSV, retention` | `admin.py`, `tasks.py`, `base.py` (beat), `.po` ×5, тесты админки/purge | `ruff check .`, `ruff format --check .`, `scripts/i18n_quickcheck.py` (новые msgid), `test_template_comments` не нужен (шаблонов нет) |

Затем строка в `docs/build-log.md`, статус в `docs/task-catalog.md`, в `CLAUDE.md` §3 — «Самое свежее» и очередь миграций (`aggregator/0025` ждёт деплоя).

---

## 6. Тесты — `apps/aggregator/tests/test_search_log.py` (новый)
Хелперы `_listing`, `_req`, `_portal` взять из `test_unified_search.py:32-60, :256` (импорт или перенос в conftest). `pytestmark = pytest.mark.django_db`. Redis-ключи `rl:*` переживают прогоны: использовать уникальный `ip` на тест (урок проекта).

| # | Тест | Проверка |
|---|---|---|
| 1 | `test_portal_search_writes_row` | `portal_home(q="Messer")` создаёт 1 строку: surface=portal, portal_host=хост портала, city=portal.city, searches=1, last_mode=fts, last_results=1 |
| 2 | `test_entdecken_search_writes_row` | `discover_index(?q=…&city=Solingen)`: surface=entdecken, city=`solingen`, portal_host="" |
| 3 | `test_filters_only_search_is_logged` | `?stadtteil=ohligs` без q: query_norm="", filters_key содержит `stadtteil=ohligs`, filters={"stadtteil": "ohligs"} |
| 4 | `test_one_write_per_request` | после portal_home и discover_index `searches == 1` (track=False у широкого пула и чипов не пишет). Существующий `test_record_seam_called_once_per_search` (`test_unified_search.py:333-342`) остаётся; дополнить проверкой `kwargs["portal_host"]` |
| 5 | `test_same_query_same_day_aggregates` | два одинаковых запроса дают одну строку с `searches == 2`; «Messer» и «  MESSER » тоже одна строка |
| 6 | `test_zero_results_counted` | запрос без совпадений: `zero_results == 1`, `last_results == 0`; `mode=empty` («!!!») пишется, last_mode=empty |
| 7 | `test_trigram_hit_counted` | «mesesr» даёт `trigram_hits == 1` |
| 8 | `test_cursor_pages_not_logged` | `?q=…&cursor=…` не увеличивает счётчик (portal и entdecken) |
| 9 | `test_min_len_skips_single_char` | `q="a"` без фильтров: строк 0 |
| 10 | `test_disabled_setting_is_noop` | `override_settings(AGGREGATOR_SEARCH_LOG={…, "enabled": False})`: строк 0 и ноль дополнительных SQL |
| 11 | `test_normalize_query` | регистр, пробелы, NFC, обрезка до 100 символов |
| 12 | `test_scrub_personal_data` | e-mail даёт `‹email›`, «0171 2345678» и «+49 212 …» дают `‹nummer›`, IBAN даёт `‹iban›`; PLZ «42651» и «2,50 €» не тронуты |
| 13 | `test_model_has_no_personal_fields` (**замок**) | `{f.name for f in SearchQueryLog._meta.get_fields()} ⊆ ALLOWLIST`. Новое поле краснит тест и требует осознанного решения |
| 14 | `test_record_has_no_request_parameter` (**замок**) | `inspect.signature(search.record)` и `search_log.log` не содержат `request` и параметров с `ip`, `user`, `session`, `agent` в имени |
| 15 | `test_log_failure_does_not_break_search` | `mock.patch("apps.aggregator.search_log._log", side_effect=DatabaseError)`: portal_home и discover_index отвечают 200 с результатами. Второй вариант: `SearchQueryLog.objects.create` бросает исключение внутри savepoint, после него следующий запрос в той же транзакции теста выполняется (транзакция не отравлена) |
| 16 | `test_race_integrity_error_falls_back_to_update` | mock `create` бросает `IntegrityError` после предсозданной строки: `searches` увеличен |
| 17 | `test_query_budget` | `CaptureQueriesContext`: разница числа запросов поиска с журналом и без (`enabled=False`) на «тёплом» ключе — 1 SELECT (подсчёт) + 1 UPDATE (+ savepoint-операторы). Ассерт по составу, а не по голому числу: `SELECT … LIMIT 241` и `UPDATE "aggregator_searchquerylog"` |
| 18 | `test_count_capped` | 250 листингов дают `last_results == max_results + 1` |
| 19 | `test_purge_respects_retention` | строки с `day` = cutoff-1 удалены, cutoff и новее остались; задача `tasks.purge_search_log()` возвращает число удалённых |
| 20 | `test_admin_superuser_only` | клиент на public: суперпользователь получает 200 на changelist; staff без superuser — 403 (или нет в индексе админки); аноним — редирект на логин |
| 21 | `test_admin_not_in_tenant_urls` | `reverse("admin:aggregator_searchquerylog_changelist", urlconf="config.urls_tenant")` бросает `NoReverseMatch` (владельцу бизнеса недоступно) |
| 22 | `test_csv_export_and_injection_guard` | действие `export_csv` отдаёт `text/csv`; запрос `=HYPERLINK(...)` экспортируется как `'=HYPERLINK(...)`; `export_csv_grouped` суммирует дни |
| 23 | `test_filters_key_price_rounded` | `preis_von=2.49` и `2.50` попадают в одну строку |

---

## 7. Риски и смягчения
- **Лишний запрос на каждый поиск** (подсчёт плюс upsert). Подсчёт ограничен `LIMIT 241`, upsert идёт по уникальному индексу. Тест 17 держит бюджет. Если понадобится, upsert заменяется одним `INSERT … ON CONFLICT` (сырой SQL).
- **Конкуренция на горячем ключе** (популярный запрос, построчная блокировка UPDATE). На масштабе города незаметно. Если станет заметно, вернуться к буферу в Redis (Р-3, отвергнутый вариант).
- **Персональные данные в свободном тексте.** `scrub()` ловит основные шаблоны, но не всё: имя человека, например, не поймает. Смягчения: срок хранения, отсутствие времени и IP, доступ только суперпользователю. В Datenschutzerklärung платформы добавить строку «анонимная статистика поисковых запросов без привязки к лицу». Текст — на владельце (заготовки `/datenschutz/` с плейсхолдерами).
- **Рост числа строк из-за фильтров и мусорных `?city=`.** Ключ ограничен rate-limit'ом, округлением цен и сроком хранения. Мониторинг: число строк в день в отчёте.
- **Сломанный savepoint в транзакции.** Закрыт `transaction.atomic()` вокруг всей записи (тест 15).
- **Миграция SHARED.** Нужен деплой `./scripts/deploy.sh single`, проверка — `python manage.py migration_state`.
- **i18n-гейт.** Новые немецкие msgid (verbose_name, фильтры, действия) — во все 5 `.po`, проверить quickcheck и `scripts/i18n_untranslated.py`.

## 8. Что НЕ делаем
- Аналитику для владельца бизнеса («популярные запросы по моим объектам», просмотры и переходы) — это T-8.8, отдельная задача с отдельным решением о показе.
- Подписку на запрос / «сообщить, когда появится» — T-8.10d.
- Автоматическое пополнение синонимов из журнала. Это ручной процесс: суперпользователь смотрит «Nichts gefunden» и «Nur Tippfehler-Treffer» и правит `apps/aggregator/search_synonyms.py` коммитом.
- Журнал кликов по результатам (CTR) и цепочек запросов.
- Графики и дашборд в админке — пока хватает changelist и CSV.
- Журнал поиска внутри витрин тенантов (`?q=` каталога/акций) — другая поверхность, не каталог города.

## 9. Точки изменения — сводка
| Файл:строка | Изменение |
|---|---|
| `apps/aggregator/models.py:~286` (после `ListingReport`) | `class SearchQueryLog` |
| `apps/aggregator/migrations/0025_t8_21_search_log.py` | новая, SHARED |
| `apps/aggregator/search_log.py` | новый модуль: scrub/normalize/filters_key/_count_capped/log/purge |
| `apps/aggregator/search.py:302-308` | `SearchOutcome.lang` |
| `apps/aggregator/search.py:311-351` | `execute(..., city="", portal_host="")`, заполнение `lang`, проброс в record |
| `apps/aggregator/search.py:355-363` | `record(..., city, portal_host, first_page)` делегирует в `search_log.log` |
| `apps/aggregator/portal_views.py:233-236` | city/portal_host/first_page/lang |
| `apps/aggregator/views.py:402, :425` | cursor поднять выше; `execute(..., city=city, track=not cursor)` |
| `apps/aggregator/admin.py:~131` | `SearchQueryLogAdmin` + 2 фильтра + 2 CSV-действия |
| `apps/aggregator/tasks.py` (конец) | `purge_search_log` |
| `config/settings/base.py:~259` | `AGGREGATOR_SEARCH_LOG` |
| `config/settings/base.py:~477` | beat `purge-search-log` |
| `locale/*/LC_MESSAGES/django.po` ×5 | новые msgid админки |
| `apps/aggregator/tests/test_search_log.py` | новый; дополнить `test_unified_search.py:333-342` проверкой kwargs |
