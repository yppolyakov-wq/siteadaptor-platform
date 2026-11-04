# FLT — фильтры городского портала (план, 2026-11-04)

Макет утверждён владельцем 2026-11-04 (артефакт «Filter & Breite — Entwurf», правка: районы на
телефоне — мультивыбор списком). План — агент `planner`, ссылки `файл:строка` сверены с кодом.

## 0. Цель и границы
- **Что меняем.** На странице выдачи портала (`portal_home.html`) у порталов с главной
  (`home.has_home(portal)`, `portal_home_blocks.py:224`) пять слоёв фильтров заменяет одна система:
  - **строка быстрых фильтров**: «Alle Filter · N», «Bereich ▾», «Stadtteil ▾», «Preis ▾»,
    «Jetzt geöffnet», «Merkmale ▾», «Nur Aktionen»;
  - **строка результатов**: «N Treffer» + «Sortieren ▾»;
  - **левая шторка**: секции Bereich, Preis, Stadtteil, Merkmale, «Jetzt geöffnet»; липкий подвал
    «Zurücksetzen» + «N Treffer anzeigen».
- **Мультивыбор района** (`?stadtteil=a&stadtteil=b`) — решение владельца. Мультивыбор раздела
  (`?kat=a&kat=b`, ИЛИ) движок уже умеет (`search.py:284,406,519-523`).
- **Ширина контента портала — 1536 px** (сейчас `max-w-5xl`).
- **Не в объёме:** вертикальные/combo-порталы (`_portal_kind_chips`, `_portal_hotel_search` — FLT-2);
  интерфейс `/entdecken/`; ширина витрины бизнеса (FLT-W, §9); фид и MCP остаются на одном районе.

## 1. Как устроено сейчас
| Слой | Где | Что делает |
|---|---|---|
| Чипы районов | `portal_home.html:23,38`; `_portal_district_chips.html`; `_district_choices` (`portal_views.py:66-77`) | ссылки на `/stadtteil/<slug>/`, одиночный выбор |
| Форма «Filter» | `_portal_filters.html`; `_filter_panel` (`portal_views.py:758-832`) | район, цена, «Wann», сортировка, радиус, «Nur verfügbar», «Jetzt geöffnet» + пилюли с ✕ |
| Вкладки видов | `_portal_tabs.html`; `home.tabs` | ось «что ищем» (`?kind=`) |
| Чипы разделов/признаков | `_category_chips.html`; `category_facets.chips` (`category_facets.py:34-92`) | одиночный `kat` + `merkmal`; скан ≤ 2000 строк |
| Чипы «Branche» | `_portal_facet_chips.html` | путь `/<facet>/` |
| «Eingrenzen» при поиске | `portal_home.html:35-43` | дублирует районы/виды/разделы/отрасли |
| «Erkannt: …» | `_search_intent_chips.html` | фильтры из текста запроса |

**Дефект (класс W0).** Скрытые поля формы «Filter» — белый список (`portal_views.py:811-815`):
«Anwenden» молча сбрасывает `marke`, `unternehmen`, `roh=ort`, `ansicht=karte`. Чинится в FLT-1d
(скрытые поля из `FILTER_PARAMS`), замок класса.

**Кэш (P0-1).** `cache_public_page` (`core/pagecache.py:193-217`) кэширует только GET без query и без
сессии — страницы-пути. Счётчики в кэшированном HTML допустимы (публичные агрегаты); в шторке и
поповерах **никакого `{% csrf_token %}`** — формы только GET (замок).

## 2. Мультивыбор по слоям
- **Движок** (`search.py`): `SearchFilters.district: str` → `districts: tuple`; `parse_filters` —
  `getlist("stadtteil")` + `districts.normalize` + дедуп, потолки `MAX_DISTRICTS = 30`, `MAX_KATS = 20`;
  `apply_filters` — `district__in`; `carry` — пара на каждый район. Одиночный URL байт-в-байт.
- **Намерение** (`query_intent.py:305-311,353`): `districts=(slug,)`, явный район сильнее.
- **Страница портала** (решение A, рекомендовано): путь `/stadtteil/<slug>/` = тот же фильтр
  `districts=(slug,)`, широкий поиск без районов, районы применяются после — шторка видит соседей
  со счётчиками. Изменение: режим «неточно» по пулу города (В-1). Хвост Г5 — только при ровно одном
  районе. При ≥ 2 значениях `stadtteil`/`kat` — `robots_noindex`, ссылки-опции `rel="nofollow"`.
- **Подписка** (`follow_query.py:131-141`): районы сортированно, `MAX_DISTRICTS_FOLLOW = 3`; хэш
  набора с одним районом не меняется; два района → `TARGET_QUERY`.
- **Журнал поиска** (`search_log.py:56-84`): `stadtteil` списком, как `kat`/`merkmal`.
- **ИИ-подсказка**: `stadtteil` остаётся в `_SINGLE`; замок «не добавляет район при любом заданном».
- **Фид / MCP**: фид одиночный (расширение — api-design, roadmap); MCP `_applied` — строка при одном,
  список при нескольких.
- **Bereich**: выбранная категория (не раздел) видна отмеченной строкой под разделом — без тихой потери.

## 3. Счётчики по опциям
Новый `apps/aggregator/portal_facets.py`: один `aggregate()` с условными `Count(filter=…)` по пулу
после широкого поиска (без районов/разделов/признаков), каждая опция исключает свой фасет
(~55 выражений за один проход). Заменяет `category_facets.chips`, DISTINCT `pairs` и два
`_district_choices`. Границы цены — `Min/Max` по пулу портала, кэш 300 с по fingerprint.
«N Treffer» — `count_capped` всегда. Инварианты-замки: счётчик единственной выбранной опции ==
«N Treffer»; число запросов ≤ до FLT.

## 4. Работа без JS
Шторка — `<dialog>` с одной GET-формой, без JS видна через `<noscript>`-стиль (приём DS-6);
«Alle Filter» — якорь `#flt-drawer`; скрытые поля = `search.carry` минус контролы шторки (замок:
каждый ключ `FILTER_PARAMS ∪ {kind,neu,q,lat,lng,roh,ansicht}` переживает отправку). Поповеры —
`<details>` со ссылками-переключателями (добавить/снять значение), «Preis» — мини-форма GET.

## 5. Что удаляем
На странице выдачи порталов с главной: `_portal_district_chips` (кроме навигации на главной),
`_portal_filters.html`, «Eingrenzen», `_category_chips` (остаётся для `/entdecken/`); «Branche» —
секцией шторки (В-2). Не меняются: вкладки, «Erkannt», вертикальные порталы. Осознанно
переписываются замки `test_unified_search.py:302,311`, `test_portal_block_a.py:122,138`,
`test_portal_block_b.py:77-100`, `test_districts_portal.py:148`.

## 6. Доступность и телефон
`showModal()` (инертный фон, фокус, Esc, возврат фокуса), `fieldset/legend`, `details`, ✕ с
`aria-label`, цели ≥ 44 px, слайдер — два `range` без `name` синхронно с текстовыми полями,
счётчик в доступном имени. Телефон: строка пилюль с прокруткой; поповер внутри `overflow-x-auto`
обрезается → на `<sm` пилюли ▾ открывают шторку на своей секции; шторка во весь экран.

## 7. Ширина 1536 px
`portal_base.html` / `_base.html`: шапка и подвал `max-w-screen-2xl`, у `main` блок `main_width`
(широко — только листинги: portal_home, portal_discover, search, index; формы и чтение — 1024).
`_cards.html` + `xl:grid-cols-4`. Пересборка `app.css`.

## 8. Инкременты (замки — до кода)
| ID | Состав | Риск |
|---|---|---|
| FLT-0 | характеризация + красный замок дефекта W0 | низкий |
| FLT-1a | ширина §7 | низкий |
| FLT-1b | мультирайон §2 + решение A + noindex | средний |
| FLT-1c | `portal_facets.py`, «N Treffer» всегда | средний (перф) |
| FLT-1d | разметка: пилюли, строка результатов, шторка, поповеры; удаление слоёв §5 | средний |
| FLT-1e | `static/js/portal.js`: шторка, поповеры, телефон, слайдер; Playwright-стенд | средний |
| FLT-1f (опц.) | живое «N Treffer anzeigen» (GET JSON) | средний |
| FLT-2 | вертикальные порталы, фид списком | — |

Миграций нет. i18n: новые msgid во все 5 `.po`; не передавать `_()` в `{% include with %}`.

## 9. FLT-W — ширина витрины бизнеса (позже)
`site_defaults.page_width` = `""` (1280) | `"2xl"` (1536) | `"full"`, presence-minimal рядом с
`text_width` (`siteconfig.py:1945`), контекст рядом с `storefront_text_width` (`core/context.py:656`),
четыре места `max-w-7xl` в `storefront/_base.html` (`:145,157,292,305`), контрол на «Design des Shops».
Решение владельца по умолчанию: Breit (1536).

## 10. Вопросы владельцу
- В-1 решение A (рекомендовано). В-2 «Branche» секцией шторки (рекомендовано).
- В-3 «Nur Aktionen» = `?kind=promotion`, скрыта без акций (рекомендовано).
- В-4 «Wann», «Nur verfügbar», «Umkreis» — секциями шторки (рекомендовано).
- В-5 живое число в подвале — после пилота (рекомендовано).

## 11. ECC-прогоны
| Шаг | Скиллы до кода | Агенты |
|---|---|---|
| после плана | — | `architect` (решение A, счётчики), `seo-specialist` (noindex/nofollow/canonical) |
| FLT-1b | django-patterns, django-tdd, postgres-patterns, python-testing | `tdd-guide`, `django-reviewer`, `security-reviewer`, `silent-failure-hunter` |
| FLT-1c | postgres-patterns, django-patterns | `database-reviewer` (EXPLAIN, индексы), `django-reviewer` |
| FLT-1d | accessibility, seo, django-security | `django-reviewer`, `a11y-architect` |
| FLT-1e | e2e-testing, accessibility | `e2e-runner` (Python-Playwright, `/opt/pw-browsers`), `a11y-architect` |
| FLT-1f | api-design, django-security | `security-reviewer`, `django-reviewer` |
| перед мержем | django-verification (наш гейт) | `code-reviewer`, `doc-updater` |

Грабли (`docs/pitfalls.md`): `{{ block.super }}` и переменные контекст-процессора в фильтрах;
многострочные `{# #}`; пересборка CSS; скрытие только CSS (W0); `ruff format --check .` целиком.

## 12. Поправки по SEO-ревью (seo-specialist, 2026-11-04) — заменяют §2.3 в части индексации
1. **Индексируемы** (self-canonical, в sitemap): корень, `/stadtteil/<slug>/`, `/<facet>/` без query,
   страницы бизнесов — без изменений.
2. **`noindex,follow`** — ЛЮБАЯ страница портала с query из `search.FILTER_PARAMS ∪
   {q,kind,neu,sort,lat,lng,roh,ansicht}` и смешанная форма «путь + query» (`/stadtteil/a/?stadtteil=b`);
   `cursor`/`seite` сами по себе — нет. Ключ `robots_noindex` в контексте `portal_home`
   (`portal_base.html:9` его уже читает). На таких страницах canonical — на себя (не на путь).
3. **robots.txt** живых порталов (`portal_robots_txt`, `portal_views.py:981-1012`): `Disallow:
   /*stadtteil=*stadtteil=`, `/*kat=*kat=`, `/*merkmal=*merkmal=` — noindex не останавливает обход
   сочетаний, nofollow — только подсказка. Пути (`/stadtteil/<slug>/`) не задеты (в них нет `=`).
4. **`rel=nofollow`** — только на ссылках с noindex-целью (query); ссылки на путевые лендинги —
   follow, хотя бы одна follow-ссылка на каждый район/отрасль остаётся (навигация главной).
5. Канон района: ровно один район → путь `/stadtteil/<slug>/`, ≥ 2 → query-форма.
6. **Решение A с оговоркой:** путевая страница района БЕЗ query сохраняет точный режим и прежний
   набор результатов (замок «как до FLT»), заголовок и JSON-LD не меняются.
Замки: путевая страница без noindex и canonical=путь; каждая query-вариация — noindex; robots.txt
содержит wildcard-правила и не закрывает `/stadtteil/<slug>/`.

## 13. Поправки по ревью архитектора (architect, 2026-11-04) — обязательны для FLT-1b/1c
1. **Режим поиска и решение A.** Режим (fts / soft / trigram) решается один раз на широком пуле
   (он же кормит счётчики), но выдача считается так: в `fts` фильтр района после — эквивалентен;
   в `soft`/`trigram` этот шаг-фолбэк ПЕРЕЗАПУСКАЕТСЯ на пуле с районом (или предикат района
   передаётся в `_trigram_pks`). Иначе страница района пуста при «похожих» только в нём (`search.py:
   268,662,673-687`), и хвост Г5 гаснет из-за `main_fuzzy` (`portal_views.py:177,477`).
2. **Путь района — отдельная область, не GET-фильтр.** Иначе голая `/stadtteil/x/` становится
   «поиском»: лимит `portal-search`, `searching=True`, запись в журнал, ключ `stadtteil=x&stadtteil=x`
   (`portal_views.py:297,363,401,411`). `active`/`searching`/`record`/лимит читают только GET;
   путь сливается с GET-районами только внутри `_district_pool`.
3. **Схема URL путь + шторка** (сейчас W0-потеря: `portal_views.py:290-291`, ✕ района = мёртвая
   ссылка `:788`, `follow_link` и `ai_search` перетирают): форма шторки — action корня (или
   `/<facet>/`), район пути — заранее отмеченная галочка; снятие района пути → корень; путь + param =
   объединение везде (ссылка подписки, ИИ-слияние, журнал); ровно один район и нет других фильтров →
   ссылка на `/stadtteil/<slug>/`.
4. **Счётчики:** «N Treffer» сейчас под капом 240 (`count_capped`) — для показа берётся ТОЧНОЕ число
   из того же агрегата, кап только для пагинации; база счётчиков — `base_pool` с kind/neu, плюс
   `firm_total`; `merkmal` — И: невыбранный признак считает «текущие ∪ {t}», выбранный = Treffer
   (исключение своего фасета — только для районов и разделов); сохранить `cc.tags_for(kat)` (союз при
   нескольких), разворот раздела в категории `keys_for_filter`, заголовок из `category_chips.label`.
5. **Стоимость:** агрегат по `AggregatorListing.objects.filter(pk__in=pool.order_by().values("pk"))`
   (без `SearchRank`/CASE-аннотаций), EXPLAIN ANALYZE в FLT-1c; индексов на `district`/`city_tags`
   нет — замерить, функциональный `Upper(city)` только по замеру; выражений может быть > 100.
6. **Подписка:** не предлагать кнопку при районах > потолка (а не молча усекать); `_district_pool`
   получает районы только через `filters_eff` — три вызова (страница, Г5, подписка) одинаковы.
7. Переименование `district` → `districts` затрагивает также `query_intent.py:310,340,353`,
   `mcp/handlers.py:433`, `portal_views.py:181,291,464,782-788`, `follow_query.py:132`; журнал —
   список только при > 1 значении; MCP — вход одиночный, ветку «список» не делать (YAGNI).
8. **SEO-разногласие решено:** `Disallow` в robots.txt для сочетаний НЕ ставим — он прячет от
   робота сам `noindex` (грабля T-8.26 п.2); правило — `noindex,follow` + `rel=nofollow` на ссылках
   с query-целью. Одиночный `?stadtteil=a` на корне → canonical на `/stadtteil/a/`.
9. «Branche» в шторке — ссылками (путь не задаётся GET-формой); `_facet_choices` сузить по
   районам из параметров.
Новые замки: (i) страница района, опечатка, «похожие» только в этом районе → показаны;
(ii) `/stadtteil/x/` без query не пишет журнал и не тратит лимит `portal-search`; (iii) путь +
`?stadtteil=b` держит оба значения в выдаче, ссылке подписки и ИИ-слиянии; (iv) письмо подписки
⊆ «Alle anzeigen» с двумя районами.
