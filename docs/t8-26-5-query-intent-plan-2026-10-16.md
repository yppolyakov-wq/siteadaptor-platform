# T-8.26 п.5 — разбор намерения запроса · составные слова · синонимы · оси вариантов (2026-10-16)

План агента planner по пункту 5 `docs/t8-26-audit-fixes-plan-2026-10-16.md` (аудит §7.2 — семь
эталонных запросов). Цикл: замки ДО кода → три ревью → зелёный CI → FF в `main`. Только правила,
без ML/LLM (ИИ-поиск — T-8.10d).

## Факты (main 5bd1ce23)
- `SearchFilters` уже несёт kats/tags/district/price_from/price_to/date/available/open_now/sort/
  radius; `date_window` понимает `heute|wochenende|YYYY-MM-DD`; `parse_filters` читает ТОЛЬКО GET.
- `_match_words`: подстрока от 4 букв — в одну сторону («jacke» → «Winterjacke», не наоборот).
- `_words`: ИЛИ по группе синонимов × конфиги, бюджет TERMS_MAX; групп `vegetarisch`, `aktivität`,
  `damen/herren` нет; `mittagessen`, `restaurant`, `kinder`, `jacke/mantel` есть.
- Индекс: A title · B business/dishes · C teaser+labels+tags · D city; `search_text` = title+
  business+dishes; `refresh()` пересобирает ТОЛЬКО из полей листинга → размеры без поля потеряются.
- Снимок товара без вариантов; `dish_names` занят семантикой наборов (вес B, замки).
- `merkmal=vegetarisch` в данных почти пуст (аудит прав).

## Решения
- **Р-1** разбор — отдельный шаг `search.resolve_intent(q, filters, city, lang, roh, path_district)`
  → `(q_eff, filters_eff, chips)` в двух вьюхах ДО лимита частоты; `execute`/`match`/`listings_for`
  не меняются (подписки T-8.7, замки п.4 стабильны).
- **Р-2** `apps/aggregator/query_intent.py::parse(q, *, city, today)` — чистая функция без БД, по
  порядку, найденная фраза вырезается: 1) «(jetzt|heute|gerade)? (geöffnet|offen|auf)» → open_now
  (ДО времени); 2) «unter|bis|max|höchstens N (€|euro)?» → price_to; «ab|von|mindestens N €» —
  валюта ОБЯЗАТЕЛЬНА (иначе «ab 18 Uhr» = цена); «N–M €» обе; 3) heute / morgen / (am) wochenende /
  будни → ближайший день; даты «24.12.» — v2; 4) «größe|gr. X» → до 5c: фраза вырезана + честная
  пилюля «Größenfilter noch nicht verfügbar»; голое «in M» не разбираем; 5) район только в
  надёжных формах («<город>-<район>», «in <район>», многословные имена/алиасы через
  `districts.normalize`, только при городе портала) — «Wald»/«Burg» одним словом не трогаем;
  6) признак (vegetarisch/veggie…) — НЕ жёсткий фильтр (данных мало): слово остаётся текстом +
  подсказка-ссылка «Nur mit Merkmal …», если в пуле есть ≥1; 7) вид бизнеса — НЕ выводим.
- **Р-3** явный GET сильнее вывода (фраза вырезана, пилюли нет); район из пути `/stadtteil/`
  блокирует вывод; пустой остаток `q` → режим «только фильтры» («Solingen-Wald» → лента Wald).
- **Р-4** выведенное НЕ попадает в carry/`search_hidden`/поля формы (не «прилипает»); ✕ цены/
  времени/offen/размера = `q` без фразы; ✕ района = `q` + `roh=ort` (слово остаётся текстом).
  Общий партиал `_search_intent_chips.html` на обеих поверхностях.
- **Р-5** журнал: сырой `q` + явные фильтры; выведенные — `extra["auto"]="datum,preis"`.
- **Р-6** составные слова: закрытые `search_synonyms.HEADS` (~40) и `MODIFIERS` (~15); слово ≥8
  букв вне синонимов, КОНЧАЕТСЯ головой ≥4 и остаток ≥3 → голова как ещё одна ветка ИЛИ того же
  слова (между словами — И); НАЧИНАЕТСЯ модификатором → модификатор в ИЛИ; стоп-лист ложных голов
  (tisch/haus/stadt/land/zeit/platz/markt) + замок; ранг держит точное первым.
- **Р-7** синонимы: ~15 групп (vegetarisch/veggie/vegetarian/fleischlos · vegan/pflanzlich ·
  aktivität(en)/freizeit/ausflugsziel · damen/frauen · herren/männer · hose/jeans · kleid(er) ·
  wochenmarkt/markt/hofladen · eis/eisdiele/gelato · sushi/japanisch · burger/hamburger ·
  bäcker/bäckerei/backstube · handyreparatur/displayreparatur; + mittag/mittagsmenü, lokal/gasthaus,
  kind/kinderprogramm, winterjacke/parka/anorak в существующие), EN-зеркала в тех же группах.
- **Р-8 (5c, ⚠️ миграция `aggregator/0027`, SHARED, аддитивная):** `variant_terms = JSONField(list)`
  — размеры/цвета активных вариантов (≤40, UPPER), вес C + `search_text`, `refresh().only()` += поле,
  фильтр `size` (`variant_terms__contains`) только по товарам. Без миграции не делаем — решение владельца.

## Инкременты
5a парсер + пилюли + журнал (без миграций) · 5b HEADS/MODIFIERS + синонимы (без миграций) ·
5c оси вариантов (по отмашке: миграция → `sync_aggregator` → `search_index.refresh`).

## Замки ДО кода
`test_query_intent.py` (без БД, `today` явно): unter 100 Euro · ab без валюты — не цена · heute
geöffnet = open_now, не дата · wochenende · будний день — ближайший · формы района (in Solingen-Wald /
Ohligs / голое Wald и Burgführung — НЕТ / без города — НЕТ) · размер вырезан, фильтра нет · явный GET
сильнее · признак — подсказка, не фильтр. Интеграционные (`isolated_ratelimit`, без фикс. IP):
Winterjacke unter 100 → только дешёвая Jacke · heute geöffnet = `?offen=1` · Kinderaktivitäten am
Wochenende = `?q=Kinder&datum=wochenende` (после 5b) · Friseur in Wald фильтрует район, ✕ → все
Friseur · выведенное не в `search_hidden` · журнал: сырой q + auto. 5b: Winterjacke → Jacke,
точное первым, Nachtisch не находит Tisch, veggie↔vegetarisch, группы без дублей.
**Осознанно:** на уровне ПОРТАЛА «Friseur in Solingen-Wald» теперь фильтрует Wald (п.4 брал всех
Friseur) — замки п.4 зовут `execute()` напрямую и остаются.

## Риски / Ops
Ложный вывод молча сужает выдачу → только надёжные формы + обязательная пилюля с ✕ + GET сильнее;
пустая выдача по выведенному району → «Ohne Stadtteil suchen». 5a/5b без миграций и переиндексации;
новые msgid пилюль × 5 `.po`.
