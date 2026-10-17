# Г5 — «Живой» район портала: порог N бизнесов + «Auch in der Nähe»

Дата: 2026-10-17 · ID: Г5 (backlog-portal-direction-2026-10-16.md §4) · N = 10 (владелец)
Статус: план на согласование, кода нет. Миграций НЕ требуется.

## 0. Суть в двух строках
Если в районе меньше N разных бизнесов, страница района показывает свою выдачу без изменений. После неё идёт отдельный подписанный блок «Auch in der Nähe» с предложениями соседних районов: у каждой карточки видна метка района, у каждой группы есть ссылка «Alle in <Район> anzeigen». С чужими позициями ничего не смешивается молча. В счётчик, JSON-LD, фид, подписку, журнал поиска и sitemap хвост не попадает.

## 1. Разведка: как сейчас устроены районы

### 1.1 Реестр
- `apps/core/districts.py:28-46` — `CITIES["solingen"]`: **ровно 5 Stadtbezirke** в официальном порядке: `graefrath`, `wald`, `mitte`, `burg-hoehscheid`, `ohligs-aufderhoehe-merscheid`. Уровня Stadtteil НЕТ. Stadtteile (Burg, Höhscheid, Unterburg, Ohligs, Aufderhöhe, Merscheid, Innenstadt) — `aliases` внутри Stadtbezirk.
- API: `normalize` (:107), `label` (:122), `choices_for` (:103), `toponym_tokens` (:76, кэш через lru_cache).
- **Соседства нет вообще.** В коде есть только «близость» листинга по координатам или по совпадению района: `apps/aggregator/views.py:1109-1110` («Ähnliche … in der Nähe», блок Б).

### 1.2 Как бизнес связан с районом
- `Tenant.district` (slug; `tenants/0033`) — выбирается в «Mein Geschäft».
- `AggregatorListing.district` (`apps/aggregator/models.py:115-116`) — снимок при синке: `tasks.py:183` (`tenant.district`), события — `_event_district` `tasks.py:161-165` (событие в другом городе получает `""`), массовый перенос при Save настроек — `tasks.py:981-988`.
- Личность бизнеса в листинге — `tenant_schema` (по нему уже разбивают выдачу: `portal_home_blocks.py:334`, `follow.py:351`). Один бизнес с 5 листингами = одна схема.

### 1.3 Где район читается и фильтруется
| Поверхность | Место | Как |
|---|---|---|
| Страница района `/stadtteil/<slug>/` и `/stadtteil/<slug>/<facet>/` | `config/urls_portal.py:82-86` → `portal_views.portal_home(district=…)` `portal_views.py:125` | метка/404 :148-153; пул `listings_for(district=…)` :216-221; путь сильнее `?stadtteil=` :185-186; `path_district` в intent :190 |
| Чипы районов | `_district_choices` `portal_views.py:70-88` → `_portal_district_chips.html` | показывается район с ≥1 публичным листингом, без счётчика; при поиске чипы сужаются по найденному (:282-285) |
| Главная портала | `_render_home` `portal_views.py:701-752` | только чипы (:740); блоки главной районов не знают (`home_blocks` :318) |
| Единый поиск | `search.py:239` (`SearchFilters.district`), :340-345 (`?stadtteil=`), :408-409 (фильтр), :465 (carry); намерение «in Wald» — `query_intent.py:137-155, 247-255` | точный фильтр |
| Общий пул | `views.listings_for` `views.py:155-161` | `public()` + `is_demo=False` при `include_demo=False` + `district=` |
| Видимость | `models.ListingQuerySet.public` `models.py:39-63` + `visibility.withheld_schemas` `visibility.py:30-42` | неактивные/suspended/без почты/без согласия/intern — вне |
| Фид T-8.8 | `open_feed.py:71, 95` | точный `?stadtteil=` |
| Подписка на район T-8.7 | `follow.py:361-367` | точный `district`, `include_demo=False` |
| Sitemap | `_sitemap_urls` `portal_views.py:782-785` | все районы из `_district_choices`; на превью sitemap пустой (:767-770) |
| llms.txt | `llms.py:34-38, 114-118` | районы с листингами |
| JSON-LD | `ld_collection` `portal_views.py:457-461` (элементы = `cards`); у предложения `structured.py:153-155` (`addressRegion`) | |
| Журнал поиска T-8.21 | `search_engine.record(..., extra={"stadtteil": district})` `portal_views.py:294-308` | |
| Кэш P0-1 | `apps/core/pagecache.py:193-222` | кэшируется только GET без query и без сессии; при query — живой рендер |

### 1.4 Демо
- `portal.show_demo` (`models.py:550`) → `include_demo=portal.show_demo` во всех выборках портала. На настоящем портале демо не видно вовсе, на превью видно с полосой «Vorschau» (`shows_demo`, `portal_views.py:450`).

## 2. Определения

**Бизнес района** — уникальный `tenant_schema` среди листингов `listings_for(city=portal.city, business_type=<область страницы>, include_demo=portal.show_demo)` с `district == slug`. Учитываются все виды листингов, включая карточку бизнеса (`KIND_BUSINESS`): если бизнес виден в районе, он есть в районе.
- Почему `include_demo=portal.show_demo`: счётчик обязан совпадать с тем, что видит посетитель. На настоящем портале демо не считаются по построению. На превью-портале (до запуска) считаются, иначе превью Золингена всегда показывало бы «мёртвые» районы и не показывало бы реальный вид запуска с наполнением.
- Область страницы — портальный `business_type` плюс фасет пути (`/stadtteil/wald/bakery/`). Запрос `q`, разделы `?kat=` и вкладки в подсчёт **не входят**: «живость» — свойство района, а не запроса. Иначе любой узкий запрос («Fahrradschloss») вызывал бы соседей.

**Живой район:** `count >= N`, где `N = settings.PORTAL_DISTRICT_MIN_BUSINESSES` (по умолчанию 10; `0` = функция выключена). Ровно N — живой, соседей нет.

**Соседи** — явный упорядоченный список в реестре. Это не расстояние по координатам: координаты есть не у всех бизнесов, а подпись «aus Mitte» должна быть стабильной и проверяемой.

## 3. Источник соседства — `apps/core/districts.py`

Добавить рядом с `CITIES`:

```python
# Г5: соседние Stadtbezirke (общая граница), порядок = ближе к центру района первым.
NEIGHBORS: dict[str, dict[str, tuple[str, ...]]] = {
    "solingen": {
        "graefrath": ("wald", "mitte"),
        "wald": ("graefrath", "mitte", "ohligs-aufderhoehe-merscheid"),
        "mitte": ("graefrath", "wald", "burg-hoehscheid", "ohligs-aufderhoehe-merscheid"),
        "burg-hoehscheid": ("mitte", "ohligs-aufderhoehe-merscheid"),
        "ohligs-aufderhoehe-merscheid": ("wald", "mitte", "burg-hoehscheid"),
    },
}

def neighbors(city: str, slug: str) -> tuple[str, ...]: ...  # незнакомое → ()
```
- Предположение по карте (сверить, вопрос В-1): нет общей границы у Gräfrath–Ohligs/Aufderhöhe/Merscheid, Gräfrath–Burg/Höhscheid и Wald–Burg/Höhscheid.
- Город вне таблицы, например Хильден → `()` → честный пустой хвост (§4.4).
- Stadtteil-уровень НЕ вводим: страницы и хранение работают на уровне Stadtbezirk (5 slug), Stadtteile остаются алиасами. При вводе нового уровня таблицу соседей пришлось бы вести вдвое.

## 4. Поведение

### 4.1 Страница района (путь `/stadtteil/<slug>/[<facet>/]`)
1. Основная выдача — без изменений: тот же пул, featured, пагинация, счётчик «N Treffer», карта и `ld_collection`.
2. Если район не живой, под заголовком выводится строка-пояснение: «Noch wenige Geschäfte in {{ name }} — Angebote aus der Nähe finden Sie weiter unten.» Строка показывается только когда хвост реально не пуст, иначе это обещание без исполнения.
3. **Хвост «Auch in der Nähe»** выводится только на странице, где выдача района заканчивается (`page is not None and not page.has_more`), после карточек и до «More local portals». Обоснование:
   - соседи не вытесняют свои позиции района;
   - курсор и offset пагинации не трогаем;
   - хвост остаётся рядом с «больше ничего нет».
   Если у района 0 карточек, хвост стоит сразу, вместо голого «No offers yet.», а сама фраза «No offers yet.» остаётся над ним.
4. Хвост состоит из **групп по соседям** в порядке `NEIGHBORS`: заголовок «Auch in der Nähe: {{ Mitte }}», у карточки метка района, ссылка «Alle in {{ Mitte }} anzeigen →».
   - Константы: `TAIL_NEIGHBORS = 2` непустые соседа, `TAIL_PER_NEIGHBOR = 6` карточек, ≤ 2 карточек на бизнес. Ограничение на бизнес — тем же `Window(RowNumber() partition_by tenant_schema)`, что `portal_home_blocks.py:331-337`.
   - Порядок без поиска — `_order("daily_rotation")` (`portal_home_blocks.py:288-290`), честно ко всем бизнесам. С поиском — ранг движка.
   - **Featured хвост не поднимает** (UWG §5a): сортировка не смотрит `featured_until`. Платная позиция, попавшая в хвост органически, сохраняет свой «★ Anzeige» из `_cards`.
5. **Сосед сам «мёртвый»** (тоже < N) — его всё равно показываем, если у него есть карточки: подпись честная, а пользы больше, чем от пустоты. Сосед с 0 карточек в области пропускается, вместо него берётся следующий по списку.
6. **Соседей нет** (город вне таблицы или у всех соседей 0) — секции нет вовсе: без заголовка, без строки-пояснения.

### 4.2 Поиск и фильтры на странице района
- Хвост повторяет тот же `q_eff` и `filters_eff` (кроме района), ту же вкладку (`kinds`), `kat`/`merkmal`, `neu` и фасет. В соседях это то же самое, а не «что-нибудь рядом».
- Хвост выполняется через `search_engine.execute(..., track=False)`. Журнал поиска пишет только основной поиск, как сейчас (`portal_views.py:294-308`); ключ журнала не меняется.
- Режим движка (FTS или опечатки) для хвоста решается отдельно. Если хвост ушёл в fuzzy, у группы выводится пометка «ähnliche», как в `_search_fuzzy_note.html`.
- «N Treffer» считает **только район** (`hits`, :289-293). Хвост в счётчик не входит.

### 4.3 Район фильтром, а не путём (`?stadtteil=` на корне или намерение «in Wald»)
- По умолчанию в v1 (В-3): хвост показывается и здесь, когда `filters_eff.district` задан и район не живой. Посетитель тоже выбрал район, ожидания те же.
- Намерение с `roh=ort` отключает фильтр района (`query_intent.py`), а значит и хвост. Это следует из построения.
- `/entdecken/` (`views.py`, `search.py`) — **вне v1** (В-4): там свой шаблон и нет городского контекста портала.

### 4.4 Когда хвоста нет никогда
- `N == 0`;
- район живой (`count >= N`);
- сорт «Nähe»/радиус с точкой (`point is not None and filters.sort in ("", "naehe")` → `page is None`, `geo.nearest`): близость уже задана позицией посетителя;
- живой отельный поиск по датам (`search` dict, :340-350): доступность соседей не проверяем;
- курсор не на последней странице;
- главная портала (`is_home_request`) и страницы без района.

### 4.5 Чипы районов
- Состав прежний: район с ≥1 публичным листингом (`portal_views.py:70-88`). Малые районы НЕ прячем: страница малого района теперь полезна благодаря хвосту.
- Счётчик на чипе в v1 **не выводим** (В-2): «Gräfrath · 2» читается как «мёртвый портал», а честность обеспечивает строка-пояснение на самой странице.
- Чип — ссылка на ту же область (`chip_carry`, :243-245): правило «та же область» не меняется.

## 5. Подсчёт и кэш

Новый модуль `apps/aggregator/district_liveness.py`:

```python
def business_counts(portal) -> dict[tuple[str, str], set[str]]
    # ОДИН запрос: listings_for(city, business_type=portal.business_type, include_demo=portal.show_demo)
    #   .exclude(district="").order_by().values_list("district","business_type","tenant_schema").distinct()
    # → {(district, business_type): {schema, …}}; число строк ≤ число бизнесов портала.
def count_for(portal, district, business_type=None) -> int   # |∪ множеств по области|
def is_live(portal, district, business_type=None) -> bool    # N==0 → True
def neighbor_tail(portal, district, *, pool_for, q, filters, kinds, scope, ranked) -> list[dict]
    # [{slug, label, items, more_url, fuzzy}] — ≤ TAIL_NEIGHBORS групп
```
- Множества нужны, а не `Count(distinct)` по паре: сумма по типам задвоила бы бизнес с листингами двух `business_type`. Адверсариальный замок §7, тест 3.
- Кэш: `django.core.cache`, ключ `g5:districts:{portal.pk}:{int(portal.show_demo)}:{portal.business_type}`, TTL `PORTAL_DISTRICT_COUNT_TTL = 300` с. При ошибке кэша — прямой расчёт (fail-safe, как в `pagecache.py:206-209`). Кэшируемые рендеры страниц P0-1 и без того хранятся `PUBLIC_PAGE_CACHE_TTL`; некэшируемые (с query) не платят лишний запрос на каждый рендер.
- Без инвалидации по сигналу. Устаревание ≤ 5 минут допустимо: порог — мягкая UX-эвристика, а не видимость. Видимость по-прежнему решает `public()` в момент запроса, поэтому хвост никогда не покажет скрытое.
- Settings в `config/settings/base.py`: `PORTAL_DISTRICT_MIN_BUSINESSES = env.int(..., default=10)`, `PORTAL_DISTRICT_COUNT_TTL = 300`.

## 6. Как не сломать существующее

| Инвариант | Решение |
|---|---|
| «Блок ⊆ ленты» (T-8.19, `test_every_block_more_link_contains_all_block_cards`) | каждая группа хвоста ⊆ выдачи по своему `more_url` (`/stadtteil/<сосед>/?<те же carry без stadtteil/cursor>`); выборка группы строится той же функцией пула, что `portal_home` для соседа. Новый замок-аналог |
| «Alle anzeigen = та же область» | `more_url` несёт `chip_carry` (kind/neu/kat/merkmal/q/фильтры/geo, без `stadtteil`/`cursor`) + путь фасета, если он есть |
| Фид T-8.8 | `open_feed` не трогаем: `?stadtteil=` точный, без соседей (машинный формат = точная выборка). Замок |
| Подписка на район T-8.7 (`follow.py:361-367`) | точная, без соседей. Замок |
| Sitemap / llms | без изменений; соседи туда не попадают |
| JSON-LD `ld_collection` | элементы — только `cards` района; хвост не входит (иначе CollectionPage района перечисляла бы Mitte). Замок |
| Журнал поиска T-8.21 | хвост `track=False`; одна запись на поиск. Замок «record вызван один раз» (`test_record_seam_called_once_per_search`) должен остаться зелёным |
| Сорт «Nähe»/радиус T-8.7 | хвост выключен (§4.4) |
| Пагинация/курсор | хвост только на последней странице, курсор не трогаем; `page_carry` без изменений |
| Кэш P0-1 | рендер детерминирован в пределах дня (daily_rotation солится датой, как главная); персонального в хвосте нет |
| noindex превью (T-8.26 п.2) | без изменений; полоса «Vorschau»: `shows_demo` учитывает и карточки хвоста |
| Карта (`map_points`) | только `cards` района (v1) |
| Демо на настоящем портале | `include_demo=portal.show_demo` и в подсчёте, и в хвосте |
| Featured/UWG §5a | хвост не поднимает платное; ярлык «Anzeige» остаётся |
| Hotel-портал (H8a) | `_collapse_hotels` применяется к каждой группе хвоста; при поиске по датам хвоста нет |

## 7. Замки-тесты ДО кода
Файл `apps/aggregator/tests/test_district_threshold.py` (фабрики как в `test_districts_portal.py`/`test_portal_block_b.py`; `override_settings(PORTAL_DISTRICT_MIN_BUSINESSES=…)`; `isolated_ratelimit` для запросов с query).

Реестр:
1. `NEIGHBORS`: каждый slug ∈ `CITIES`, нет самоссылок, отношение **симметрично**, у каждого района ≥1 сосед, ключи = все районы города.
2. `neighbors("Hilden", "x") == ()`, `neighbors("Solingen", "мусор") == ()`.

Подсчёт:
3. **Бизнес с 5 листингами считается один раз**, и с двумя `business_type` у листингов одного бизнеса — тоже один.
4. **Ровно N бизнесов → живой**: хвоста нет, строки-пояснения нет. **N−1 → хвост есть.**
5. **Демо не считается на настоящем портале** (`show_demo=False`): 9 настоящих + 3 демо → не живой. На превью (`show_demo=True`) те же 12 → живой.
6. Withheld-бизнес (suspended/`email_pending`/`in_city_catalog=False`/intern) не считается и не попадает в хвост.
7. Листинг с пустым district (событие в другом городе) не считается ни к одному району.
8. `N=0` → хвоста нет нигде.
9. Кэш недоступен (мок `cache.get` бросает) → страница 200, подсчёт прямой.

Хвост:
10. В хвосте только листинги соседей (`district ∈ neighbors`), у каждой карточки метка района. **Ни одной карточки несоседнего района** (Gräfrath не показывает Burg).
11. **«Alle in X anzeigen» ⊇ группы**: каждая карточка группы есть в выдаче по `more_url` (тот же kind/kat/q).
12. **Сосед сам мёртвый, но с карточками** → показан. **Сосед с 0** → пропущен, берётся следующий.
13. **Соседей нет** (все соседи пусты) → секции нет, строки-пояснения нет (адверсариальный: «обещание без исполнения»).
14. Хвост на последней странице: при `has_more=True` его нет, на странице `?cursor=` с концом выдачи — есть.
15. ≤ 2 карточек на бизнес в группе; ≤ `TAIL_NEIGHBORS` групп; featured не поднимается в хвосте (порядок не зависит от `featured_until`).
16. Поиск на странице района: хвост с тем же `q` (сосед с «Pizza» есть, с «Brot» нет — при `q=Pizza` в хвосте только пицца); «N Treffer» = только район; `search_engine.record` вызван ровно один раз.
17. `?stadtteil=wald` на корне (фильтр) → хвост есть; `roh=ort` → фильтра и хвоста нет.
18. Сорт «Nähe» с точкой → хвоста нет; отельный поиск по датам → хвоста нет.
19. `ld_collection` содержит только карточки района.
20. Фид `?stadtteil=wald` и выборка дайджеста района (`follow` district) — без листингов соседей (регресс-замок).
21. Превью-портал: хвост из демо-карточек → полоса «Vorschau» видна.
22. Число SQL-запросов страницы района с хвостом ограничено константой (`django_assert_max_num_queries`) и не растёт с числом листингов.

Шаблоны: прогон `apps/core/tests/test_template_comments.py` и `scripts/i18n_quickcheck.py`.

## 8. Точки изменения
- `apps/core/districts.py` — `NEIGHBORS`, `neighbors()`.
- `config/settings/base.py` — `PORTAL_DISTRICT_MIN_BUSINESSES`, `PORTAL_DISTRICT_COUNT_TTL`.
- **NEW** `apps/aggregator/district_liveness.py` — подсчёт, кэш, `neighbor_tail`.
- `apps/aggregator/portal_views.py::portal_home` (после построения `page`, :311-323; до `render`): эффективный район = путь или `filters_eff.district`; вызов `neighbor_tail`; контекст `district_tail`, `district_sparse`; `shows_demo` с учётом хвоста. Пул соседа собирается той же цепочкой, что основной (`listings_for` → `execute` → `apply_scope(kinds/neu)` → `apply_filters(kats/tags)`). Вынести в хелпер `_district_pool(...)`, чтобы основной пул и пул хвоста не разошлись — на этом держится замок 11.
- `templates/aggregator/portal_home.html` — строка-пояснение под :16; секция хвоста после блока карточек (:65-76), до `other_portals`.
- **NEW** `templates/aggregator/_portal_district_tail.html`; `_cards.html` — необязательный флаг `show_district` (метка `listing.district_name`). Если флаг уже есть — использовать его.
- `locale/{de,en,ru,uk,tr}/LC_MESSAGES/django.po` — 3–4 msgid: «Auch in der Nähe: %(name)s», «Alle in %(name)s anzeigen», «Noch wenige Geschäfte in %(name)s — Angebote aus der Nähe finden Sie weiter unten.», метка «aus %(name)s».
- `static/css/app.css` — пересобрать, если появятся новые классы Tailwind (лучше переиспользовать классы `firm_group`-секции, :56-62).
- `docs/build-log.md`, `docs/task-catalog.md` (Г5), §3 `CLAUDE.md`.

## 9. Инкременты (батч-режим, один CI на верхушке)
- **G5-1** реестр соседей + `district_liveness` (подсчёт/кэш) + settings; замки 1–9. Без UI.
- **G5-2** хвост на странице района в режиме просмотра (без query) + шаблоны + i18n; замки 10–15, 19, 21, 22.
- **G5-3** поиск/фильтр/намерение + исключения «Nähe»/отель + регресс-замки фида и подписки; замки 16–18, 20.
- Стенд Python-Playwright на `solingen.<base>` (демо DCC, превью): Gräfrath/Wald 390 и 1440 px, de/ru; проверить, что хвост не дублирует карточки района и что ссылки групп ведут на соседа с тем же фильтром.
- Ревью перед мержем (правило сессии T-8.26): `django-reviewer` + `security-reviewer`; `database-reviewer` — на запрос подсчёта и хвост (план запроса Window по `district`; индекс `(city, district)` проверить в `models.Meta`).

Размер — S (≈1–1,5 дня), миграций нет.

## 10. Риски
- **Расхождение пулов основной выдачи и хвоста** ломает «блок ⊆ ленты». Митигация: общий хелпер `_district_pool` + замок 11.
- **Нагрузка на некэшируемые рендеры** (каждый `?q=` на странице района — до 2 дополнительных `execute`). Митигация: хвост только на последней странице, лимиты групп, существующий rate-limit `portal-search`/`portal-feed` (:133-142, :192-201), замок 22.
- **Таблица соседей неверна географически** — её проверяет владелец (В-1); ошибка видна на странице, а не в данных.
- **Устаревший подсчёт ≤ 5 мин** — допустимо: видимость решает `public()`.
- **SEO: тонкие страницы районов дублируют соседей.** Хвост — меньшая часть страницы, canonical прежний; при сомнении — В-5.
- Превью-портал выглядит «живее» реального запуска, потому что считаются демо. Это осознанно и подписано полосой «Vorschau».

## 11. Вопросы владельцу (рекомендация по умолчанию — жирным)
- **В-1 Соседи Золингена** — таблица §3 (общая граница; Gräfrath не граничит с Ohligs/Burg, Wald не граничит с Burg). **Принять, поправить по карте при необходимости.**
- **В-2 Счётчик на чипах малых районов** — а) без счётчика; б) «Wald · 3»; в) прятать районы < N. **а)** — честность обеспечивает строка-пояснение на странице, а счётчик продаёт «пустоту».
- **В-3 Хвост при районе-фильтре** (`?stadtteil=`/«in Wald»), а не только при пути — **да**.
- **В-4 `/entdecken/`** (платформенный каталог без портала) — **вне v1**, по спросу.
- **В-5 Индексация малых районов** — **оставить в sitemap и index** (локальный SEO «Bäcker Gräfrath»); альтернатива `noindex,follow` для районов < N.
- **В-6 Хвост при 0 Treffer** в ЖИВОМ районе (поиск ничего не нашёл в Mitte) — **нет в v1**: Г5 — про порог района; кандидат на следующий шаг.
- **В-7 Счёт по области** — порог считается по району с учётом отрасли портала и фасета пути, без учёта `q`/`kat` — **да**.
